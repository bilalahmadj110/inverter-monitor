import Foundation

/// `GET /recent-readings` - avg/min/max per bucket.
struct RecentReadings: Decodable, Equatable {
    var minutes: Int
    var bucketSeconds: Int
    var points: [RecentReadingPoint]

    private enum CodingKeys: String, CodingKey {
        case minutes, points
        case bucketSeconds = "bucket_seconds"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        minutes = (try? c.decode(Int.self, forKey: .minutes)) ?? 0
        bucketSeconds = (try? c.decode(Int.self, forKey: .bucketSeconds)) ?? 0
        points = (try? c.decode([RecentReadingPoint].self, forKey: .points)) ?? []
    }

    init(minutes: Int, bucketSeconds: Int, points: [RecentReadingPoint]) {
        self.minutes = minutes
        self.bucketSeconds = bucketSeconds
        self.points = points
    }

    static let empty = RecentReadings(minutes: 30, bucketSeconds: 0, points: [])
}

struct RecentReadingPoint: Decodable, Equatable, Identifiable {
    var timestamp: TimeInterval
    var solarAvg: Double
    var solarMin: Double
    var solarMax: Double
    var gridAvg: Double
    var gridMin: Double
    var gridMax: Double
    var loadAvg: Double
    var loadMin: Double
    var loadMax: Double
    var batteryAvg: Double
    var batteryMin: Double
    var batteryMax: Double
    var batteryPercentage: Double
    var gridVoltage: Double

    var id: TimeInterval { timestamp }
    var date: Date { Date(timeIntervalSince1970: timestamp) }

    private enum CodingKeys: String, CodingKey {
        case timestamp
        case solarAvg = "solar_avg", solarMin = "solar_min", solarMax = "solar_max"
        case gridAvg = "grid_avg", gridMin = "grid_min", gridMax = "grid_max"
        case loadAvg = "load_avg", loadMin = "load_min", loadMax = "load_max"
        case batteryAvg = "battery_avg", batteryMin = "battery_min", batteryMax = "battery_max"
        case batteryPercentage = "battery_percentage"
        case gridVoltage = "grid_voltage"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        timestamp = (try? c.decode(Double.self, forKey: .timestamp)) ?? 0
        solarAvg = (try? c.decode(Double.self, forKey: .solarAvg)) ?? 0
        solarMin = (try? c.decode(Double.self, forKey: .solarMin)) ?? 0
        solarMax = (try? c.decode(Double.self, forKey: .solarMax)) ?? 0
        gridAvg = (try? c.decode(Double.self, forKey: .gridAvg)) ?? 0
        gridMin = (try? c.decode(Double.self, forKey: .gridMin)) ?? 0
        gridMax = (try? c.decode(Double.self, forKey: .gridMax)) ?? 0
        loadAvg = (try? c.decode(Double.self, forKey: .loadAvg)) ?? 0
        loadMin = (try? c.decode(Double.self, forKey: .loadMin)) ?? 0
        loadMax = (try? c.decode(Double.self, forKey: .loadMax)) ?? 0
        batteryAvg = (try? c.decode(Double.self, forKey: .batteryAvg)) ?? 0
        batteryMin = (try? c.decode(Double.self, forKey: .batteryMin)) ?? 0
        batteryMax = (try? c.decode(Double.self, forKey: .batteryMax)) ?? 0
        batteryPercentage = (try? c.decode(Double.self, forKey: .batteryPercentage)) ?? 0
        gridVoltage = (try? c.decode(Double.self, forKey: .gridVoltage)) ?? 0
    }
}

/// `GET /day-readings`
struct DayReadings: Decodable, Equatable {
    var date: String?
    var bucketSeconds: Int
    var points: [DayReadingPoint]

    private enum CodingKeys: String, CodingKey {
        case date, points
        case bucketSeconds = "bucket_seconds"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        date = try? c.decode(String.self, forKey: .date)
        bucketSeconds = (try? c.decode(Int.self, forKey: .bucketSeconds)) ?? 60
        points = (try? c.decode([DayReadingPoint].self, forKey: .points)) ?? []
    }

    init(date: String?, bucketSeconds: Int, points: [DayReadingPoint]) {
        self.date = date
        self.bucketSeconds = bucketSeconds
        self.points = points
    }

    static let empty = DayReadings(date: nil, bucketSeconds: 60, points: [])
}

struct DayReadingPoint: Decodable, Equatable, Identifiable {
    var timestamp: TimeInterval
    var solarPower: Double
    var gridPower: Double
    var loadPower: Double
    var batteryPower: Double
    var batteryPercentage: Double
    var gridVoltage: Double

    var id: TimeInterval { timestamp }
    var date: Date { Date(timeIntervalSince1970: timestamp) }

    private enum CodingKeys: String, CodingKey {
        case timestamp
        case solarPower = "solar_power"
        case gridPower = "grid_power"
        case loadPower = "load_power"
        case batteryPower = "battery_power"
        case batteryPercentage = "battery_percentage"
        case gridVoltage = "grid_voltage"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        timestamp = (try? c.decode(Double.self, forKey: .timestamp)) ?? 0
        solarPower = (try? c.decode(Double.self, forKey: .solarPower)) ?? 0
        gridPower = (try? c.decode(Double.self, forKey: .gridPower)) ?? 0
        loadPower = (try? c.decode(Double.self, forKey: .loadPower)) ?? 0
        batteryPower = (try? c.decode(Double.self, forKey: .batteryPower)) ?? 0
        batteryPercentage = (try? c.decode(Double.self, forKey: .batteryPercentage)) ?? 0
        gridVoltage = (try? c.decode(Double.self, forKey: .gridVoltage)) ?? 0
    }
}

