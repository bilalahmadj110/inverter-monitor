import Foundation
import Combine

@MainActor
final class LiveDashboardViewModel: ObservableObject {
    enum ConnectionState: Equatable {
        case connecting
        case connected
        case offline(String)

        var label: String {
            switch self {
            case .connecting: return "Connecting…"
            case .connected: return "Connected"
            case .offline(let reason): return reason.isEmpty ? "Offline" : reason
            }
        }
    }

    enum LiveRange: Int, CaseIterable, Identifiable {
        case fiveMinutes = 5
        case thirtyMinutes = 30
        case twoHours = 120
        case sixHours = 360

        var id: Int { rawValue }
        var label: String {
            switch self {
            case .fiveMinutes: return "5m"
            case .thirtyMinutes: return "30m"
            case .twoHours: return "2h"
            case .sixHours: return "6h"
            }
        }
    }

    @Published private(set) var status: InverterStatus = .placeholder
    @Published private(set) var summary: DailySummary = .placeholder
    @Published private(set) var monthStats: MonthlyStats?
    @Published private(set) var yearStats: YearlyStats?
    @Published private(set) var config: InverterConfig = InverterConfig()
    @Published private(set) var readingStats: ReadingStats?
    @Published private(set) var lastUpdate: Date?
    @Published private(set) var connection: ConnectionState = .connecting
    @Published private(set) var isRefreshingExtras = false
    @Published private(set) var recentReadings: RecentReadings = .empty
    @Published private(set) var isLoadingRecent = false
    @Published var liveRange: LiveRange = .thirtyMinutes {
        didSet { if liveRange != oldValue { Task { await loadRecentReadings() } } }
    }
    @Published var dismissedWarnings = false
    @Published var priorityFlash: String?
    @Published var priorityError: String?
    @Published private(set) var isApplyingPriority = false

    private let inverter: InverterService
    private let commands: CommandService

    private var statusTask: Task<Void, Never>?
    private var statsTask: Task<Void, Never>?
    private var recentTask: Task<Void, Never>?
    private var isStopped = true
    private var lastAnnouncedFaultKeys: Set<String> = []
    /// Set on first successful status fetch. Any faults that pre-existed at app launch
    /// aren't announced via notification (the warnings banner shows them in the UI instead).
    private var hasSeenInitialFaults = false
    /// Flipped true after the first /refresh-extras this session so we don't re-fetch
    /// QMOD/QPIWS/QPIRI every time the user resumes the app (scene-phase → start()).
    private var didInitialExtrasFetch = false

    /// Callback invoked whenever a *new* fault (one we haven't seen this session) enters
    /// the warnings list. Wired by the App to drive local notifications.
    var onNewFault: ((InverterWarning) -> Void)?
    /// Callback invoked when the session is no longer valid (401/403 from the server).
    var onSessionExpired: (() -> Void)?

    init(inverter: InverterService, commands: CommandService) {
        self.inverter = inverter
        self.commands = commands
    }

    // MARK: - Lifecycle --------------------------------------------------------

    func start() {
        guard isStopped else { return }
        isStopped = false
        connection = .connecting
        statusTask = Task { [weak self] in
            await self?.statusLoop()
        }
        statsTask = Task { [weak self] in
            await self?.statsLoop()
        }
        recentTask = Task { [weak self] in
            await self?.recentLoop()
        }
        // Fire exactly one extras refresh on the first connect of this session so the
        // config (QPIRI) and warnings (QPIWS) are populated before the user opens a
        // component sheet. After this, /refresh-extras is only hit via the toolbar
        // button or as a side-effect of setOutputPriority/setChargerPriority.
        if !didInitialExtrasFetch {
            didInitialExtrasFetch = true
            Task { [weak self] in await self?.refreshExtras() }
        }
    }

    func stop() {
        isStopped = true
        statusTask?.cancel(); statusTask = nil
        statsTask?.cancel(); statsTask = nil
        recentTask?.cancel(); recentTask = nil
    }

    /// Reset state tied to "this session" so a sign-out followed by a fresh sign-in
    /// doesn't carry over the previous user's fault-dedup set or cached connection state.
    func resetSessionState() {
        status = .placeholder
        summary = .placeholder
        monthStats = nil
        yearStats = nil
        config = InverterConfig()
        readingStats = nil
        lastUpdate = nil
        connection = .connecting
        recentReadings = .empty
        priorityFlash = nil
        priorityError = nil
        dismissedWarnings = false
        lastAnnouncedFaultKeys = []
        hasSeenInitialFaults = false
        didInitialExtrasFetch = false
        // Clear in-flight flags too — if sign-out interrupted a refresh/priority-change,
        // the view would otherwise keep showing a spinning indicator after re-sign-in.
        isRefreshingExtras = false
        isLoadingRecent = false
        isApplyingPriority = false
    }

