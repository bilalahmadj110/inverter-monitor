import SwiftUI

/// Mobile rendering of the web's `/savings` page. Surfaces the headline KPIs
/// (today / month / lifetime savings, payback), the current billing-month
/// slab projection with a cliff warning, and the detailed month bill delta.
/// Full tariff editing stays on the web — the Pi-hosted UI is the source of
/// truth for slab/surcharge edits.
struct SavingsReportView: View {
    @EnvironmentObject var reports: ReportsViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            PhaseIndicator(phase: reports.savingsPhase)
            kpiGrid
            monthCard
            projectionCard
            paybackCard
        }
    }

    // MARK: - KPI grid --------------------------------------------------------

    private var kpiGrid: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 10)], spacing: 10) {
            SummaryKpi(
                title: "Today",
                tint: Palette.solar,
                value: "Rs \(Self.pkr(reports.savings.today.savingsPkr))",
                subtitle: "\(Self.kwh(reports.savings.today.solarKwh)) kWh @ Rs \(Self.rate(reports.savings.today.marginalRate))/kWh"
            )
            SummaryKpi(
                title: "This Month",
                tint: Palette.battery,
                value: "Rs \(Self.pkr(reports.savings.month.savingsPkr))",
                subtitle: reports.savings.month.month.isEmpty ? "—" : reports.savings.month.month
            )
            SummaryKpi(
                title: "Lifetime",
                tint: Palette.grid,
                value: "Rs \(Self.pkr(reports.savings.lifetime.totalSavingsPkr))",
                subtitle: "\(reports.savings.lifetime.daysElapsed) days · \(Self.kwh(reports.savings.lifetime.totalSolarKwh)) kWh"
            )
            SummaryKpi(
                title: "Payback",
                tint: Color.mint,
                value: paybackValue,
                subtitle: paybackSubtitle
            )
        }
    }

    private var paybackValue: String {
        let pb = reports.savings.payback
        switch pb.status {
        case "ok":
            if let months = pb.paybackMonths {
                return String(format: "%.1f mo", months)
            }
            return "—"
        default:
            return "—"
        }
    }

    private var paybackSubtitle: String {
        let pb = reports.savings.payback
        switch pb.status {
        case "ok":
            let years = pb.paybackYears.map { String(format: "%.1f yrs", $0) } ?? "—"
            return "\(years) at Rs \(Self.pkr(pb.avgDailySavingsPkr))/day"
        case "set_install_cost":
            return "Set install cost on web UI"
        default:
            return "Need savings data to estimate"
        }
    }

    // MARK: - Month bill delta ------------------------------------------------

    private var monthCard: some View {
        let m = reports.savings.month
        return VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text("Month Bill Delta")
                    .font(.headline)
                    .foregroundStyle(.white)
                Spacer(minLength: 0)
                Text(m.month)
                    .font(.caption)
                    .foregroundStyle(Palette.subtleText)
            }

            InfoRow(label: "Solar", value: "\(Self.kwh(m.solarKwh)) kWh")
            InfoRow(label: "Grid Import", value: "\(Self.kwh(m.gridKwh)) kWh")
            InfoRow(label: "Total Load", value: "\(Self.kwh(m.loadKwh)) kWh")
            InfoRow(label: "Bill without solar", value: "Rs \(Self.pkr(m.billWithoutSolar))")
            InfoRow(label: "Bill with solar", value: "Rs \(Self.pkr(m.billWithSolar))")
            InfoRow(label: "You saved", value: "Rs \(Self.pkr(m.savingsPkr))")
        }
        .padding(14)
        .card()
    }

    // MARK: - Slab projection -------------------------------------------------

    private var projectionCard: some View {
        let p = reports.savings.projection
        return VStack(alignment: .leading, spacing: 10) {
            Text("Slab Projection")
                .font(.headline)
                .foregroundStyle(.white)

            InfoRow(label: "Days elapsed / remaining", value: "\(p.daysElapsed) / \(p.daysRemaining)")
            InfoRow(label: "Grid so far", value: "\(Self.kwh(p.gridKwhSoFar)) kWh")
            InfoRow(label: "Daily grid avg", value: "\(Self.kwh(p.dailyGridRateKwh)) kWh")
            InfoRow(label: "Projected month-end grid", value: "\(Self.kwh(p.projectedMonthEndGridKwh)) kWh")
            InfoRow(label: "Projected bill", value: "Rs \(Self.pkr(p.projectedBillTotalPkr))")
            if let cur = p.currentSlabLabel {
                InfoRow(label: "Current slab", value: cur)
            }
            if let proj = p.projectedSlabLabel {
                InfoRow(label: "Projected slab", value: proj)
            }
            if let kwh = p.kwhUntilCliff, let jump = p.rateJumpPkr {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(Color.orange)
                    Text("You're \(Self.kwh(kwh)) kWh from a slab cliff — the next unit costs Rs \(String(format: "%.2f", jump))/kWh more.")
                        .font(.caption)
                        .foregroundStyle(Color.orange)
                }
                .padding(10)
                .background(Color.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .strokeBorder(Color.orange.opacity(0.4))
                )
                .padding(.top, 4)
            }
        }
        .padding(14)
        .card()
    }

    // MARK: - Payback detail --------------------------------------------------

    private var paybackCard: some View {
        let pb = reports.savings.payback
        return VStack(alignment: .leading, spacing: 10) {
            Text("Payback")
                .font(.headline)
                .foregroundStyle(.white)

            InfoRow(label: "Install cost", value: pb.installCost > 0 ? "Rs \(Self.pkr(pb.installCost))" : "—")
            InfoRow(label: "Avg daily savings", value: "Rs \(Self.pkr(pb.avgDailySavingsPkr))")
            if let months = pb.paybackMonths {
                InfoRow(label: "Months to break-even", value: String(format: "%.1f mo", months))
            }
            if let years = pb.paybackYears {
                InfoRow(label: "Years to break-even", value: String(format: "%.2f yrs", years))
            }
            if pb.status != "ok" {
                Text(pb.status == "set_install_cost" ? "Add your install cost on the web Savings page to unlock payback estimates." : "Need a few days of savings to estimate payback.")
                    .font(.caption)
                    .foregroundStyle(Palette.subtleText)
                    .padding(.top, 4)
            }
        }
        .padding(14)
        .card()
    }

    // MARK: - Formatters ------------------------------------------------------

    private static let pkrFormatter: NumberFormatter = {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.maximumFractionDigits = 0
        f.groupingSeparator = ","
        return f
    }()

    private static func pkr(_ v: Double) -> String {
        pkrFormatter.string(from: NSNumber(value: v.rounded())) ?? "0"
    }

    private static func kwh(_ v: Double) -> String {
        String(format: "%.2f", v)
    }

    private static func rate(_ v: Double) -> String {
        String(format: "%.2f", v)
    }
}
