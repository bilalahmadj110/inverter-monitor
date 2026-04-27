import Foundation
import Combine

@MainActor
final class ReportsViewModel: ObservableObject {
    enum Tab: String, CaseIterable, Identifiable {
        case day, month, year, outages, raw
        var id: String { rawValue }
        var title: String {
            switch self {
            case .day: return "Day"
            case .month: return "Month"
            case .year: return "Year"
            case .outages: return "Outages"
            case .raw: return "Raw"
            }
        }
    }

    enum LoadPhase: Equatable {
        case idle
        case loading
        case loaded
        case empty
        case error(String)
    }

    // Day
    @Published var dayDate: Date = Date()
    @Published private(set) var daySummary: DailySummary = .placeholder
    @Published private(set) var dayReadings: DayReadings = .empty
    @Published private(set) var dayPhase: LoadPhase = .idle

    // Month
    @Published var monthDate: Date = Date()
    @Published private(set) var monthStats: MonthlyStats = .placeholder
    @Published private(set) var monthHistory: [HistoryRow] = []
    @Published private(set) var monthPhase: LoadPhase = .idle

    // Year
    @Published var yearValue: Int = Calendar.current.component(.year, from: Date())
    @Published private(set) var yearStats: YearlyStats = .placeholder
    @Published private(set) var monthlyTotals: [MonthlyTotal] = []
    @Published private(set) var yearPhase: LoadPhase = .idle

    // Outages
    @Published var outagesFrom: Date = Calendar.current.date(byAdding: .day, value: -6, to: Date()) ?? Date()
    @Published var outagesTo: Date = Date()
    @Published private(set) var outages: OutagesResponse = .empty
    @Published private(set) var outagesPhase: LoadPhase = .idle

    // Raw
    @Published var rawPage: Int = 1
    @Published var rawPageSize: Int = 25
    @Published private(set) var rawReadings: RawReadingsPage = .empty
    @Published private(set) var rawPhase: LoadPhase = .idle

    // Cross-tab: exports
    @Published var exportProgress: String?
    @Published var exportError: String?

    private let inverter: InverterService
    private var historyCache: [HistoryRow] = []

    /// Fires when any Reports request returns `APIError.notAuthenticated`. Wired by
    /// the App to trigger a full sign-out + redirect to LoginView — otherwise the
    /// user is stuck looking at "Not signed in" error banners on the active tab.
    var onSessionExpired: (() -> Void)?

    init(inverter: InverterService) { self.inverter = inverter }

    /// Unified error handling that distinguishes session-expired from other failures.
    private func handleLoadError(_ error: Error) -> String {
        if case APIError.notAuthenticated = error {
            onSessionExpired?()
            return "Session expired. Please sign in again."
        }
        if let apiErr = error as? APIError, let msg = apiErr.errorDescription {
            return msg
        }
        return error.localizedDescription
    }

    struct MonthlyTotal: Identifiable {
        var month: Int // 1-12
        var solar: Double
        var grid: Double
        var load: Double
        var battery: Double

        var id: Int { month }
    }

    // MARK: - Day -------------------------------------------------------------

    func loadDay(date: Date? = nil) async {
        if let date { dayDate = date }
        let iso = Self.isoDate(dayDate)
        dayPhase = .loading
        do {
            async let summary = inverter.summary(date: iso)
            async let readings = inverter.dayReadings(date: iso, bucket: 60)
            daySummary = try await summary
            dayReadings = try await readings
            dayPhase = dayReadings.points.isEmpty ? .empty : .loaded
        } catch {
            dayPhase = .error(handleLoadError(error))
        }
    }

    func shiftDay(by days: Int) async {
        if let next = Calendar.current.date(byAdding: .day, value: days, to: dayDate) {
            dayDate = next
            await loadDay()
        }
    }

    func jumpToToday() async {
        dayDate = Date()
        await loadDay()
    }

    // MARK: - Month -----------------------------------------------------------

    func loadMonth(date: Date? = nil) async {
        if let date { monthDate = date }
        let monthStr = Self.monthString(monthDate)
        monthPhase = .loading
        do {
            async let stats = inverter.monthlyStats(month: monthStr)
            async let history = historyOrFetch(days: 365)
            monthStats = try await stats
            monthHistory = try await history.filter { $0.date.hasPrefix(monthStr) }
            monthPhase = monthHistory.isEmpty ? .empty : .loaded
        } catch {
            monthPhase = .error(handleLoadError(error))
        }
    }

