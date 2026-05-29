import Foundation
import Combine

@MainActor
final class AuthViewModel: ObservableObject {
    enum State: Equatable {
        case idle
        case checking
        case signedOut
        case signedIn
        case signingIn
        case error(String)
    }

    @Published var state: State = .idle
    @Published var username: String = ""
    @Published var password: String = ""
    @Published var loginError: String?

    let settings: AppSettings
    private let auth: AuthService

    init(settings: AppSettings, auth: AuthService) {
        self.settings = settings
        self.auth = auth
        // Prefill the username field from the Keychain so the user sees their
        // existing account pre-filled if they ever land back on LoginView after
        // an explicit sign-out. Password isn't prefilled for UX — a silent
        // re-login consumes it directly instead.
        if let saved = CredentialStore.load() {
            self.username = saved.username
        }
    }

    var isSignedIn: Bool {
        if case .signedIn = state { return true }
        return false
    }

    var isBusy: Bool {
        switch state {
        case .checking, .signingIn: return true
        default: return false
        }
    }

    /// App launch: try the existing session cookie first, then fall back to saved
    /// Keychain credentials before bouncing the user to the login screen. Together
    /// this means the user only ever types credentials once per device.
    func bootstrap() async {
        state = .checking
        if await auth.verifySession() {
            state = .signedIn
            return
        }
        if await attemptSilentLogin() {
            state = .signedIn
            return
        }
        state = .signedOut
    }

    func signIn() async {
        guard !username.isEmpty, !password.isEmpty else {
            loginError = "Enter username and password."
            return
        }
        loginError = nil
        state = .signingIn
        do {
            try await auth.login(username: username, password: password)
            // Persist for silent re-login on session expiry / cold start.
            CredentialStore.save(.init(username: username, password: password))
            password = ""
            state = .signedIn
        } catch let err as APIError {
            loginError = err.errorDescription
            state = .signedOut
        } catch {
            loginError = error.localizedDescription
            state = .signedOut
        }
    }

    /// Re-login using Keychain credentials without user interaction. Used both by
    /// bootstrap (cold start, expired cookie) and by the session-expired handler
    /// wired in AppEnvironment (mid-session 401/403 from the server).
    /// Returns true when the login succeeded and a fresh session cookie is in place.
    func attemptSilentLogin() async -> Bool {
        guard let saved = CredentialStore.load() else { return false }
        do {
            try await auth.login(username: saved.username, password: saved.password)
            return true
        } catch {
            return false
        }
    }

    func signOut() async {
        await auth.logout()
        // Explicit sign-out is the one path that clears stored credentials — the
        // user told us they want to stop auto-logging-in, so wipe the keychain
        // entry. Any background silent re-login attempt will now fail cleanly.
        CredentialStore.clear()
        username = ""
        password = ""
        // Wipe any stale error banner from a previous failed sign-in so the
        // login screen presents fresh on next appearance.
        loginError = nil
        state = .signedOut
    }
}
