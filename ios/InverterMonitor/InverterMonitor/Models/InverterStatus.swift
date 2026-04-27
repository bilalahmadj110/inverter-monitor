import Foundation

/// Full payload from `GET /status` (and pushed live via polling).
struct InverterStatus: Decodable, Equatable {
    var success: Bool
    var metrics: InverterMetrics
    var system: SystemInfo
    var timing: ReadingTiming?
    var error: String?

    private enum CodingKeys: String, CodingKey {
        case success, metrics, system, timing, error
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        success = (try? c.decode(Bool.self, forKey: .success)) ?? false
        metrics = (try? c.decode(InverterMetrics.self, forKey: .metrics)) ?? .empty
        system = (try? c.decode(SystemInfo.self, forKey: .system)) ?? .empty
        timing = try? c.decode(ReadingTiming.self, forKey: .timing)
        error = try? c.decode(String.self, forKey: .error)
    }

    init(success: Bool, metrics: InverterMetrics, system: SystemInfo, timing: ReadingTiming?, error: String?) {
        self.success = success
        self.metrics = metrics
        self.system = system
        self.timing = timing
        self.error = error
    }

    static let placeholder = InverterStatus(
        success: false,
        metrics: .empty,
        system: .empty,
        timing: nil,
        error: nil
    )
}

struct ReadingTiming: Decodable, Equatable {
    var startTime: Double
    var endTime: Double
    var durationMs: Double

    private enum CodingKeys: String, CodingKey {
        case startTime = "start_time"
        case endTime = "end_time"
        case durationMs = "duration_ms"
    }
}