    // MARK: - Year ------------------------------------------------------------

    func loadYear(year: Int? = nil) async {
        if let year { yearValue = year }
        yearPhase = .loading
        do {
            async let stats = inverter.yearlyStats(year: String(yearValue))
            async let history = historyOrFetch(days: 365)
            yearStats = try await stats
            let yearRows = try await history.filter { $0.date.hasPrefix(String(yearValue)) }
            var totals = (1...12).map { MonthlyTotal(month: $0, solar: 0, grid: 0, load: 0, battery: 0) }
            for row in yearRows {
                let parts = row.date.split(separator: "-")
                guard parts.count >= 2, let m = Int(parts[1]) else { continue }
                totals[m - 1].solar += row.solarKwh
                totals[m - 1].grid += row.gridKwh
                totals[m - 1].load += row.loadKwh
                totals[m - 1].battery += row.batteryChargeKwh
            }
            self.monthlyTotals = totals
            yearPhase = yearRows.isEmpty ? .empty : .loaded
        } catch {
            yearPhase = .error(handleLoadError(error))
        }
    }

    // MARK: - Outages ---------------------------------------------------------

    func loadOutages() async {
        outagesPhase = .loading
        do {
            outages = try await inverter.outages(
                from: Self.isoDate(outagesFrom),
                to: Self.isoDate(outagesTo)
            )
            outagesPhase = outages.outages.isEmpty ? .empty : .loaded
        } catch {
            outagesPhase = .error(handleLoadError(error))
        }
    }

    func applyOutagePreset(days: Int) async {
        outagesTo = Date()
        if let start = Calendar.current.date(byAdding: .day, value: -(days - 1), to: Date()) {
            outagesFrom = start
        }
        await loadOutages()
    }

    // MARK: - Raw -------------------------------------------------------------

    func loadRaw() async {
        rawPhase = .loading
        do {
            rawReadings = try await inverter.rawReadings(page: rawPage, pageSize: rawPageSize)
            rawPhase = rawReadings.data.isEmpty ? .empty : .loaded
        } catch {
            rawPhase = .error(handleLoadError(error))
        }
    }

    func goToPage(_ page: Int) async {
        let maxPage = max(1, rawReadings.totalPages)
        rawPage = max(1, min(page, maxPage))
        await loadRaw()
    }

    // MARK: - Export ---------------------------------------------------------

    struct ExportResult {
        var data: Data
        var filename: String
        var mime: String
    }

    func exportDay(format: InverterService.ExportFormat, bucketSeconds: Int?) async -> ExportResult? {
        exportError = nil
        exportProgress = "Exporting…"
        defer { exportProgress = nil }
        let iso = Self.isoDate(dayDate)
        do {
            let (data, filename) = try await inverter.exportReadings(from: iso, to: iso, format: format, bucket: bucketSeconds)
            return ExportResult(
                data: data,
                filename: filename,
                mime: format == .csv ? "text/csv" : "application/json"
            )
        } catch {
            exportError = handleLoadError(error)
            return nil
        }
    }

    // MARK: - Helpers --------------------------------------------------------

    static func isoDate(_ date: Date) -> String {
        let fmt = DateFormatter()
        fmt.calendar = Calendar(identifier: .gregorian)
        fmt.locale = Locale(identifier: "en_US_POSIX")
        fmt.timeZone = TimeZone.current
        fmt.dateFormat = "yyyy-MM-dd"
        return fmt.string(from: date)
    }

    static func monthString(_ date: Date) -> String {
        let fmt = DateFormatter()
        fmt.calendar = Calendar(identifier: .gregorian)
        fmt.locale = Locale(identifier: "en_US_POSIX")
        fmt.timeZone = TimeZone.current
        fmt.dateFormat = "yyyy-MM"
        return fmt.string(from: date)
    }

    private func historyOrFetch(days: Int) async throws -> [HistoryRow] {
        if !historyCache.isEmpty { return historyCache }
        let rows = try await inverter.history(days: days)
        self.historyCache = rows
        return rows
    }

    func invalidateHistoryCache() {
        historyCache = []
    }
}
