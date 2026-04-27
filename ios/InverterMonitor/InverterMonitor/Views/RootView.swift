import SwiftUI

struct RootView: View {
    @EnvironmentObject var appEnv: AppEnvironment
    @EnvironmentObject var auth: AuthViewModel

    var body: some View {
        Group {
            switch auth.state {
            case .idle, .checking:
                ProgressView("Signing in…")
                    .tint(.white)
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .immersiveBackground()
            case .signedOut, .signingIn, .error:
                LoginView()
            case .signedIn:
                MainTabView()
            }
        }
        .task { await auth.bootstrap() }
    }
}