/// `GET /outages`
struct OutagesResponse: Decodable, Equatable {
    var from: String?
    var to: String?
    var outages: [Outage]
    var count: Int
    var totalDownSeconds: Int
    var availability: Double

    private enum CodingKeys: String, CodingKey {
        case from, to, outages, count, availability
        case totalDownSeconds = "total_down_seconds"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        from = try? c.decode(String.self, forKey: .from)
        to = try? c.decode(String.self, forKey: .to)
        outages = (try? c.decode([Outage].self, forKey: .outages)) ?? []
        count = (try? c.decode(Int.self, forKey: .count)) ?? 0
        totalDownSeconds = (try? c.decode(Int.self, forKey: .totalDownSeconds)) ?? 0
        availability = (try? c.decode(Double.self, forKey: .availability)) ?? 1.0
    }

    init(from: String?, to: String?, outages: [Outage], count: Int, totalDownSeconds: Int, availability: Double) {
        self.from = from
        self.to = to
        self.outages = outages
        self.count = count
        self.totalDownSeconds = totalDownSeconds
        self.availability = availability
    }

    static let empty = OutagesResponse(
        from: nil, to: nil, outages: [], count: 0, totalDownSeconds: 0, availability: 1.0
    )
}

struct Outage: Decodable, Equatable, Identifiable {
    var start: TimeInterval
    var end: TimeInterval
    var durationSeconds: Int

    var id: TimeInterval { start }
    var startDate: Date { Date(timeIntervalSince1970: start) }
    var endDate: Date { Date(timeIntervalSince1970: end) }

    private enum CodingKeys: String, CodingKey {
        case start, end
        case durationSeconds = "duration_seconds"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        start = (try? c.decode(Double.self, forKey: .start)) ?? 0
        end = (try? c.decode(Double.self, forKey: .end)) ?? 0
        durationSeconds = (try? c.decode(Int.self, forKey: .durationSeconds)) ?? 0
    }
}

/// `GET /raw-data`
struct RawReadingsPage: Decodable, Equatable {
    var data: [RawReading]
    var totalCount: Int
    var page: Int
    var pageSize: Int
    var totalPages: Int

    private enum CodingKeys: String, CodingKey {
        case data
        case totalCount = "total_count"
        case page
        case pageSize = "page_size"
        case totalPages = "total_pages"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        data = (try? c.decode([RawReading].self, forKey: .data)) ?? []
        totalCount = (try? c.decode(Int.self, forKey: .totalCount)) ?? 0
        page = (try? c.decode(Int.self, forKey: .page)) ?? 1
        pageSize = (try? c.decode(Int.self, forKey: .pageSize)) ?? 25
        totalPages = (try? c.decode(Int.self, forKey: .totalPages)) ?? 0
    }

    init(data: [RawReading], totalCount: Int, page: Int, pageSize: Int, totalPages: Int) {
        self.data = data
        self.totalCount = totalCount
        self.page = page
        self.pageSize = pageSize
        self.totalPages = totalPages
    }

    static let empty = RawReadingsPage(data: [], totalCount: 0, page: 1, pageSize: 25, totalPages: 0)
}

struct RawReading: Decodable, Equatable, Identifiable {
    var timestamp: TimeInterval
    var timestampFormatted: String
    var solarPower: Double
    var gridPower: Double
    var gridVoltage: Double
    var batteryPercentage: Double
    var loadPower: Double
    var batteryPower: Double
    var temperature: Double
    var durationMs: Double

    var id: TimeInterval { timestamp }

    private enum CodingKeys: String, CodingKey {
        case timestamp
        case timestampFormatted = "timestamp_formatted"
        case solarPower = "solar_power"
        case gridPower = "grid_power"
        case gridVoltage = "grid_voltage"
        case batteryPercentage = "battery_percentage"
        case loadPower = "load_power"
        case batteryPower = "battery_power"
        case temperature
        case durationMs = "duration_ms"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        timestamp = (try? c.decode(Double.self, forKey: .timestamp)) ?? 0
        timestampFormatted = (try? c.decode(String.self, forKey: .timestampFormatted)) ?? ""
        solarPower = (try? c.decode(Double.self, forKey: .solarPower)) ?? 0
        gridPower = (try? c.decode(Double.self, forKey: .gridPower)) ?? 0
        gridVoltage = (try? c.decode(Double.self, forKey: .gridVoltage)) ?? 0
        batteryPercentage = (try? c.decode(Double.self, forKey: .batteryPercentage)) ?? 0
        loadPower = (try? c.decode(Double.self, forKey: .loadPower)) ?? 0
        batteryPower = (try? c.decode(Double.self, forKey: .batteryPower)) ?? 0
        temperature = (try? c.decode(Double.self, forKey: .temperature)) ?? 0
        durationMs = (try? c.decode(Double.self, forKey: .durationMs)) ?? 0
    }
}