    // MARK: - Polling loops ----------------------------------------------------

    private func statusLoop() async {
        while !Task.isCancelled && !isStopped {
            await fetchStatus()
            try? await Task.sleep(nanoseconds: 3_000_000_000) // 3s matches the backend reader cadence.
        }
    }

    private func statsLoop() async {
        // /stats returns the same payload as the WebSocket `stats_update` event; poll every minute.
        await fetchStats()
        while !Task.isCancelled && !isStopped {
            try? await Task.sleep(nanoseconds: 60_000_000_000)
            await fetchStats()
        }
    }

    private func recentLoop() async {
        await loadRecentReadings()
        while !Task.isCancelled && !isStopped {
            let cadence = liveRange == .fiveMinutes ? 3 : liveRange == .thirtyMinutes ? 5 : 10
            try? await Task.sleep(nanoseconds: UInt64(cadence) * 1_000_000_000)
            await loadRecentReadings()
        }
    }

    // MARK: - Fetchers ---------------------------------------------------------

    @discardableResult
    func fetchStatus() async -> Bool {
        do {
            let next = try await inverter.status()
            self.status = next
            self.lastUpdate = Date()
            self.connection = next.success ? .connected : .offline("Inverter Offline")
            announceNewFaults(in: next.system.warnings)
            return true
        } catch APIError.notAuthenticated {
            connection = .offline("Session expired")
            onSessionExpired?()
            return false
        } catch let err as APIError {
            connection = .offline(err.errorDescription ?? "Offline")
            return false
        } catch {
            connection = .offline(error.localizedDescription)
            return false
        }
    }

    private func announceNewFaults(in warnings: [InverterWarning]) {
        let currentKeys = Set(warnings.filter { $0.severity == .fault }.map { $0.key })
        defer { lastAnnouncedFaultKeys = currentKeys }
        // Seed silently on the first successful fetch so we don't notification-spam
        // pre-existing faults the user already sees in the warnings banner.
        guard hasSeenInitialFaults else {
            hasSeenInitialFaults = true
            return
        }
        let newKeys = currentKeys.subtracting(lastAnnouncedFaultKeys)
        for key in newKeys {
            if let warning = warnings.first(where: { $0.key == key }) {
                onNewFault?(warning)
            }
        }
    }

    func fetchStats() async {
        // `/stats` returns `day` as a raw daily_stats row (solar_energy in Wh with no kWh
        // derivatives), so we can't decode it as DailySummary — hit `/summary` instead,
        // which returns the pre-converted kWh + self_sufficiency + solar_fraction shape.
        // Month/year keep coming from /stats since MonthlyStats/YearlyStats decode Wh
        // correctly and the view divides by 1000.
        async let summaryFetch = inverter.summary()
        async let statsFetch = inverter.allStats()
        if let summary = try? await summaryFetch {
            self.summary = summary
        }
        if let stats = try? await statsFetch {
            if let month = stats.month { self.monthStats = month }
            if let year = stats.year { self.yearStats = year }
            if let config = stats.config { self.config = config }
            if let readingStats = stats.readingStats { self.readingStats = readingStats }
        }
    }

    func loadRecentReadings() async {
        isLoadingRecent = true
        defer { isLoadingRecent = false }
        do {
            let data = try await inverter.recentReadings(minutes: liveRange.rawValue)
            self.recentReadings = data
        } catch {
            // Keep last good data.
        }
    }

    // MARK: - Extras / config --------------------------------------------------

    func refreshExtras() async {
        guard !isRefreshingExtras else { return }
        isRefreshingExtras = true
        defer { isRefreshingExtras = false }
        do {
            let extras = try await commands.refreshExtras()
            if !extras.config.isEmpty {
                self.config = extras.config
            }
            if let mode = extras.mode {
                var newSystem = status.system
                newSystem.mode = InverterMode.from(raw: mode)
                newSystem.modeLabel = newSystem.mode.defaultLabel
                self.status = InverterStatus(
                    success: status.success,
                    metrics: status.metrics,
                    system: newSystem,
                    timing: status.timing,
                    error: status.error
                )
            }
            if !extras.warnings.isEmpty || status.system.warnings.count > 0 {
                var newSystem = status.system
                newSystem.warnings = extras.warnings
                newSystem.hasFault = extras.warnings.contains { $0.severity == .fault }
                self.status = InverterStatus(
                    success: status.success,
                    metrics: status.metrics,
                    system: newSystem,
                    timing: status.timing,
                    error: status.error
                )
            }
        } catch {
            // swallow
        }
    }

    // MARK: - Priority changes -------------------------------------------------

