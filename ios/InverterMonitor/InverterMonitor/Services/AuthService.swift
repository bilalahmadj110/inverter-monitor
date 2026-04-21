import Foundation

struct HealthResponse: Decodable, Equatable {
    var ok: Bool
    var version: String?
}

final class AuthService {
    private let api: APIClient

    init(api: APIClient) { self.api = api }

    /// Probe `/healthz`. Used by Settings to verify reachability without needing a session.
    func health() async throws -> HealthResponse {
        try await api.getJSON("/healthz")
    }

    /// Checks if the session cookie is still accepted by the server by calling an authed JSON route.
    func verifySession() async -> Bool {
        do {
            _ = try await api.getJSON("/healthz", as: HealthResponse.self)
            // Healthz is unauth — hit /summary to prove the session is valid.
            _ = try await api.getJSON("/summary", as: DailySummary.self)
            return true
        } catch APIError.notAuthenticated {
            return false
        } catch {
            return false
        }
    }

    /// Flask login: POST /login with form fields + csrf. A successful login always redirects
    /// (302/303); any other 2xx/4xx response means the login page re-rendered with an error.
    func login(username: String, password: String) async throws {
        // Fresh CSRF from the login page (unauth token).
        _ = try await api.refreshCSRFToken()

        let fields = ["username": username, "password": password]
        let (_, response) = try await api.postForm("/login", fields: fields)

        switch response.statusCode {
        case 302, 303:
            // Refresh CSRF against the new session so subsequent writes have a valid token.
            _ = try await api.refreshCSRFToken()
            return
        case 401:
            throw APIError.server(code: 401, body: "Invalid username or password.")
        case 200:
            // Flask renders login.html with a 200 + error banner when credentials are wrong.
            throw APIError.server(code: 401, body: "Invalid username or password.")
        case 429:
            throw APIError.rateLimited
        default:
            throw APIError.server(code: response.statusCode, body: "Login failed (HTTP \(response.statusCode)).")
        }
    }

    func logout() async {
        do {
            _ = try await api.postForm("/logout", fields: [:])
        } catch {
            // Logout best-effort — clear session locally regardless.
        }
        api.clearSession()
    }
}
