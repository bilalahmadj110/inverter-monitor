import Foundation

/// `GET /savings/data` — one-shot payload powering the web's Savings page. Only
/// the fields the iOS Reports tab surfaces are modelled here; everything else
/// (slab editor, bill breakdown lines, AI chat) lives on the web UI.
struct CostSavingsPayload: Decodable, Equatable {
    var today: TodaySavings
    var month: MonthSavings
    var lifetime: LifetimeSavings
    var payback: PaybackInfo
    var projection: SlabProjection

    static let empty = CostSavingsPayload(
        today: .empty,
        month: .empty,
        lifetime: .empty,
        payback: .empty,
        projection: .empty
    )

    init(today: TodaySavings, month: MonthSavings, lifetime: LifetimeSavings, payback: PaybackInfo, projection: SlabProjection) {
        self.today = today
        self.month = month
        self.lifetime = lifetime
        self.payback = payback
        self.projection = projection
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyKey.self)
        today = (try? c.decode(TodaySavings.self, forKey: AnyKey("today"))) ?? .empty
        month = (try? c.decode(MonthSavings.self, forKey: AnyKey("month"))) ?? .empty
        lifetime = (try? c.decode(LifetimeSavings.self, forKey: AnyKey("lifetime"))) ?? .empty
        payback = (try? c.decode(PaybackInfo.self, forKey: AnyKey("payback"))) ?? .empty
        projection = (try? c.decode(SlabProjection.self, forKey: AnyKey("projection"))) ?? .empty
    }
}

struct TodaySavings: Decodable, Equatable {
    var date: String
    var solarKwh: Double
    var gridKwh: Double
    var loadKwh: Double
    var marginalRate: Double
    var savingsPkr: Double

    static let empty = TodaySavings(date: "", solarKwh: 0, gridKwh: 0, loadKwh: 0, marginalRate: 0, savingsPkr: 0)

    init(date: String, solarKwh: Double, gridKwh: Double, loadKwh: Double, marginalRate: Double, savingsPkr: Double) {
        self.date = date
        self.solarKwh = solarKwh
        self.gridKwh = gridKwh
        self.loadKwh = loadKwh
        self.marginalRate = marginalRate
        self.savingsPkr = savingsPkr
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyKey.self)
        date = (try? c.decode(String.self, forKey: AnyKey("date"))) ?? ""
        solarKwh = (try? c.decode(Double.self, forKey: AnyKey("solar_kwh"))) ?? 0
        gridKwh = (try? c.decode(Double.self, forKey: AnyKey("grid_kwh"))) ?? 0
        loadKwh = (try? c.decode(Double.self, forKey: AnyKey("load_kwh"))) ?? 0
        marginalRate = (try? c.decode(Double.self, forKey: AnyKey("marginal_rate_pkr_per_kwh"))) ?? 0
        savingsPkr = (try? c.decode(Double.self, forKey: AnyKey("savings_pkr"))) ?? 0
    }
}

struct MonthSavings: Decodable, Equatable {
    var month: String
    var solarKwh: Double
    var gridKwh: Double
    var loadKwh: Double
    var billWithoutSolar: Double
    var billWithSolar: Double
    var savingsPkr: Double

    static let empty = MonthSavings(month: "", solarKwh: 0, gridKwh: 0, loadKwh: 0, billWithoutSolar: 0, billWithSolar: 0, savingsPkr: 0)

