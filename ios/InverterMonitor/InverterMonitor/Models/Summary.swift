import Foundation

/// `GET /summary?date=YYYY-MM-DD` — energy totals + derived ratios for one day.
struct DailySummary: Decodable, Equatable {
    var date: String?
    var solarKwh: Double
    var gridKwh: Double
    var loadKwh: Double
    var batteryChargeKwh: Double
    var batteryDischargeKwh: Double
    var solarPeakW: Double
    var loadPeakW: Double
    var gridPeakW: Double
    var pfAvg: Double
    var temperatureMax: Double
    var selfSufficiency: Double
    var solarFraction: Double

    private enum CodingKeys: String, CodingKey {
        case date
        case solarKwh = "solar_kwh"
        case gridKwh = "grid_kwh"
        case loadKwh = "load_kwh"
        case batteryChargeKwh = "battery_charge_kwh"
        case batteryDischargeKwh = "battery_discharge_kwh"
        case solarPeakW = "solar_peak_w"
        case loadPeakW = "load_peak_w"
        case gridPeakW = "grid_peak_w"
        case pfAvg = "pf_avg"
        case temperatureMax = "temperature_max"
        case selfSufficiency = "self_sufficiency"
        case solarFraction = "solar_fraction"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        date = try? c.decode(String.self, forKey: .date)
        solarKwh = (try? c.decode(Double.self, forKey: .solarKwh)) ?? 0
        gridKwh = (try? c.decode(Double.self, forKey: .gridKwh)) ?? 0
        loadKwh = (try? c.decode(Double.self, forKey: .loadKwh)) ?? 0
        batteryChargeKwh = (try? c.decode(Double.self, forKey: .batteryChargeKwh)) ?? 0
        batteryDischargeKwh = (try? c.decode(Double.self, forKey: .batteryDischargeKwh)) ?? 0
        solarPeakW = (try? c.decode(Double.self, forKey: .solarPeakW)) ?? 0
        loadPeakW = (try? c.decode(Double.self, forKey: .loadPeakW)) ?? 0
        gridPeakW = (try? c.decode(Double.self, forKey: .gridPeakW)) ?? 0
        pfAvg = (try? c.decode(Double.self, forKey: .pfAvg)) ?? 0
        temperatureMax = (try? c.decode(Double.self, forKey: .temperatureMax)) ?? 0
        selfSufficiency = (try? c.decode(Double.self, forKey: .selfSufficiency)) ?? 0
        solarFraction = (try? c.decode(Double.self, forKey: .solarFraction)) ?? 0
    }

    init(
        date: String?, solarKwh: Double, gridKwh: Double, loadKwh: Double,
        batteryChargeKwh: Double, batteryDischargeKwh: Double,
        solarPeakW: Double, loadPeakW: Double, gridPeakW: Double,
        pfAvg: Double, temperatureMax: Double,
        selfSufficiency: Double, solarFraction: Double
    ) {
        self.date = date
        self.solarKwh = solarKwh
        self.gridKwh = gridKwh
        self.loadKwh = loadKwh
        self.batteryChargeKwh = batteryChargeKwh
        self.batteryDischargeKwh = batteryDischargeKwh
        self.solarPeakW = solarPeakW
        self.loadPeakW = loadPeakW
        self.gridPeakW = gridPeakW
        self.pfAvg = pfAvg
        self.temperatureMax = temperatureMax
        self.selfSufficiency = selfSufficiency
        self.solarFraction = solarFraction
    }

    static let placeholder = DailySummary(
        date: nil,
        solarKwh: 0, gridKwh: 0, loadKwh: 0,
        batteryChargeKwh: 0, batteryDischargeKwh: 0,
        solarPeakW: 0, loadPeakW: 0, gridPeakW: 0,
        pfAvg: 0, temperatureMax: 0,
        selfSufficiency: 0, solarFraction: 0
    )
}

