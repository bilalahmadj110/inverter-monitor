import Foundation

final class CommandService {
    private let api: APIClient

    /// Fired after a successful /recompute-daily so caches tied to daily_stats can invalidate.
    var onDidRecompute: (() -> Void)?

    init(api: APIClient) { self.api = api }

    /// Generous timeout for any call that funnels through the PI30 USB layer. The server
    /// retries QMOD/QPIWS/QPIRI/POP/PCP up to 3-5 times with backoff, so a worst-case
    /// round trip can approach 60-90s.
    private let inverterTimeout: TimeInterval = 90

    /// POST /refresh-extras → forces the inverter to re-query mode/warnings/config.
    /// Server sends QMOD + QPIWS + QPIRI serialized behind a single USB lock, with
    /// a 2-second debounce protecting against concurrent clients.
    @discardableResult
    func refreshExtras() async throws -> RefreshExtrasResponse {
        try await api.postJSON("/refresh-extras",
                               timeout: inverterTimeout,
                               as: RefreshExtrasResponse.self)
    }

    /// POST /set-output-priority { mode }. Server also runs QPIRI immediately after and
    /// returns the fresh config in the response, so callers don't need to refresh again.
    @discardableResult
    func setOutputPriority(_ mode: OutputPriority) async throws -> PriorityChangeResponse {
        let result: PriorityChangeResponse = try await api.postJSON(
            "/set-output-priority",
            body: ["mode": mode.rawValue],
            timeout: inverterTimeout,
            as: PriorityChangeResponse.self
        )
        if let err = result.error, !result.success {
            throw APIError.server(code: 400, body: err)
        }
        return result
    }

    /// POST /set-charger-priority { mode }
    @discardableResult
    func setChargerPriority(_ mode: ChargerPriority) async throws -> PriorityChangeResponse {
        let result: PriorityChangeResponse = try await api.postJSON(
            "/set-charger-priority",
            body: ["mode": mode.rawValue],
            timeout: inverterTimeout,
            as: PriorityChangeResponse.self
        )
        if let err = result.error, !result.success {
            throw APIError.server(code: 400, body: err)
        }
        return result
    }

    struct RecomputeResponse: Decodable, Equatable {
        var count: Int
        var updated: [Updated]
        var error: String?

        struct Updated: Decodable, Equatable, Identifiable {
            var date: String
            var solarWh: Double
            var gridWh: Double
            var loadWh: Double

            var id: String { date }

            private enum CodingKeys: String, CodingKey {
                case date
                case solarWh = "solar_wh"
                case gridWh = "grid_wh"
                case loadWh = "load_wh"
            }

            init(from decoder: Decoder) throws {
                let c = try decoder.container(keyedBy: CodingKeys.self)
                date = (try? c.decode(String.self, forKey: .date)) ?? ""
                solarWh = (try? c.decode(Double.self, forKey: .solarWh)) ?? 0
                gridWh = (try? c.decode(Double.self, forKey: .gridWh)) ?? 0
                loadWh = (try? c.decode(Double.self, forKey: .loadWh)) ?? 0
            }
        }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            count = (try? c.decode(Int.self, forKey: .count)) ?? 0
            updated = (try? c.decode([Updated].self, forKey: .updated)) ?? []
            error = try? c.decode(String.self, forKey: .error)
        }

        private enum CodingKeys: String, CodingKey {
            case count, updated, error
        }
    }

    @discardableResult
    func recomputeDaily(day: String? = nil) async throws -> RecomputeResponse {
        let result: RecomputeResponse = try await api.postJSON(
            "/recompute-daily",
            query: ["day": day],
            as: RecomputeResponse.self
        )
        if result.error == nil {
            onDidRecompute?()
        }
        return result
    }
}
