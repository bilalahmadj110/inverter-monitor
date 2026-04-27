import Foundation

enum APIError: LocalizedError, Equatable {
    case invalidURL
    case notAuthenticated
    case server(code: Int, body: String)
    case decoding(String)
    case network(String)
    case csrfMissing
    case rateLimited
    case noData

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Server URL is invalid."
        case .notAuthenticated: return "Not signed in."
        case .server(let code, let body):
            if body.isEmpty { return "Server returned HTTP \(code)." }
            return "Server error \(code): \(body)"
        case .decoding(let detail): return "Failed to parse response: \(detail)"
        case .network(let detail): return "Network error: \(detail)"
        case .csrfMissing: return "Could not fetch CSRF token."
        case .rateLimited: return "Rate limited. Try again in a moment."
        case .noData: return "No data received."
        }
    }
}

/// Thin URLSession wrapper:
///   • honors cookies (Flask session) automatically,
///   • serializes JSON, form-encoded, and plain queries,
///   • scrapes the CSRF token from HTML pages for write requests,
///   • transparently refreshes + retries once if the server rejects a stale CSRF token.
final class APIClient {
    let settings: AppSettings
    let session: URLSession
    private let noRedirectDelegate = NoRedirectDelegate()
    private let noRedirectSession: URLSession

    private(set) var csrfToken: String?

    init(settings: AppSettings) {
        self.settings = settings
        let cfg = URLSessionConfiguration.default
        // Use the app's *shared* cookie jar so sessions persist across launches:
        // HTTPCookieStorage.shared is backed by disk inside the app's sandbox, so
        // a valid Flask session cookie survives cold starts — user doesn't have
        // to re-login until the server session expires (60 minutes by default).
        cfg.httpCookieStorage = .shared
        cfg.httpCookieAcceptPolicy = .always
        cfg.timeoutIntervalForRequest = 15
        cfg.timeoutIntervalForResource = 30
        cfg.requestCachePolicy = .reloadIgnoringLocalCacheData
        self.session = URLSession(configuration: cfg)
        // Reuse one session for non-redirect POSTs (login / logout) so we're not
        // recreating URLSession on every write. Shares the cookie jar with `session`
        // because both use the same configuration object.
        self.noRedirectSession = URLSession(configuration: cfg, delegate: noRedirectDelegate, delegateQueue: nil)
    }

    // MARK: - URL building -----------------------------------------------------

    func url(_ path: String, query: [String: String?] = [:]) throws -> URL {
        guard let base = settings.baseURL else { throw APIError.invalidURL }
        guard var comp = URLComponents(url: base, resolvingAgainstBaseURL: false) else {
            throw APIError.invalidURL
        }
        comp.path = path.hasPrefix("/") ? path : "/" + path
        let items = query.compactMap { key, value -> URLQueryItem? in
            guard let value else { return nil }
            return URLQueryItem(name: key, value: value)
        }
        comp.queryItems = items.isEmpty ? nil : items
        guard let url = comp.url else { throw APIError.invalidURL }
        return url
    }

    // MARK: - GET / POST core --------------------------------------------------

    func getJSON<T: Decodable>(_ path: String, query: [String: String?] = [:], as type: T.Type = T.self) async throws -> T {
        let url = try url(path, query: query)
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await perform(req)
        try checkAuth(response)
        try checkStatus(response, data: data)
        return try decode(type, from: data)
    }

    func getRaw(_ path: String, query: [String: String?] = [:]) async throws -> (Data, HTTPURLResponse) {
        let url = try url(path, query: query)
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        let (data, response) = try await perform(req)
        return (data, response)
    }

    func postJSON<T: Decodable>(_ path: String, body: [String: Any] = [:], query: [String: String?] = [:], timeout: TimeInterval? = nil, as type: T.Type = T.self) async throws -> T {
        // One-shot retry: if the first POST is rejected as a CSRF mismatch, refresh the
        // token and try again. Flask-WTF tokens rotate with session lifetime (1h default).
        //
        // `allowRedirects: false` is critical — otherwise, when the server session has
        // expired the POST gets 302'd to /login, URLSession follows to the 200 login page,
        // and JSON decode fails with a cryptic "decoding" error instead of surfacing that
        // the user needs to re-authenticate.
        //
        // `timeout` overrides the session default (15s) — writes that talk to the inverter
        // over USB can legitimately take 60+ seconds due to PI30's retry/backoff budget.
        for attempt in 0..<2 {
            let url = try url(path, query: query)
            var req = URLRequest(url: url)
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.setValue("application/json", forHTTPHeaderField: "Accept")
            if let timeout { req.timeoutInterval = timeout }
            if let token = try await ensureCSRFToken() {
                req.setValue(token, forHTTPHeaderField: "X-CSRFToken")
            }
            req.httpBody = try JSONSerialization.data(withJSONObject: body, options: [])
            let (data, response) = try await perform(req, allowRedirects: false)
            if response.statusCode == 302 || response.statusCode == 303 {
                // Flask redirects to /login when the session cookie is no longer valid.
                throw APIError.notAuthenticated
            }
            try checkAuth(response)
            if attempt == 0, response.statusCode == 400, isCSRFFailure(data: data) {
                csrfToken = nil
                _ = try? await refreshCSRFToken()
                continue
            }
            try checkStatus(response, data: data)
            return try decode(type, from: data)
        }
        // Unreachable — the loop either returns or throws, but the compiler needs this.
        throw APIError.server(code: 400, body: "Retry exhausted")
    }

    private func isCSRFFailure(data: Data) -> Bool {
        let body = (String(data: data, encoding: .utf8) ?? "").lowercased()
        return body.contains("csrf") || body.contains("the csrf token")
    }

