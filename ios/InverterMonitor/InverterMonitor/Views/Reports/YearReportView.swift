import SwiftUI
import Charts

struct YearReportView: View {
    @EnvironmentObject var reports: ReportsViewModel
    private static let monthNames = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 10) {
                Image(systemName: "calendar")
                    .foregroundStyle(Palette.subtleText)
                Picker("Year", selection: $reports.yearValue) {
                    ForEach(yearOptions, id: \.self) { year in
                        Text(String(year)).tag(year)
                    }
                }
                .pickerStyle(.menu)
                .tint(.white)
                .onChange(of: reports.yearValue) { _, _ in
                    Task { await reports.loadYear() }
                }
                Spacer(minLength: 0)
            }
            .padding(12)
            .card()

            PhaseIndicator(phase: reports.yearPhase)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
                SummaryKpi(title: "Solar", tint: Palette.solar,
                           value: kwh(reports.yearStats.solarEnergyWh), subtitle: "kWh")
                SummaryKpi(title: "Grid", tint: Palette.grid,
                           value: kwh(reports.yearStats.gridEnergyWh), subtitle: "kWh")
                SummaryKpi(title: "Load", tint: Palette.load,
                           value: kwh(reports.yearStats.loadEnergyWh), subtitle: "kWh")
                SummaryKpi(title: "Bat. +/-", tint: Palette.battery,
                           value: "\(kwh(reports.yearStats.batteryChargeEnergyWh)) / \(kwh(reports.yearStats.batteryDischargeEnergyWh))",
                           subtitle: "kWh")
            }

            VStack(alignment: .leading, spacing: 10) {
                Text("Monthly Breakdown")
                    .font(.headline)
                    .foregroundStyle(.white)

                if reports.monthlyTotals.isEmpty {
                    HStack { Spacer(); Text("No data for this year").foregroundStyle(Palette.subtleText); Spacer() }
                        .frame(height: 240)
                } else {
                    Chart {
                        ForEach(reports.monthlyTotals) { row in
                            BarMark(
                                x: .value("Month", Self.monthNames[row.month - 1]),
                                y: .value("Solar", row.solar)
                            )
                            .foregroundStyle(by: .value("Series", "Solar"))
                            .position(by: .value("Series", "Solar"))
                        }
                        ForEach(reports.monthlyTotals) { row in
                            BarMark(
                                x: .value("Month", Self.monthNames[row.month - 1]),
                                y: .value("Grid", row.grid)
                            )
                            .foregroundStyle(by: .value("Series", "Grid"))
                            .position(by: .value("Series", "Grid"))
                        }
                        ForEach(reports.monthlyTotals) { row in
                            BarMark(
                                x: .value("Month", Self.monthNames[row.month - 1]),
                                y: .value("Load", row.load)
                            )
                            .foregroundStyle(by: .value("Series", "Load"))
                            .position(by: .value("Series", "Load"))
                        }
                        ForEach(reports.monthlyTotals) { row in
                            BarMark(
                                x: .value("Month", Self.monthNames[row.month - 1]),
                                y: .value("Battery", row.battery)
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

    private var yearOptions: [Int] {
        let current = Calendar.current.component(.year, from: Date())
        return Array((current - 4)...current).reversed()
    }

    private func kwh(_ wh: Double) -> String {
        String(format: "%.2f", wh / 1000.0)
    }
}