/// `GET /stats?period=month`
struct MonthlyStats: Decodable, Equatable {
    var month: String?
    var solarEnergyWh: Double
    var gridEnergyWh: Double
    var loadEnergyWh: Double
    var batteryChargeEnergyWh: Double
    var batteryDischargeEnergyWh: Double

    private enum CodingKeys: String, CodingKey {
        case month
        case solarEnergyWh = "solar_energy"
        case gridEnergyWh = "grid_energy"
        case loadEnergyWh = "load_energy"
        case batteryChargeEnergyWh = "battery_charge_energy"
        case batteryDischargeEnergyWh = "battery_discharge_energy"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        month = try? c.decode(String.self, forKey: .month)
        solarEnergyWh = (try? c.decode(Double.self, forKey: .solarEnergyWh)) ?? 0
        gridEnergyWh = (try? c.decode(Double.self, forKey: .gridEnergyWh)) ?? 0
        loadEnergyWh = (try? c.decode(Double.self, forKey: .loadEnergyWh)) ?? 0
        batteryChargeEnergyWh = (try? c.decode(Double.self, forKey: .batteryChargeEnergyWh)) ?? 0
        batteryDischargeEnergyWh = (try? c.decode(Double.self, forKey: .batteryDischargeEnergyWh)) ?? 0
    }

    init(month: String?, solarEnergyWh: Double, gridEnergyWh: Double, loadEnergyWh: Double,
         batteryChargeEnergyWh: Double, batteryDischargeEnergyWh: Double) {
        self.month = month
        self.solarEnergyWh = solarEnergyWh
        self.gridEnergyWh = gridEnergyWh
        self.loadEnergyWh = loadEnergyWh
        self.batteryChargeEnergyWh = batteryChargeEnergyWh
        self.batteryDischargeEnergyWh = batteryDischargeEnergyWh
    }

    static let placeholder = MonthlyStats(
        month: nil,
        solarEnergyWh: 0, gridEnergyWh: 0, loadEnergyWh: 0,
        batteryChargeEnergyWh: 0, batteryDischargeEnergyWh: 0
    )
}

/// `GET /stats?period=year`
struct YearlyStats: Decodable, Equatable {
    var year: String?
    var solarEnergyWh: Double
    var gridEnergyWh: Double
    var loadEnergyWh: Double
    var batteryChargeEnergyWh: Double
    var batteryDischargeEnergyWh: Double

    private enum CodingKeys: String, CodingKey {
        case year
        case solarEnergyWh = "solar_energy"
        case gridEnergyWh = "grid_energy"
        case loadEnergyWh = "load_energy"
        case batteryChargeEnergyWh = "battery_charge_energy"
        case batteryDischargeEnergyWh = "battery_discharge_energy"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        year = try? c.decode(String.self, forKey: .year)
        solarEnergyWh = (try? c.decode(Double.self, forKey: .solarEnergyWh)) ?? 0
        gridEnergyWh = (try? c.decode(Double.self, forKey: .gridEnergyWh)) ?? 0
        loadEnergyWh = (try? c.decode(Double.self, forKey: .loadEnergyWh)) ?? 0
        batteryChargeEnergyWh = (try? c.decode(Double.self, forKey: .batteryChargeEnergyWh)) ?? 0
        batteryDischargeEnergyWh = (try? c.decode(Double.self, forKey: .batteryDischargeEnergyWh)) ?? 0
    }

    init(year: String?, solarEnergyWh: Double, gridEnergyWh: Double, loadEnergyWh: Double,
         batteryChargeEnergyWh: Double, batteryDischargeEnergyWh: Double) {
        self.year = year
        self.solarEnergyWh = solarEnergyWh
        self.gridEnergyWh = gridEnergyWh
        self.loadEnergyWh = loadEnergyWh
        self.batteryChargeEnergyWh = batteryChargeEnergyWh
        self.batteryDischargeEnergyWh = batteryDischargeEnergyWh
    }

