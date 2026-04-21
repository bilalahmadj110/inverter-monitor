import Foundation

enum InverterMode: String, Equatable {
    case powerOn = "P"
    case standby = "S"
    case line = "L"
    case battery = "B"
    case fault = "F"
    case powerSaving = "H"
    case charging = "C"
    case shutdown = "D"

    static func from(raw: String?) -> InverterMode {
        guard let raw, let mode = InverterMode(rawValue: raw.uppercased()) else { return .standby }
        return mode
    }

    var defaultLabel: String {
        switch self {
        case .powerOn: return "Power On"
        case .standby: return "Standby"
        case .line: return "Line Mode"
        case .battery: return "Battery Mode"
        case .fault: return "Fault"
        case .powerSaving: return "Power Saving"
        case .charging: return "Charging"
        case .shutdown: return "Shutdown"
        }
    }
}

enum ChargeStage: String, Decodable, Equatable {
    case idle, bulk, absorption, float

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = ChargeStage(rawValue: raw.lowercased()) ?? .idle
    }

    var label: String {
        switch self {
        case .idle: return "Idle"
        case .bulk: return "Bulk Charging"
        case .absorption: return "Absorption"
        case .float: return "Float Charge"
        }
    }
}

enum WarningSeverity: String, Decodable, Equatable {
    case warning
    case fault

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = WarningSeverity(rawValue: raw.lowercased()) ?? .warning
    }
}

struct InverterWarning: Decodable, Equatable, Identifiable {
    var key: String
    var label: String
    var severity: WarningSeverity

    var id: String { key }

    init(key: String, label: String, severity: WarningSeverity) {
        self.key = key
        self.label = label
        self.severity = severity
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        key = (try? c.decode(String.self, forKey: .key)) ?? ""
        label = (try? c.decode(String.self, forKey: .label)) ?? key
        severity = (try? c.decode(WarningSeverity.self, forKey: .severity)) ?? .warning
    }

    private enum CodingKeys: String, CodingKey {
        case key, label, severity
    }
}

struct SystemInfo: Decodable, Equatable {
    var busVoltage: Double
    var temperature: Double
    var isLoadOn: Bool
    var isChargingOn: Bool
    var isSccChargingOn: Bool
    var isAcChargingOn: Bool
    var isSwitchedOn: Bool
    var isChargingToFloat: Bool
    var mode: InverterMode
    var modeLabel: String
    var modeSource: String
    var chargeStage: ChargeStage
    var warnings: [InverterWarning]
    var hasFault: Bool

    private enum CodingKeys: String, CodingKey {
        case busVoltage = "bus_voltage"
        case temperature
        case isLoadOn = "is_load_on"
        case isChargingOn = "is_charging_on"
        case isSccChargingOn = "is_scc_charging_on"
        case isAcChargingOn = "is_ac_charging_on"
        case isSwitchedOn = "is_switched_on"
        case isChargingToFloat = "is_charging_to_float"
        case mode
        case modeLabel = "mode_label"
        case modeSource = "mode_source"
        case chargeStage = "charge_stage"
        case warnings
        case hasFault = "has_fault"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        busVoltage = (try? c.decode(Double.self, forKey: .busVoltage)) ?? 0
        temperature = (try? c.decode(Double.self, forKey: .temperature)) ?? 0
        isLoadOn = (try? c.decode(Bool.self, forKey: .isLoadOn)) ?? false
        isChargingOn = (try? c.decode(Bool.self, forKey: .isChargingOn)) ?? false
        isSccChargingOn = (try? c.decode(Bool.self, forKey: .isSccChargingOn)) ?? false
        isAcChargingOn = (try? c.decode(Bool.self, forKey: .isAcChargingOn)) ?? false
        isSwitchedOn = (try? c.decode(Bool.self, forKey: .isSwitchedOn)) ?? false
        isChargingToFloat = (try? c.decode(Bool.self, forKey: .isChargingToFloat)) ?? false
        let rawMode = (try? c.decode(String.self, forKey: .mode)) ?? "S"
        mode = InverterMode.from(raw: rawMode)
        modeLabel = (try? c.decode(String.self, forKey: .modeLabel)) ?? mode.defaultLabel
        modeSource = (try? c.decode(String.self, forKey: .modeSource)) ?? "derived"
        chargeStage = (try? c.decode(ChargeStage.self, forKey: .chargeStage)) ?? .idle
        warnings = (try? c.decode([InverterWarning].self, forKey: .warnings)) ?? []
        hasFault = (try? c.decode(Bool.self, forKey: .hasFault)) ?? warnings.contains { $0.severity == .fault }
    }

    init(
        busVoltage: Double, temperature: Double,
        isLoadOn: Bool, isChargingOn: Bool, isSccChargingOn: Bool,
        isAcChargingOn: Bool, isSwitchedOn: Bool, isChargingToFloat: Bool,
        mode: InverterMode, modeLabel: String, modeSource: String,
        chargeStage: ChargeStage, warnings: [InverterWarning], hasFault: Bool
    ) {
        self.busVoltage = busVoltage
        self.temperature = temperature
        self.isLoadOn = isLoadOn
        self.isChargingOn = isChargingOn
        self.isSccChargingOn = isSccChargingOn
        self.isAcChargingOn = isAcChargingOn
        self.isSwitchedOn = isSwitchedOn
        self.isChargingToFloat = isChargingToFloat
        self.mode = mode
        self.modeLabel = modeLabel
        self.modeSource = modeSource
        self.chargeStage = chargeStage
        self.warnings = warnings
        self.hasFault = hasFault
    }

    static let empty = SystemInfo(
        busVoltage: 0, temperature: 0,
        isLoadOn: false, isChargingOn: false, isSccChargingOn: false,
        isAcChargingOn: false, isSwitchedOn: false, isChargingToFloat: false,
        mode: .standby, modeLabel: InverterMode.standby.defaultLabel, modeSource: "derived",
        chargeStage: .idle, warnings: [], hasFault: false
    )
}
