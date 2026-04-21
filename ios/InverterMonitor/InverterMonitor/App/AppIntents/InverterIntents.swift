import AppIntents
import Foundation

/// These intents appear in Shortcuts, Siri, and Spotlight. They reach the shared
/// `APIClient` via `IntentServiceContainer` which is itself bootstrapped from
/// `InverterMonitorApp.init()` so cookies + server URL match the foreground app.

enum IntentOutputPriorityOption: String, AppEnum {
    case utilityFirst, solarFirst, sbu

    static let typeDisplayRepresentation: TypeDisplayRepresentation = "Output Priority"
    static let caseDisplayRepresentations: [Self: DisplayRepresentation] = [
        .utilityFirst: DisplayRepresentation(title: "Utility First"),
        .solarFirst: DisplayRepresentation(title: "Solar First"),
        .sbu: DisplayRepresentation(title: "SBU (Solar → Battery → Utility)")
    ]

    var apiValue: OutputPriority {
        switch self {
        case .utilityFirst: return .uti
        case .solarFirst: return .sol
        case .sbu: return .sbu
        }
    }
}

enum IntentChargerPriorityOption: String, AppEnum {
    case onlySolar, solarFirst, solarUtility, utilitySolar

    static let typeDisplayRepresentation: TypeDisplayRepresentation = "Charger Priority"
    static let caseDisplayRepresentations: [Self: DisplayRepresentation] = [
        .onlySolar: DisplayRepresentation(title: "Only Solar"),
        .solarFirst: DisplayRepresentation(title: "Solar First"),
        .solarUtility: DisplayRepresentation(title: "Solar + Utility"),
        .utilitySolar: DisplayRepresentation(title: "Utility + Solar")
    ]

    var apiValue: ChargerPriority {
        switch self {
        case .onlySolar: return .solOnly
        case .solarFirst: return .solFirst
        case .solarUtility: return .solUti
        case .utilitySolar: return .utiSol
        }
    }
}

/// Wraps a unified "please sign in" dialog when an intent runs cold (the app has
/// never been launched this session, so no session cookie exists yet).
private func dialogForIntentError(_ error: Error, action: String) -> IntentDialog {
    if case APIError.notAuthenticated = error {
        return IntentDialog("Open Inverter Monitor and sign in, then try \(action) again.")
    }
    if let apiError = error as? APIError, let msg = apiError.errorDescription {
        return IntentDialog(stringLiteral: msg)
    }
    return IntentDialog(stringLiteral: "Couldn't \(action): \(error.localizedDescription)")
}

struct SetOutputPriorityIntent: AppIntent {
    static let title: LocalizedStringResource = "Set Output Priority"
    static let description = IntentDescription(
        "Switches the inverter's output source priority (where the load pulls power from)."
    )
    static let openAppWhenRun: Bool = false

    @Parameter(title: "Mode", requestValueDialog: "Which output mode?")
    var mode: IntentOutputPriorityOption

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let command = IntentServiceContainer.shared.commandService
        do {
            let result = try await command.setOutputPriority(mode.apiValue)
            let label = result.applied?.label ?? mode.apiValue.title
            return .result(dialog: IntentDialog("Output priority set to \(label)."))
        } catch {
            return .result(dialog: dialogForIntentError(error, action: "changing output priority"))
        }
    }
}

struct SetChargerPriorityIntent: AppIntent {
    static let title: LocalizedStringResource = "Set Charger Priority"
    static let description = IntentDescription(
        "Switches what source is allowed to charge the battery."
    )
    static let openAppWhenRun: Bool = false

    @Parameter(title: "Mode", requestValueDialog: "Which charger mode?")
    var mode: IntentChargerPriorityOption

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let command = IntentServiceContainer.shared.commandService
        do {
            let result = try await command.setChargerPriority(mode.apiValue)
            let label = result.applied?.label ?? mode.apiValue.title
            return .result(dialog: IntentDialog("Charger priority set to \(label)."))
        } catch {
            return .result(dialog: dialogForIntentError(error, action: "changing charger priority"))
        }
    }
}

struct GetInverterStatusIntent: AppIntent {
    static let title: LocalizedStringResource = "Check Inverter Status"
    static let description = IntentDescription(
        "Reads the inverter's current mode, solar production, battery state, and load."
    )
    static let openAppWhenRun: Bool = false

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let inverter = IntentServiceContainer.shared.inverterService
        do {
            let status = try await inverter.status()
            guard status.success else {
                return .result(dialog: IntentDialog("Inverter is offline."))
            }
            let m = status.metrics
            let dialog = """
            \(status.system.modeLabel). \
            Solar \(Int(m.solar.power.rounded())) watts, \
            battery \(Int(m.battery.percentage.rounded())) percent, \
            load \(Int(m.load.effectivePower.rounded())) watts.
            """
            return .result(dialog: IntentDialog(stringLiteral: dialog))
        } catch {
            return .result(dialog: dialogForIntentError(error, action: "reading the inverter"))
        }
    }
}

struct InverterAppShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: GetInverterStatusIntent(),
            phrases: [
                "Check \(.applicationName)",
                "What's my \(.applicationName) status",
                "Get \(.applicationName) status"
            ],
            shortTitle: "Check Status",
            systemImageName: "bolt.circle.fill"
        )
        AppShortcut(
            intent: SetOutputPriorityIntent(),
            phrases: [
                "Set \(.applicationName) output priority"
            ],
            shortTitle: "Set Output Priority",
            systemImageName: "house.fill"
        )
        AppShortcut(
            intent: SetChargerPriorityIntent(),
            phrases: [
                "Set \(.applicationName) charger priority"
            ],
            shortTitle: "Set Charger Priority",
            systemImageName: "battery.100.bolt"
        )
    }
}

/// Bridges AppIntents (which run in their own process context) to the shared
/// services that hold cookies / server URL state.
@MainActor
final class IntentServiceContainer {
    static let shared = IntentServiceContainer()

    private(set) var settings: AppSettings
    private(set) var api: APIClient
    private(set) var inverterService: InverterService
    private(set) var commandService: CommandService

    private init() {
        let settings = AppSettings()
        let api = APIClient(settings: settings)
        self.settings = settings
        self.api = api
        self.inverterService = InverterService(api: api)
        self.commandService = CommandService(api: api)
    }

    /// Called by AppEnvironment during app launch to replace the default container with
    /// the one that already has a live session cookie.
    static func adopt(
        settings: AppSettings,
        api: APIClient,
        inverterService: InverterService,
        commandService: CommandService
    ) {
        shared.settings = settings
        shared.api = api
        shared.inverterService = inverterService
        shared.commandService = commandService
    }
}
