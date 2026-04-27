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

    func bootstrap() async {
        state = .checking
        if await auth.verifySession() {
            state = .signedIn
        } else {
            state = .signedOut
        }
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

    func signOut() async {
        await auth.logout()
        username = ""
        password = ""
        // Wipe any stale error banner from a previous failed sign-in so the
        // login screen presents fresh on next appearance.
        loginError = nil
        state = .signedOut
    }
}
