import Foundation

/// Output source priority — where the load pulls power from.
enum OutputPriority: String, Decodable, CaseIterable, Identifiable, Equatable {
    case uti = "UTI"
    case sol = "SOL"
    case sbu = "SBU"

    var id: String { rawValue }

    var shortLabel: String {
        switch self {
        case .uti: return "UTI"
        case .sol: return "SOL"
        case .sbu: return "SBU"
        }
    }

    var title: String {
        switch self {
        case .uti: return "Utility First"
        case .sol: return "Solar First"
        case .sbu: return "SBU"
        }
    }

    var detail: String {
        switch self {
        case .uti: return "Grid powers the load; battery/solar stay as backup."
        case .sol: return "Solar feeds load first, then grid; battery is last resort."
        case .sbu: return "Solar → Battery → Utility. Typical off-grid profile."
        }
    }
}

/// Charger source priority — what's allowed to charge the battery.
enum ChargerPriority: String, Decodable, CaseIterable, Identifiable, Equatable {
    case utiSol = "UTI_SOL"
    case solFirst = "SOL_FIRST"
    case solUti = "SOL_UTI"
    case solOnly = "SOL_ONLY"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .utiSol: return "Utility + Solar"
        case .solFirst: return "Solar First"
        case .solUti: return "Solar + Utility"
        case .solOnly: return "Only Solar"
        }
    }

    var detail: String {
        switch self {
        case .utiSol: return "Grid and solar can both charge the battery."
        case .solFirst: return "Solar charges first; grid tops up if needed."
        case .solUti: return "Both charge simultaneously when available."
        case .solOnly: return "Only solar is allowed to charge; grid never does."
        }
    }
}

struct ConfigRow: Decodable, Equatable, Identifiable {
    var key: String
    var label: String
    var value: String
    var unit: String

    var id: String { key }

    private enum CodingKeys: String, CodingKey {
        case key, label, value, unit
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        key = (try? c.decode(String.self, forKey: .key)) ?? ""
        label = (try? c.decode(String.self, forKey: .label)) ?? key
        // Inverter returns value as either number or string; normalize to string.
        if let s = try? c.decode(String.self, forKey: .value) {
            value = s
        } else if let d = try? c.decode(Double.self, forKey: .value) {
            value = formatNumber(d)
        } else if let i = try? c.decode(Int.self, forKey: .value) {
            value = String(i)
        } else {
            value = "—"
        }
        unit = (try? c.decode(String.self, forKey: .unit)) ?? ""
    }

    init(key: String, label: String, value: String, unit: String) {
        self.key = key
        self.label = label
        self.value = value
        self.unit = unit
    }
}

private func formatNumber(_ d: Double) -> String {
    if d == d.rounded() { return String(Int(d)) }
    return String(format: "%.2f", d)
}

/// `GET /config` (the `config` nested object) and the inline `config` in `/stats`.
struct InverterConfig: Decodable, Equatable {
    var outputPriority: OutputPriority?
    var outputPriorityRaw: String?
    var chargerPriority: ChargerPriority?
    var chargerPriorityRaw: String?
    var batteryType: String?
    var maxChargingCurrent: Double?
    var maxAcChargingCurrent: Double?
    var batteryUnderVoltage: Double?
    var batteryBulkChargeVoltage: Double?
    var batteryFloatChargeVoltage: Double?
    var acOutputVoltage: Double?
    var acOutputFrequency: Double?
    var rows: [ConfigRow]

    var isEmpty: Bool {
        outputPriority == nil && chargerPriority == nil && rows.isEmpty
    }

    private enum CodingKeys: String, CodingKey {
        case outputPriority = "output_priority"
        case outputPriorityRaw = "output_priority_raw"
        case chargerPriority = "charger_priority"
        case chargerPriorityRaw = "charger_priority_raw"
        case batteryType = "battery_type"
        case maxChargingCurrent = "max_charging_current"
        case maxAcChargingCurrent = "max_ac_charging_current"
        case batteryUnderVoltage = "battery_under_voltage"
        case batteryBulkChargeVoltage = "battery_bulk_charge_voltage"
        case batteryFloatChargeVoltage = "battery_float_charge_voltage"
        case acOutputVoltage = "ac_output_voltage"
        case acOutputFrequency = "ac_output_frequency"
        case rows
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        outputPriority = try? c.decode(OutputPriority.self, forKey: .outputPriority)
        outputPriorityRaw = try? c.decode(String.self, forKey: .outputPriorityRaw)
        chargerPriority = try? c.decode(ChargerPriority.self, forKey: .chargerPriority)
        chargerPriorityRaw = try? c.decode(String.self, forKey: .chargerPriorityRaw)
        batteryType = Self.decodeNullableString(c, key: .batteryType)
        maxChargingCurrent = Self.decodeNullableDouble(c, key: .maxChargingCurrent)
        maxAcChargingCurrent = Self.decodeNullableDouble(c, key: .maxAcChargingCurrent)
        batteryUnderVoltage = Self.decodeNullableDouble(c, key: .batteryUnderVoltage)
        batteryBulkChargeVoltage = Self.decodeNullableDouble(c, key: .batteryBulkChargeVoltage)
        batteryFloatChargeVoltage = Self.decodeNullableDouble(c, key: .batteryFloatChargeVoltage)
        acOutputVoltage = Self.decodeNullableDouble(c, key: .acOutputVoltage)
        acOutputFrequency = Self.decodeNullableDouble(c, key: .acOutputFrequency)
        rows = (try? c.decode([ConfigRow].self, forKey: .rows)) ?? []
    }

