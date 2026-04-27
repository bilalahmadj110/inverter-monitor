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

        // Session expired anywhere → flip the AuthViewModel back to signedOut so
        // RootView re-renders LoginView. Logout best-effort to clear any stale cookie.
        // Same handler from both Live and Reports so neither tab gets stuck.
        // We also reset VM state so a fresh sign-in doesn't inherit the previous
        // user's fault-dedup set / cached metrics.
        let handleExpired: () -> Void = { [weak authVM, weak liveVM, weak reportsVM] in
            Task { @MainActor in
                liveVM?.resetSessionState()
                reportsVM?.invalidateHistoryCache()
                await authVM?.signOut()
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