    func setOutputPriority(_ mode: OutputPriority) async {
        isApplyingPriority = true
        priorityError = nil
        priorityFlash = nil
        defer { isApplyingPriority = false }
        do {
            // Server's /set-output-priority already runs QPIRI after the POP write and
            // returns fresh config; a follow-up /refresh-extras would double the wait.
            let result = try await commands.setOutputPriority(mode)
            if let applied = result.applied {
                priorityFlash = "Applied: \(applied.label)"
            } else {
                priorityFlash = "Applied: \(mode.title)"
            }
            if let cfg = result.config { self.config = cfg }
            scheduleFlashDismiss()
        } catch let err as APIError {
            priorityError = err.errorDescription
            scheduleErrorDismiss()
        } catch {
            priorityError = error.localizedDescription
            scheduleErrorDismiss()
        }
    }

    func setChargerPriority(_ mode: ChargerPriority) async {
        isApplyingPriority = true
        priorityError = nil
        priorityFlash = nil
        defer { isApplyingPriority = false }
        do {
            let result = try await commands.setChargerPriority(mode)
            if let applied = result.applied {
                priorityFlash = "Applied: \(applied.label)"
            } else {
                priorityFlash = "Applied: \(mode.title)"
            }
            if let cfg = result.config { self.config = cfg }
            scheduleFlashDismiss()
        } catch let err as APIError {
            priorityError = err.errorDescription
            scheduleErrorDismiss()
        } catch {
            priorityError = error.localizedDescription
            scheduleErrorDismiss()
        }
    }

    /// Success toast auto-dismisses after 4 seconds so the detail sheet doesn't
    /// stay cluttered after the user has seen the confirmation.
    private func scheduleFlashDismiss() {
        let token = priorityFlash
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 4_000_000_000)
            // Only dismiss if the flash hasn't been replaced by a newer one.
            guard let self, self.priorityFlash == token else { return }
            self.priorityFlash = nil
        }
    }

    private func scheduleErrorDismiss() {
        // Errors stay a little longer so the user has time to read them.
        let token = priorityError
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 6_000_000_000)
            guard let self, self.priorityError == token else { return }
            self.priorityError = nil
        }
    }

    // MARK: - Derived display values ------------------------------------------

    var modeStyle: ModePillStyle { ModePillStyle.style(for: status.system.mode) }

    var activeWarnings: [InverterWarning] { status.system.warnings }

    var showWarningsBanner: Bool {
        !dismissedWarnings && !activeWarnings.isEmpty
    }

    var solarIsActive: Bool { status.metrics.solar.power > 5 }
    var gridIsActive: Bool { status.metrics.grid.inUse }
    var loadIsActive: Bool { status.metrics.load.effectivePower > 5 }
    var batteryIsActive: Bool { status.metrics.battery.voltage > 20 }

    var batteryDirectionText: String {
        switch status.metrics.battery.direction {
        case .charging:
            return "Charging \(Int(abs(status.metrics.battery.power).rounded())) W"
        case .discharging:
            return "Discharging \(Int(abs(status.metrics.battery.power).rounded())) W"
        case .idle:
            return "Idle"
        }
    }

    var gridFlowLabel: String {
        if status.system.isAcChargingOn {
            return "Grid charging · \(Int(status.metrics.grid.power.rounded())) W"
        }
        if status.metrics.grid.inUse {
            return "Grid in use · ~\(Int(status.metrics.grid.power.rounded())) W"
        }
        return ""
    }
}

struct ModePillStyle {
    var label: String
    var primary: String
    var background: String
    var dot: String

    static func style(for mode: InverterMode) -> ModePillStyle {
        switch mode {
        case .line:
            return ModePillStyle(label: "Line Mode", primary: "#BFDBFE", background: "#1D4ED8", dot: "#93C5FD")
        case .battery:
            return ModePillStyle(label: "Battery Mode", primary: "#A7F3D0", background: "#047857", dot: "#6EE7B7")
        case .standby:
            return ModePillStyle(label: "Standby", primary: "#E2E8F0", background: "#334155", dot: "#CBD5E1")
        case .powerOn:
            return ModePillStyle(label: "Power On", primary: "#BAE6FD", background: "#0369A1", dot: "#7DD3FC")
        case .powerSaving:
            return ModePillStyle(label: "Power Saving", primary: "#C7D2FE", background: "#3730A3", dot: "#A5B4FC")
        case .charging:
            return ModePillStyle(label: "Charging", primary: "#FDE68A", background: "#B45309", dot: "#FCD34D")
        case .fault:
            return ModePillStyle(label: "Fault", primary: "#FECACA", background: "#B91C1C", dot: "#F87171")
        case .shutdown:
            return ModePillStyle(label: "Shutdown", primary: "#E5E7EB", background: "#52525B", dot: "#D4D4D8")
        }
    }
}
