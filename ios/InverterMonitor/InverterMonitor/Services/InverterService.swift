import Foundation

final class InverterService {
    private let api: APIClient

    init(api: APIClient) { self.api = api }

    // MARK: - Live status -----------------------------------------------------

    func status() async throws -> InverterStatus {
        try await api.getJSON("/status", as: InverterStatus.self)
    }

    func allStats() async throws -> AllStats {
        try await api.getJSON("/stats", query: ["period": "all"], as: AllStats.self)
    }

    // MARK: - History & summaries --------------------------------------------

    func summary(date: String? = nil) async throws -> DailySummary {
        try await api.getJSON("/summary", query: ["date": date], as: DailySummary.self)
    }

    func monthlyStats(month: String? = nil) async throws -> MonthlyStats {
        try await api.getJSON("/stats", query: ["period": "month", "month": month], as: MonthlyStats.self)
    }

    func yearlyStats(year: String? = nil) async throws -> YearlyStats {
        try await api.getJSON("/stats", query: ["period": "year", "year": year], as: YearlyStats.self)
    }

    func history(days: Int = 30) async throws -> [HistoryRow] {
        try await api.getJSON("/history", query: ["days": String(days)], as: [HistoryRow].self)
    }

    func recentReadings(minutes: Int = 30, bucketSeconds: Int? = nil) async throws -> RecentReadings {
        var q: [String: String?] = ["minutes": String(minutes)]
        if let bucketSeconds { q["bucket"] = String(bucketSeconds) }
        return try await api.getJSON("/recent-readings", query: q, as: RecentReadings.self)
    }

    func dayReadings(date: String? = nil, bucket: Int = 60) async throws -> DayReadings {
        try await api.getJSON("/day-readings",
                              query: ["date": date, "bucket": String(bucket)],
                              as: DayReadings.self)
    }

    func outages(from: String?, to: String?) async throws -> OutagesResponse {
        try await api.getJSON("/outages", query: ["from": from, "to": to], as: OutagesResponse.self)
    }

    func rawReadings(page: Int, pageSize: Int) async throws -> RawReadingsPage {
        try await api.getJSON("/raw-data",
                              query: ["page": String(page), "page_size": String(pageSize)],
                              as: RawReadingsPage.self)
    }

    // MARK: - Config ----------------------------------------------------------

    func config() async throws -> ConfigEnvelope {
        try await api.getJSON("/config", as: ConfigEnvelope.self)
    }

    // MARK: - Exports ---------------------------------------------------------

    enum ExportFormat: String { case csv, json }

    /// Downloads an export and returns both the raw bytes and the suggested filename.
    func exportReadings(from: String, to: String, format: ExportFormat, bucket: Int?) async throws -> (Data, String) {
        var query: [String: String?] = [
            "from": from, "to": to, "format": format.rawValue
        ]
        if let bucket { query["bucket"] = String(bucket) }
        let (data, response) = try await api.getRaw("/export-readings", query: query)
        guard (200..<400).contains(response.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw APIError.server(code: response.statusCode, body: String(body.prefix(240)))
        }
        let filename = response.suggestedFilename(forDefault: "inverter_\(from)_to_\(to).\(format.rawValue)")
        return (data, filename)
    }
}

private extension HTTPURLResponse {
    func suggestedFilename(forDefault fallback: String) -> String {
        if let disposition = value(forHTTPHeaderField: "Content-Disposition"),
           let range = disposition.range(of: "filename=") {
            let start = disposition.index(range.upperBound, offsetBy: 0)
            let raw = String(disposition[start...])
                .trimmingCharacters(in: CharacterSet(charactersIn: "\" ;"))
            if !raw.isEmpty { return raw }
        }
        return fallback
    }
}