    static let placeholder = YearlyStats(
        year: nil,
        solarEnergyWh: 0, gridEnergyWh: 0, loadEnergyWh: 0,
        batteryChargeEnergyWh: 0, batteryDischargeEnergyWh: 0
    )
}

/// One row in `GET /history?days=N` (values already in kWh).
struct HistoryRow: Decodable, Identifiable, Equatable {
    var date: String
    var solarKwh: Double
    var gridKwh: Double
    var loadKwh: Double
    var batteryChargeKwh: Double
    var batteryDischargeKwh: Double

    var id: String { date }

    private enum CodingKeys: String, CodingKey {
        case date
        case solarKwh = "solar_energy"
        case gridKwh = "grid_energy"
        case loadKwh = "load_energy"
        case batteryChargeKwh = "battery_charge_energy"
        case batteryDischargeKwh = "battery_discharge_energy"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        date = (try? c.decode(String.self, forKey: .date)) ?? ""
        solarKwh = (try? c.decode(Double.self, forKey: .solarKwh)) ?? 0
        gridKwh = (try? c.decode(Double.self, forKey: .gridKwh)) ?? 0
        loadKwh = (try? c.decode(Double.self, forKey: .loadKwh)) ?? 0
        batteryChargeKwh = (try? c.decode(Double.self, forKey: .batteryChargeKwh)) ?? 0
        batteryDischargeKwh = (try? c.decode(Double.self, forKey: .batteryDischargeKwh)) ?? 0
    }
}

/// `GET /stats` (period=all) used for the WebSocket `stats_update` equivalent.
/// Reading stats are merged into the same object by the backend.
struct AllStats: Decodable, Equatable {
    var day: DailySummary?
    var month: MonthlyStats?
    var year: YearlyStats?
    var summary: DailySummary?
    var readingStats: ReadingStats?
    var config: InverterConfig?
    var system: SystemInfo?

    private enum CodingKeys: String, CodingKey {
        case day, month, year, summary, system, config
        case readingStats = "reading_stats"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        // /stats returns day as a flat row; we accept either the flat form or the richer summary.
        day = try? c.decode(DailySummary.self, forKey: .day)
        month = try? c.decode(MonthlyStats.self, forKey: .month)
        year = try? c.decode(YearlyStats.self, forKey: .year)
        summary = try? c.decode(DailySummary.self, forKey: .summary)
        readingStats = try? c.decode(ReadingStats.self, forKey: .readingStats)
        config = try? c.decode(InverterConfig.self, forKey: .config)
        system = try? c.decode(SystemInfo.self, forKey: .system)
    }
}

struct ReadingStats: Decodable, Equatable {
    var avgDuration: Double
    var minDuration: Double
    var maxDuration: Double
    var totalReadings: Int
    var totalDuration: Double
    var errorCount: Int?
    var errorRate: Double?
    var running: Bool?
    var lastReadingTime: Double?

    private enum CodingKeys: String, CodingKey {
        case avgDuration = "avg_duration"
        case minDuration = "min_duration"
        case maxDuration = "max_duration"
        case totalReadings = "total_readings"
        case totalDuration = "total_duration"
        case errorCount = "error_count"
        case errorRate = "error_rate"
        case running
        case lastReadingTime = "last_reading_time"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        avgDuration = (try? c.decode(Double.self, forKey: .avgDuration)) ?? 0
        minDuration = (try? c.decode(Double.self, forKey: .minDuration)) ?? 0
        maxDuration = (try? c.decode(Double.self, forKey: .maxDuration)) ?? 0
        totalReadings = (try? c.decode(Int.self, forKey: .totalReadings)) ?? 0
        totalDuration = (try? c.decode(Double.self, forKey: .totalDuration)) ?? 0
        errorCount = try? c.decode(Int.self, forKey: .errorCount)
        errorRate = try? c.decode(Double.self, forKey: .errorRate)
        running = try? c.decode(Bool.self, forKey: .running)
        lastReadingTime = try? c.decode(Double.self, forKey: .lastReadingTime)
    }
}
