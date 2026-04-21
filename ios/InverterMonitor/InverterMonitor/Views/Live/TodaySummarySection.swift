import SwiftUI

/// Three-way period toggle that mirrors the classic dashboard's Today/This Month/This Year
/// stats tabs. On tap of the whole card, we deep-link to the Reports tab for drill-down.
struct TodaySummarySection: View {
    let summary: DailySummary
    let monthStats: MonthlyStats?
    let yearStats: YearlyStats?

    enum Period: String, CaseIterable, Identifiable {
        case today, month, year
        var id: String { rawValue }
        var title: String {
            switch self {
            case .today: return "Today"
            case .month: return "This Month"
            case .year: return "This Year"
            }
        }
    }

    @State private var period: Period = .today

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header

            Picker("Period", selection: $period) {
                ForEach(Period.allCases) { Text($0.title).tag($0) }
            }
            .pickerStyle(.segmented)
            .sensoryFeedback(.selection, trigger: period)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
                summaryTile(title: "Solar", tint: Palette.solar, value: kwh(activeSolar))
                summaryTile(title: "Grid Import", tint: Palette.grid, value: kwh(activeGrid))
                summaryTile(title: "Load", tint: Palette.load, value: kwh(activeLoad))
                chargeDischargeTile()
                if period == .today {
                    selfSufficiencyTile()
                }
            }
        }
        .padding(14)
        .card()
        .contentShape(Rectangle())
        .onTapGesture {
            if period == .today {
                tapCount &+= 1
                // Deep-link to Reports > Day for today's date.
                NotificationCenter.default.post(name: .inverterOpenDayReport, object: Date())
            }
        }
        .sensoryFeedback(.impact(weight: .light), trigger: tapCount)
    }

    @State private var tapCount: Int = 0

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(period.title)
                .font(.headline)
                .foregroundStyle(.white)
            Spacer(minLength: 0)
            Text(dateSubtitle)
                .font(.caption)
                .foregroundStyle(Palette.subtleText)
            if period == .today {
                Image(systemName: "arrow.up.forward.square")
                    .foregroundStyle(Palette.subtleText)
                    .font(.caption)
                    .accessibilityLabel("Open Day report")
            }
        }
    }

    // MARK: - Period-aware values -------------------------------------------

    private var activeSolar: Double {
        switch period {
        case .today: return summary.solarKwh
        case .month: return (monthStats?.solarEnergyWh ?? 0) / 1000.0
        case .year: return (yearStats?.solarEnergyWh ?? 0) / 1000.0
        }
    }

    private var activeGrid: Double {
        switch period {
        case .today: return summary.gridKwh
        case .month: return (monthStats?.gridEnergyWh ?? 0) / 1000.0
        case .year: return (yearStats?.gridEnergyWh ?? 0) / 1000.0
        }
    }

    private var activeLoad: Double {
        switch period {
        case .today: return summary.loadKwh
        case .month: return (monthStats?.loadEnergyWh ?? 0) / 1000.0
        case .year: return (yearStats?.loadEnergyWh ?? 0) / 1000.0
        }
    }

    private var activeCharge: Double {
        switch period {
        case .today: return summary.batteryChargeKwh
        case .month: return (monthStats?.batteryChargeEnergyWh ?? 0) / 1000.0
        case .year: return (yearStats?.batteryChargeEnergyWh ?? 0) / 1000.0
        }
    }

    private var activeDischarge: Double {
        switch period {
        case .today: return summary.batteryDischargeKwh
        case .month: return (monthStats?.batteryDischargeEnergyWh ?? 0) / 1000.0
        case .year: return (yearStats?.batteryDischargeEnergyWh ?? 0) / 1000.0
        }
    }

    private var dateSubtitle: String {
        switch period {
        case .today: return summary.date ?? "—"
        case .month: return monthStats?.month ?? currentMonth
        case .year: return yearStats?.year ?? currentYear
        }
    }

    private var currentMonth: String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM"
        return f.string(from: Date())
    }

    private var currentYear: String {
        String(Calendar.current.component(.year, from: Date()))
    }

    // MARK: - Tiles ----------------------------------------------------------

    private func summaryTile(title: String, tint: Color, value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(tint)
            HStack(alignment: .lastTextBaseline, spacing: 4) {
                Text(value)
                    .font(.system(size: 20, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
                    .contentTransition(.numericText(value: Double(value) ?? 0))
                    .animation(.easeOut(duration: 0.35), value: value)
                    .monospacedDigit()
                Text("kWh")
                    .font(.caption)
                    .foregroundStyle(Palette.subtleText)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Palette.cardSurface.opacity(0.6), in: RoundedRectangle(cornerRadius: 10))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title) \(value) kilowatt hours")
    }

    private func chargeDischargeTile() -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Bat. Charge / Discharge")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Palette.battery)
            Text("\(kwh(activeCharge)) / \(kwh(activeDischarge)) kWh")
                .font(.system(size: 16, weight: .semibold, design: .rounded))
                .foregroundStyle(.white)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Palette.cardSurface.opacity(0.6), in: RoundedRectangle(cornerRadius: 10))
    }

    private func selfSufficiencyTile() -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Self-Sufficiency")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Color.mint)
            HStack(alignment: .lastTextBaseline, spacing: 4) {
                Text("\(Int((summary.selfSufficiency * 100).rounded()))")
                    .font(.system(size: 20, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
                Text("%")
                    .font(.caption)
                    .foregroundStyle(Palette.subtleText)
            }
            Text("Solar share \(Int((summary.solarFraction * 100).rounded()))%")
                .font(.caption2)
                .foregroundStyle(Palette.subtleText)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Palette.cardSurface.opacity(0.6), in: RoundedRectangle(cornerRadius: 10))
    }

    private func kwh(_ value: Double) -> String {
        String(format: "%.2f", value)
    }
}