    init(month: String, solarKwh: Double, gridKwh: Double, loadKwh: Double, billWithoutSolar: Double, billWithSolar: Double, savingsPkr: Double) {
        self.month = month
        self.solarKwh = solarKwh
        self.gridKwh = gridKwh
        self.loadKwh = loadKwh
        self.billWithoutSolar = billWithoutSolar
        self.billWithSolar = billWithSolar
        self.savingsPkr = savingsPkr
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyKey.self)
        month = (try? c.decode(String.self, forKey: AnyKey("month"))) ?? ""
        let energy = (try? c.decode([String: Double].self, forKey: AnyKey("energy"))) ?? [:]
        solarKwh = energy["solar_kwh"] ?? 0
        gridKwh = energy["grid_kwh"] ?? 0
        loadKwh = energy["load_kwh"] ?? 0
        let without = try? c.decode([String: AnyJSON].self, forKey: AnyKey("bill_without_solar"))
        let with = try? c.decode([String: AnyJSON].self, forKey: AnyKey("bill_with_solar"))
        billWithoutSolar = without?["total"]?.asDouble ?? 0
        billWithSolar = with?["total"]?.asDouble ?? 0
        savingsPkr = (try? c.decode(Double.self, forKey: AnyKey("savings_pkr"))) ?? 0
    }
}

struct LifetimeSavings: Decodable, Equatable {
    var systemStartDate: String?
    var daysElapsed: Int
    var totalSavingsPkr: Double
    var totalSolarKwh: Double
    var avgDailySavingsPkr: Double

    static let empty = LifetimeSavings(systemStartDate: nil, daysElapsed: 0, totalSavingsPkr: 0, totalSolarKwh: 0, avgDailySavingsPkr: 0)

    init(systemStartDate: String?, daysElapsed: Int, totalSavingsPkr: Double, totalSolarKwh: Double, avgDailySavingsPkr: Double) {
        self.systemStartDate = systemStartDate
        self.daysElapsed = daysElapsed
        self.totalSavingsPkr = totalSavingsPkr
        self.totalSolarKwh = totalSolarKwh
        self.avgDailySavingsPkr = avgDailySavingsPkr
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyKey.self)
        systemStartDate = try? c.decode(String.self, forKey: AnyKey("system_start_date"))
        daysElapsed = (try? c.decode(Int.self, forKey: AnyKey("days_elapsed"))) ?? 0
        totalSavingsPkr = (try? c.decode(Double.self, forKey: AnyKey("total_savings_pkr"))) ?? 0
        totalSolarKwh = (try? c.decode(Double.self, forKey: AnyKey("total_solar_kwh"))) ?? 0
        avgDailySavingsPkr = (try? c.decode(Double.self, forKey: AnyKey("avg_daily_savings_pkr"))) ?? 0
    }
}

struct PaybackInfo: Decodable, Equatable {
    var installCost: Double
    var avgDailySavingsPkr: Double
    var paybackMonths: Double?
    var paybackYears: Double?
    /// `ok` / `set_install_cost` / `no_savings_yet` — drives the UI copy.
    var status: String

    static let empty = PaybackInfo(installCost: 0, avgDailySavingsPkr: 0, paybackMonths: nil, paybackYears: nil, status: "set_install_cost")

    init(installCost: Double, avgDailySavingsPkr: Double, paybackMonths: Double?, paybackYears: Double?, status: String) {
        self.installCost = installCost
        self.avgDailySavingsPkr = avgDailySavingsPkr
        self.paybackMonths = paybackMonths
        self.paybackYears = paybackYears
        self.status = status
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyKey.self)
        installCost = (try? c.decode(Double.self, forKey: AnyKey("install_cost_pkr"))) ?? 0
        avgDailySavingsPkr = (try? c.decode(Double.self, forKey: AnyKey("avg_daily_savings_pkr"))) ?? 0
        paybackMonths = try? c.decode(Double.self, forKey: AnyKey("payback_months"))
        paybackYears = try? c.decode(Double.self, forKey: AnyKey("payback_years"))
        status = (try? c.decode(String.self, forKey: AnyKey("status"))) ?? "set_install_cost"
    }
}

struct SlabProjection: Decodable, Equatable {
    var month: String
    var daysElapsed: Int
    var daysRemaining: Int
    var gridKwhSoFar: Double
    var dailyGridRateKwh: Double
    var projectedMonthEndGridKwh: Double
    var projectedBillTotalPkr: Double
    var currentSlabLabel: String?
    var projectedSlabLabel: String?
    var kwhUntilCliff: Double?
    var rateJumpPkr: Double?

