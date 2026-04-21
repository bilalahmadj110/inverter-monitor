import Foundation
import Combine

/// Durable settings that persist across launches.
final class AppSettings: ObservableObject {
    private enum Keys {
        static let serverURL = "server_url"
    }

    @Published var serverURL: String {
        didSet { UserDefaults.standard.set(serverURL, forKey: Keys.serverURL) }
    }

    init() {
        let stored = UserDefaults.standard.string(forKey: Keys.serverURL)
        // Default to the Cloudflare HTTPS tunnel so the session cookie (which is
        // marked Secure by the server when BEHIND_PROXY=1) actually round-trips.
        // Change it via Settings → Server URL.
        self.serverURL = stored ?? "https://miss-new-texts-shopzilla.trycloudflare.com"
    }

    var baseURL: URL? {
        let trimmed = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if let url = URL(string: trimmed), url.scheme != nil { return url }
        return URL(string: "http://\(trimmed)")
    }
}
