import Foundation

struct InverterMetrics: Decodable, Equatable {
    var grid: GridMetrics
    var solar: SolarMetrics
    var battery: BatteryMetrics
    var load: LoadMetrics

    static let empty = InverterMetrics(
        grid: .empty,
        solar: .empty,
        battery: .empty,
        load: .empty
    )
}

struct GridMetrics: Decodable, Equatable {
    var voltage: Double
    var frequency: Double
    var power: Double
    var inUse: Bool
    var estimated: Bool

    private enum CodingKeys: String, CodingKey {
        case voltage, frequency, power
        case inUse = "in_use"
        case estimated
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        voltage = (try? c.decode(Double.self, forKey: .voltage)) ?? 0
        frequency = (try? c.decode(Double.self, forKey: .frequency)) ?? 0
        power = (try? c.decode(Double.self, forKey: .power)) ?? 0
        inUse = (try? c.decode(Bool.self, forKey: .inUse)) ?? false
        estimated = (try? c.decode(Bool.self, forKey: .estimated)) ?? true
    }

    init(voltage: Double, frequency: Double, power: Double, inUse: Bool, estimated: Bool) {
        self.voltage = voltage
        self.frequency = frequency
        self.power = power
        self.inUse = inUse
        self.estimated = estimated
    }

    static let empty = GridMetrics(voltage: 0, frequency: 0, power: 0, inUse: false, estimated: true)
}

struct SolarMetrics: Decodable, Equatable {
    var voltage: Double
    var current: Double
    var pvToBatteryCurrent: Double
    var power: Double

    private enum CodingKeys: String, CodingKey {
        case voltage, current, power
        case pvToBatteryCurrent = "pv_to_battery_current"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        voltage = (try? c.decode(Double.self, forKey: .voltage)) ?? 0
        current = (try? c.decode(Double.self, forKey: .current)) ?? 0
        pvToBatteryCurrent = (try? c.decode(Double.self, forKey: .pvToBatteryCurrent)) ?? 0
        power = (try? c.decode(Double.self, forKey: .power)) ?? 0
    }

    init(voltage: Double, current: Double, pvToBatteryCurrent: Double, power: Double) {
        self.voltage = voltage
        self.current = current
        self.pvToBatteryCurrent = pvToBatteryCurrent
        self.power = power
    }

    static let empty = SolarMetrics(voltage: 0, current: 0, pvToBatteryCurrent: 0, power: 0)
}

enum BatteryDirection: String, Decodable, Equatable {
    case charging, discharging, idle

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = BatteryDirection(rawValue: raw.lowercased()) ?? .idle
    }

    var label: String {
        switch self {
        case .charging: return "Charging"
        case .discharging: return "Discharging"
        case .idle: return "Idle"
        }
    }
}

struct BatteryMetrics: Decodable, Equatable {
    var voltage: Double
    var current: Double
    var chargingCurrent: Double
    var dischargeCurrent: Double
    var percentage: Double
    var power: Double
    var direction: BatteryDirection

    private enum CodingKeys: String, CodingKey {
        case voltage, current, percentage, power, direction
        case chargingCurrent = "charging_current"
        case dischargeCurrent = "discharge_current"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        voltage = (try? c.decode(Double.self, forKey: .voltage)) ?? 0
        current = (try? c.decode(Double.self, forKey: .current)) ?? 0
        chargingCurrent = (try? c.decode(Double.self, forKey: .chargingCurrent)) ?? 0
        dischargeCurrent = (try? c.decode(Double.self, forKey: .dischargeCurrent)) ?? 0
        percentage = (try? c.decode(Double.self, forKey: .percentage)) ?? 0
        power = (try? c.decode(Double.self, forKey: .power)) ?? 0
        direction = (try? c.decode(BatteryDirection.self, forKey: .direction)) ?? .idle
    }

    init(voltage: Double, current: Double, chargingCurrent: Double, dischargeCurrent: Double,
         percentage: Double, power: Double, direction: BatteryDirection) {
        self.voltage = voltage
        self.current = current
        self.chargingCurrent = chargingCurrent
        self.dischargeCurrent = dischargeCurrent
        self.percentage = percentage
        self.power = power
        self.direction = direction
    }

    static let empty = BatteryMetrics(
        voltage: 0, current: 0, chargingCurrent: 0, dischargeCurrent: 0,
        percentage: 0, power: 0, direction: .idle
    )
}

struct LoadMetrics: Decodable, Equatable {
    var voltage: Double
    var frequency: Double
    var current: Double
    var activePower: Double
    var apparentPower: Double
    var powerFactor: Double
    var power: Double
    var percentage: Double

    private enum CodingKeys: String, CodingKey {
        case voltage, frequency, current, power, percentage
        case activePower = "active_power"
        case apparentPower = "apparent_power"
        case powerFactor = "power_factor"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        voltage = (try? c.decode(Double.self, forKey: .voltage)) ?? 0
        frequency = (try? c.decode(Double.self, forKey: .frequency)) ?? 0
        current = (try? c.decode(Double.self, forKey: .current)) ?? 0
        activePower = (try? c.decode(Double.self, forKey: .activePower)) ?? 0
        apparentPower = (try? c.decode(Double.self, forKey: .apparentPower)) ?? 0
        powerFactor = (try? c.decode(Double.self, forKey: .powerFactor)) ?? 0
        power = (try? c.decode(Double.self, forKey: .power)) ?? activePower
        percentage = (try? c.decode(Double.self, forKey: .percentage)) ?? 0
    }

    init(voltage: Double, frequency: Double, current: Double, activePower: Double,
         apparentPower: Double, powerFactor: Double, power: Double, percentage: Double) {
        self.voltage = voltage
        self.frequency = frequency
        self.current = current
        self.activePower = activePower
        self.apparentPower = apparentPower
        self.powerFactor = powerFactor
        self.power = power
        self.percentage = percentage
    }

    var effectivePower: Double { activePower != 0 ? activePower : power }

    static let empty = LoadMetrics(
        voltage: 0, frequency: 0, current: 0, activePower: 0,
        apparentPower: 0, powerFactor: 0, power: 0, percentage: 0
    )
}