    static let empty = SlabProjection(
        month: "", daysElapsed: 0, daysRemaining: 0,
        gridKwhSoFar: 0, dailyGridRateKwh: 0, projectedMonthEndGridKwh: 0,
        projectedBillTotalPkr: 0, currentSlabLabel: nil, projectedSlabLabel: nil,
        kwhUntilCliff: nil, rateJumpPkr: nil
    )

    init(
        month: String,
        daysElapsed: Int,
        daysRemaining: Int,
        gridKwhSoFar: Double,
        dailyGridRateKwh: Double,
        projectedMonthEndGridKwh: Double,
        projectedBillTotalPkr: Double,
        currentSlabLabel: String?,
        projectedSlabLabel: String?,
        kwhUntilCliff: Double?,
        rateJumpPkr: Double?
    ) {
        self.month = month
        self.daysElapsed = daysElapsed
        self.daysRemaining = daysRemaining
        self.gridKwhSoFar = gridKwhSoFar
        self.dailyGridRateKwh = dailyGridRateKwh
        self.projectedMonthEndGridKwh = projectedMonthEndGridKwh
        self.projectedBillTotalPkr = projectedBillTotalPkr
        self.currentSlabLabel = currentSlabLabel
        self.projectedSlabLabel = projectedSlabLabel
        self.kwhUntilCliff = kwhUntilCliff
        self.rateJumpPkr = rateJumpPkr
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyKey.self)
        month = (try? c.decode(String.self, forKey: AnyKey("month"))) ?? ""
        daysElapsed = (try? c.decode(Int.self, forKey: AnyKey("days_elapsed"))) ?? 0
        daysRemaining = (try? c.decode(Int.self, forKey: AnyKey("days_remaining"))) ?? 0
        gridKwhSoFar = (try? c.decode(Double.self, forKey: AnyKey("grid_kwh_so_far"))) ?? 0
        dailyGridRateKwh = (try? c.decode(Double.self, forKey: AnyKey("daily_grid_rate_kwh"))) ?? 0
        projectedMonthEndGridKwh = (try? c.decode(Double.self, forKey: AnyKey("projected_month_end_grid_kwh"))) ?? 0
        projectedBillTotalPkr = (try? c.decode(Double.self, forKey: AnyKey("projected_bill_total_pkr"))) ?? 0
        let current = try? c.decode([String: AnyJSON].self, forKey: AnyKey("current_slab"))
        let projected = try? c.decode([String: AnyJSON].self, forKey: AnyKey("projected_slab"))
        currentSlabLabel = current?["current_label"]?.asString
        projectedSlabLabel = projected?["current_label"]?.asString
        let cliff = try? c.decode([String: AnyJSON].self, forKey: AnyKey("cliff_alert"))
        kwhUntilCliff = cliff?["kwh_until_cliff"]?.asDouble
        rateJumpPkr = cliff?["rate_jump_pkr_per_kwh"]?.asDouble
    }
}

/// Minimal `Any`-JSON shim so we can decode heterogenous bill-breakdown / slab-info
/// nested dicts without modelling every field upstream. Only the two `as*`
/// accessors we actually use for the Reports Savings tab are provided.
private struct AnyJSON: Decodable {
    let asDouble: Double?
    let asString: String?

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if let d = try? c.decode(Double.self) {
            asDouble = d
            asString = nil
        } else if let s = try? c.decode(String.self) {
            asDouble = nil
            asString = s
        } else if let b = try? c.decode(Bool.self) {
            asDouble = b ? 1 : 0
            asString = String(b)
        } else if let i = try? c.decode(Int.self) {
            asDouble = Double(i)
            asString = String(i)
        } else {
            asDouble = nil
            asString = nil
        }
    }
}

private struct AnyKey: CodingKey {
    var stringValue: String
    var intValue: Int? { nil }
    init(_ s: String) { stringValue = s }
    init?(stringValue: String) { self.stringValue = stringValue }
    init?(intValue: Int) { return nil }
}
