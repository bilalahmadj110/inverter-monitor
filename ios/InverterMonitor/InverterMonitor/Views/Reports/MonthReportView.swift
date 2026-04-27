import SwiftUI
import Charts

struct MonthReportView: View {
    @EnvironmentObject var reports: ReportsViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 10) {
                Image(systemName: "calendar")
                    .foregroundStyle(Palette.subtleText)
                DatePicker("",
                           selection: $reports.monthDate,
                           displayedComponents: .date)
                    .labelsHidden()
                    .onChange(of: reports.monthDate) { _, _ in
                        Task { await reports.loadMonth() }
                    }
                Spacer(minLength: 0)
            }
            .padding(12)
            .card()

            PhaseIndicator(phase: reports.monthPhase)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
                SummaryKpi(title: "Solar", tint: Palette.solar,
                           value: kwh(reports.monthStats.solarEnergyWh), subtitle: "kWh")
                SummaryKpi(title: "Grid", tint: Palette.grid,
                           value: kwh(reports.monthStats.gridEnergyWh), subtitle: "kWh")
                SummaryKpi(title: "Load", tint: Palette.load,
                           value: kwh(reports.monthStats.loadEnergyWh), subtitle: "kWh")
                SummaryKpi(title: "Bat. +/-", tint: Palette.battery,
                           value: "\(kwh(reports.monthStats.batteryChargeEnergyWh)) / \(kwh(reports.monthStats.batteryDischargeEnergyWh))",
                           subtitle: "kWh")
            }

            VStack(alignment: .leading, spacing: 10) {
                Text("Daily Breakdown")
                    .font(.headline)
                    .foregroundStyle(.white)
                if reports.monthHistory.isEmpty {
                    HStack { Spacer(); Text("No daily rows yet").foregroundStyle(Palette.subtleText); Spacer() }
                        .frame(height: 240)
                } else {
                    Chart {
                        ForEach(Array(reports.monthHistory.enumerated()), id: \.element.id) { _, row in
                            BarMark(
                                x: .value("Day", String(row.date.suffix(2))),
                                y: .value("Solar", row.solarKwh)
                            )
                            .foregroundStyle(by: .value("Series", "Solar"))
                            .position(by: .value("Series", "Solar"))
                        }
                        ForEach(reports.monthHistory) { row in
                            BarMark(
                                x: .value("Day", String(row.date.suffix(2))),
                                y: .value("Grid", row.gridKwh)
                            )
                            .foregroundStyle(by: .value("Series", "Grid"))
                            .position(by: .value("Series", "Grid"))
                        }
                        ForEach(reports.monthHistory) { row in
                            BarMark(
                                x: .value("Day", String(row.date.suffix(2))),
                                y: .value("Load", row.loadKwh)
                            )
                            .foregroundStyle(by: .value("Series", "Load"))
                            .position(by: .value("Series", "Load"))
                        }
                        ForEach(reports.monthHistory) { row in
                            BarMark(
                                x: .value("Day", String(row.date.suffix(2))),
                                y: .value("Battery", row.batteryChargeKwh)
                            )
                            .foregroundStyle(by: .value("Series", "Battery"))
                            .position(by: .value("Series", "Battery"))
                        }
                    }
                    .chartForegroundStyleScale([
                        "Solar": Palette.solar,
                        "Grid": Palette.grid,
                        "Load": Palette.load,
                        "Battery": Palette.battery
                    ])
                    .frame(height: 300)
                    .chartYAxis {
                        AxisMarks(position: .leading) { value in
                            AxisGridLine().foregroundStyle(Palette.cardBorder)
                            AxisValueLabel {
                                if let v = value.as(Double.self) {
                                    Text("\(Int(v)) kWh")
                                        .font(.caption2)
                                        .foregroundStyle(Palette.mutedText)
                                }
                            }
                        }
                    }
                    .chartXAxis {
                        AxisMarks { _ in
                            AxisGridLine().foregroundStyle(Palette.cardBorder)
                            AxisValueLabel().foregroundStyle(Palette.mutedText)
                        }
                    }
                }
            }
            .padding(14)
            .card()
        }
    }

    private func kwh(_ wh: Double) -> String {
        String(format: "%.2f", wh / 1000.0)
    }
}
