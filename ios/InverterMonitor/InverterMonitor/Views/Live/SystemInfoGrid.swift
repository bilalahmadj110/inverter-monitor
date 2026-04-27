import SwiftUI

struct SystemInfoGrid: View {
    @ObservedObject var live: LiveDashboardViewModel

    private let columns = [GridItem(.adaptive(minimum: 140), spacing: 12)]

    var body: some View {
        LazyVGrid(columns: columns, spacing: 12) {
            infoTile(
                title: "Inverter Temp",
                value: formatTemp(live.status.system.temperature),
                unit: "°C",
                footnote: "Today peak \(formatTemp(live.summary.temperatureMax))°C"
            )
            infoTile(
                title: "DC Bus Voltage",
                value: formatBus(live.status.system.busVoltage),
                unit: "V",
                footnote: "Mode: \(live.status.system.modeLabel)"
            )
            infoTile(
                title: "Connection",
                value: live.connection.label,
                unit: nil,
                footnote: lastUpdateText
            )
            infoTile(
                title: "Reading Cycle",
                value: formatDuration(live.status.timing?.durationMs),
                unit: "ms",
                footnote: "Errors \(errorCount) / \(totalReadings)"
            )
        }
    }

    private func infoTile(title: String, value: String, unit: String?, footnote: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(Palette.subtleText)
            HStack(alignment: .lastTextBaseline, spacing: 4) {
                Text(value)
                    .font(.system(size: 18, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
                    .monospacedDigit()
                    .contentTransition(.numericText(value: Double(value) ?? 0))
                    .animation(.easeOut(duration: 0.3), value: value)
                if let unit {
                    Text(unit)
                        .font(.caption)
                        .foregroundStyle(Palette.subtleText)
                }
            }
            Text(footnote)
                .font(.caption2)
                .foregroundStyle(Palette.subtleText)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .card()
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title) \(value)\(unit.map { " \($0)" } ?? ""). \(footnote)")
    }

    private var lastUpdateText: String {
        guard let last = live.lastUpdate else { return "Waiting…" }
        return "Last update \(Self.timeFormatter.string(from: last))"
    }

    private var errorCount: Int { live.readingStats?.errorCount ?? 0 }
    private var totalReadings: Int { live.readingStats?.totalReadings ?? 0 }

    private func formatTemp(_ t: Double) -> String {
        if t <= 0 { return "—" }
        return "\(Int(t.rounded()))"
    }

    private func formatBus(_ v: Double) -> String {
        if v <= 0 { return "—" }
        return "\(Int(v.rounded()))"
    }

    private func formatDuration(_ ms: Double?) -> String {
        guard let ms, ms > 0 else { return "—" }
        return "\(Int(ms.rounded()))"
    }

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f
    }()
}