    /// POST form-encoded. Used for the Flask login form.
    func postForm(_ path: String, fields: [String: String], includeCSRFInBody: Bool = true) async throws -> (Data, HTTPURLResponse) {
        let url = try url(path)
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        var merged = fields
        if includeCSRFInBody, let token = try await ensureCSRFToken() {
            merged["csrf_token"] = token
            req.setValue(token, forHTTPHeaderField: "X-CSRFToken")
        }
        req.httpBody = encodeForm(merged).data(using: .utf8)
        return try await perform(req, allowRedirects: false)
    }

    // MARK: - CSRF --------------------------------------------------------------

    /// Fetch /login (or /) and scrape the csrf token from the form / meta tag.
    @discardableResult
    func refreshCSRFToken() async throws -> String {
        // Try `/` first (authed pages embed a meta tag). If that redirects to /login,
        // scrape the login form instead.
        let candidates = ["/", "/login"]
        for path in candidates {
            let urlObj = try url(path)
            var req = URLRequest(url: urlObj)
            req.httpMethod = "GET"
            req.setValue("text/html", forHTTPHeaderField: "Accept")
            let (data, response) = try await perform(req)
            guard let html = String(data: data, encoding: .utf8) else { continue }
            if let token = Self.scrapeCSRF(from: html) {
                self.csrfToken = token
                _ = response
                return token
            }
        }
        throw APIError.csrfMissing
    }

    func ensureCSRFToken() async throws -> String? {
        if let token = csrfToken { return token }
        return try await refreshCSRFToken()
    }

    static func scrapeCSRF(from html: String) -> String? {
        // Meta tag first (authed pages): <meta name="csrf-token" content="..."></meta>
        if let range = html.range(of: #"<meta[^>]*name=["']csrf-token["'][^>]*content=["']([^"']+)["'][^>]*>"#,
                                  options: [.regularExpression, .caseInsensitive]) {
            let snippet = String(html[range])
            if let token = firstCapture(in: snippet, pattern: #"content=["']([^"']+)["']"#) {
                return token
            }
        }
        // Form input (login page): <input ... name="csrf_token" value="..."></input>
        if let token = firstCapture(in: html, pattern: #"<input[^>]*name=["']csrf_token["'][^>]*value=["']([^"']+)["'][^>]*>"#) {
            return token
        }
        // Reversed attribute order just in case
        if let token = firstCapture(in: html, pattern: #"<input[^>]*value=["']([^"']+)["'][^>]*name=["']csrf_token["'][^>]*>"#) {
            return token
        }
        return nil
    }

    // MARK: - Session -----------------------------------------------------------

    var hasSessionCookie: Bool {
        guard let url = settings.baseURL else { return false }
        guard let cookies = session.configuration.httpCookieStorage?.cookies(for: url) else { return false }
        return cookies.contains { $0.name == "session" && !$0.value.isEmpty }
    }

    func clearSession() {
        csrfToken = nil
        guard let cookieStore = session.configuration.httpCookieStorage else { return }
        cookieStore.cookies?.forEach { cookieStore.deleteCookie($0) }
    }

    // MARK: - Internals --------------------------------------------------------

    private func perform(_ request: URLRequest, allowRedirects: Bool = true) async throws -> (Data, HTTPURLResponse) {
        do {
            let target = allowRedirects ? session : noRedirectSession
            let (data, response) = try await target.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw APIError.network("Non-HTTP response")
            }
            return (data, http)
        } catch let error as APIError {
            throw error
        } catch let error as URLError {
            throw APIError.network(error.localizedDescription)
        } catch {
            throw APIError.network(error.localizedDescription)
        }
    }

    private func checkAuth(_ response: HTTPURLResponse) throws {
        if response.statusCode == 401 || response.statusCode == 403 {
            throw APIError.notAuthenticated
        }
        if response.statusCode == 429 {
            throw APIError.rateLimited
        }
    }

    private func checkStatus(_ response: HTTPURLResponse, data: Data) throws {
        guard (200..<400).contains(response.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw APIError.server(code: response.statusCode, body: String(body.prefix(400)))
        }
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        if data.isEmpty {
            throw APIError.noData
        }
        do {
            return try JSONDecoder().decode(type, from: data)
        } catch {
            throw APIError.decoding(error.localizedDescription)
        }
    }

    private func encodeForm(_ fields: [String: String]) -> String {
        fields.map { key, value in
            let k = key.addingPercentEncoding(withAllowedCharacters: .urlFormEncoded) ?? key
            let v = value.addingPercentEncoding(withAllowedCharacters: .urlFormEncoded) ?? value
            return "\(k)=\(v)"
        }.joined(separator: "&")
    }
}

private final class NoRedirectDelegate: NSObject, URLSessionTaskDelegate, URLSessionDelegate {
    func urlSession(_ session: URLSession,
                    task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

private extension CharacterSet {
    /// Per `application/x-www-form-urlencoded`: alphanumerics plus `-._~` pass through;
    /// everything else (including space) must be percent-encoded. Werkzeug on the
    /// Flask side accepts `%20` as a space, so we don't have to special-case `+`.
    static let urlFormEncoded: CharacterSet = {
        var allowed = CharacterSet.alphanumerics
        allowed.insert(charactersIn: "-._~")
        return allowed
    }()
}

private func firstCapture(in text: String, pattern: String) -> String? {
    guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { return nil }
    let range = NSRange(text.startIndex..<text.endIndex, in: text)
    guard let match = regex.firstMatch(in: text, options: [], range: range) else { return nil }
    guard match.numberOfRanges >= 2 else { return nil }
    guard let swiftRange = Range(match.range(at: 1), in: text) else { return nil }
    return String(text[swiftRange])
}
