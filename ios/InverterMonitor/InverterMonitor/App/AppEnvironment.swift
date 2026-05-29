import Foundation
import Combine

@MainActor
final class AppEnvironment: ObservableObject {
    let settings: AppSettings
    let api: APIClient
    let authService: AuthService
    let inverterService: InverterService
    let commandService: CommandService
    let notifier: NotificationCoordinator

    let authViewModel: AuthViewModel
    let liveViewModel: LiveDashboardViewModel
    let reportsViewModel: ReportsViewModel

    init() {
        let settings = AppSettings()
        let api = APIClient(settings: settings)
        let authService = AuthService(api: api)
        let inverterService = InverterService(api: api)
        let commandService = CommandService(api: api)
        let notifier = NotificationCoordinator()

        self.settings = settings
        self.api = api
        self.authService = authService
        self.inverterService = inverterService
        self.commandService = commandService
        self.notifier = notifier

        let authVM = AuthViewModel(settings: settings, auth: authService)
        let liveVM = LiveDashboardViewModel(inverter: inverterService, commands: commandService)
        let reportsVM = ReportsViewModel(inverter: inverterService)

        self.authViewModel = authVM
        self.liveViewModel = liveVM
        self.reportsViewModel = reportsVM

        // Session expired anywhere → try a silent re-login using saved Keychain
        // credentials first; only bounce the user to LoginView if that fails
        // (e.g. server rotated their password). This keeps the app signed-in
        // through the server's 60-minute session TTL without any user action.
        // Same handler from Live and Reports so neither tab gets stuck.
        let handleExpired: () -> Void = { [weak authVM, weak liveVM, weak reportsVM] in
            Task { @MainActor in
                guard let authVM else { return }
                if await authVM.attemptSilentLogin() {
                    // Session is back. Kick a status refresh so the user sees live
                    // data immediately instead of waiting for the next poll tick.
                    _ = await liveVM?.fetchStatus()
                    return
                }
                // Silent re-login failed — fall back to the original behavior:
                // wipe session state and drop to LoginView.
                liveVM?.resetSessionState()
                reportsVM?.invalidateHistoryCache()
                await authVM.signOut()
            }
        }
        liveVM.onSessionExpired = handleExpired
        reportsVM.onSessionExpired = handleExpired

        // New fault → user-visible local notification (requires permission).
        liveVM.onNewFault = { [weak notifier] warning in
            Task { await notifier?.postFault(warning) }
        }

        // Rebuilding daily_stats invalidates the Reports history cache, so Month/Year
        // tabs reflect the new totals next time they're opened.
        commandService.onDidRecompute = { [weak reportsVM] in
            Task { @MainActor in reportsVM?.invalidateHistoryCache() }
        }

        // Ensure AppIntents (Siri / Shortcuts) reach the same session cookies as the app.
        IntentServiceContainer.adopt(
            settings: settings,
            api: api,
            inverterService: inverterService,
            commandService: commandService
        )
    }
}
