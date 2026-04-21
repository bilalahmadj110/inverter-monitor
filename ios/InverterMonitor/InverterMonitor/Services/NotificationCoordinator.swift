import Foundation
import UserNotifications

/// Thin wrapper around UNUserNotificationCenter for posting local notifications
/// when the inverter reports a new fault. Permission is requested the first
/// time a fault would fire (not on app launch) so the prompt appears in-context.
@MainActor
final class NotificationCoordinator {
    private let center = UNUserNotificationCenter.current()
    private var hasRequestedAuth = false
    private var isAuthorized = false

    /// Post a fault notification. Requests authorization on first call; silently
    /// drops if the user previously denied permission.
    func postFault(_ warning: InverterWarning) async {
        guard await ensureAuthorization() else { return }

        let content = UNMutableNotificationContent()
        content.title = "Inverter fault"
        content.body = warning.label
        content.sound = .defaultCritical
        content.threadIdentifier = "inverter-fault"
        content.categoryIdentifier = "inverter-fault"
        content.userInfo = ["key": warning.key]

        let request = UNNotificationRequest(
            identifier: "fault-\(warning.key)",
            content: content,
            trigger: nil // fire immediately
        )
        try? await center.add(request)
    }

    private func ensureAuthorization() async -> Bool {
        let settings = await center.notificationSettings()
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral:
            isAuthorized = true
            return true
        case .denied:
            return false
        case .notDetermined:
            if hasRequestedAuth { return isAuthorized }
            hasRequestedAuth = true
            do {
                let granted = try await center.requestAuthorization(options: [.alert, .sound, .badge])
                isAuthorized = granted
                return granted
            } catch {
                return false
            }
        @unknown default:
            return false
        }
    }
}