    init() {
        outputPriority = nil
        outputPriorityRaw = nil
        chargerPriority = nil
        chargerPriorityRaw = nil
        batteryType = nil
        maxChargingCurrent = nil
        maxAcChargingCurrent = nil
        batteryUnderVoltage = nil
        batteryBulkChargeVoltage = nil
        batteryFloatChargeVoltage = nil
        acOutputVoltage = nil
        acOutputFrequency = nil
        rows = []
    }

    private static func decodeNullableString(_ c: KeyedDecodingContainer<CodingKeys>, key: CodingKeys) -> String? {
        if let s = try? c.decode(String.self, forKey: key), !s.isEmpty { return s }
        if let d = try? c.decode(Double.self, forKey: key) { return formatNumber(d) }
        if let i = try? c.decode(Int.self, forKey: key) { return String(i) }
        return nil
    }

    private static func decodeNullableDouble(_ c: KeyedDecodingContainer<CodingKeys>, key: CodingKeys) -> Double? {
        if let d = try? c.decode(Double.self, forKey: key) { return d }
        if let i = try? c.decode(Int.self, forKey: key) { return Double(i) }
        if let s = try? c.decode(String.self, forKey: key), let d = Double(s) { return d }
        return nil
    }
}

/// Response envelope for `GET /config`.
struct ConfigEnvelope: Decodable, Equatable {
    var config: InverterConfig
    var outputPriorityOptions: [ConfigOption]
    var chargerPriorityOptions: [ConfigOption]

    private enum CodingKeys: String, CodingKey {
        case config
        case outputPriorityOptions = "output_priority_options"
        case chargerPriorityOptions = "charger_priority_options"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        config = (try? c.decode(InverterConfig.self, forKey: .config)) ?? InverterConfig()
        outputPriorityOptions = (try? c.decode([ConfigOption].self, forKey: .outputPriorityOptions)) ?? []
        chargerPriorityOptions = (try? c.decode([ConfigOption].self, forKey: .chargerPriorityOptions)) ?? []
    }
}

struct ConfigOption: Decodable, Equatable, Identifiable {
    var key: String
    var label: String

    var id: String { key }
}

/// `POST /refresh-extras` response.
struct RefreshExtrasResponse: Decodable, Equatable {
    var mode: String?
    var warnings: [InverterWarning]
    var config: InverterConfig
    var cached: Bool
    var extrasAgeS: Double?

    private enum CodingKeys: String, CodingKey {
        case mode, warnings, config, cached
        case extrasAgeS = "extras_age_s"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        mode = try? c.decode(String.self, forKey: .mode)
        warnings = (try? c.decode([InverterWarning].self, forKey: .warnings)) ?? []
        config = (try? c.decode(InverterConfig.self, forKey: .config)) ?? InverterConfig()
        cached = (try? c.decode(Bool.self, forKey: .cached)) ?? false
        extrasAgeS = try? c.decode(Double.self, forKey: .extrasAgeS)
    }
}

/// `POST /set-output-priority` / `POST /set-charger-priority` response.
struct PriorityChangeResponse: Decodable, Equatable {
    var success: Bool
    var previous: String?
    var applied: AppliedChange?
    var config: InverterConfig?
    var error: String?

    struct AppliedChange: Decodable, Equatable {
        var mode: String
        var label: String
        var command: String
        var response: String?
    }

    private enum CodingKeys: String, CodingKey {
        case success, previous, applied, config, error
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        success = (try? c.decode(Bool.self, forKey: .success)) ?? false
        previous = try? c.decode(String.self, forKey: .previous)
        applied = try? c.decode(AppliedChange.self, forKey: .applied)
        config = try? c.decode(InverterConfig.self, forKey: .config)
        error = try? c.decode(String.self, forKey: .error)
    }
}
