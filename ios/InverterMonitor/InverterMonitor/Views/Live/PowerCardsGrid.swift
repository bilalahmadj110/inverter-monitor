import SwiftUI

struct PowerCardsGrid: View {
    let metrics: InverterMetrics
    let showEstimated: Bool

    private let columns = [
        GridItem(.adaptive(minimum: 160), spacing: 12)
    ]

    var body: some View {
        LazyVGrid(columns: columns, spacing: 12) {
            solarCard
            batteryCard
            gridCard
            loadCard
        }
    }

    private var solarCard: some View {
        PowerCard(
            title: "Solar Production",
            value: "\(Int(metrics.solar.power.rounded()))",
            unit: "W",
            tint: Palette.solar,
            icon: "sun.max.fill"
        ) {
            HStack {
                Text(String(format: "%.1f V", metrics.solar.voltage))
                Spacer()
                Text(String(format: "%.2f A", metrics.solar.current))
            }
        }
    }

    private var batteryCard: some View {
        PowerCard(
            title: "Battery",
            value: "\(Int(metrics.battery.percentage.rounded()))",
            unit: "%",
            tint: Palette.battery,
            icon: "battery.100.bolt"
        ) {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(metrics.battery.direction.label)
                    Spacer()
                    Text("\(Int(abs(metrics.battery.power).rounded())) W")
                }
                HStack {
                    Text(String(format: "%.2f V", metrics.battery.voltage))
                    Spacer()
                    Text(String(format: "%.2f A", abs(metrics.battery.current)))
                }
                .foregroundStyle(Palette.subtleText)
            }
        }
    }

    private var gridCard: some View {
        PowerCard(
            title: "Grid",
            value: "\(Int(metrics.grid.power.rounded()))",
            unit: "W",
            tint: Palette.grid,
            icon: "powerplug.fill",
            trailingBadge: showEstimated && metrics.grid.estimated ? "EST" : nil
        ) {
            HStack {
                Text("\(Int(metrics.grid.voltage.rounded())) V")
                Spacer()
                Text(String(format: "%.1f Hz", metrics.grid.frequency))
            }
        }
    }

    private var loadCard: some View {
        PowerCard(
            title: "Load",
            value: "\(Int(metrics.load.effectivePower.rounded()))",
            unit: "W",
            tint: Palette.load,
            icon: "house.fill"
        ) {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("\(Int(metrics.load.apparentPower.rounded())) VA")
                    Spacer()
                    Text(String(format: "PF %.2f", metrics.load.powerFactor))
                }
                HStack {
                    Text("\(Int(metrics.load.voltage.rounded())) V")
                    Spacer()
                    Text("\(Int(metrics.load.percentage.rounded()))%")
                }
                .foregroundStyle(Palette.subtleText)
            }
        }
    }
}

private struct PowerCard<Footer: View>: View {
    let title: String
    let value: String
    let unit: String
    let tint: Color
    let icon: String
    var trailingBadge: String? = nil
    @ViewBuilder var footer: Footer

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(tint)
                Spacer(minLength: 0)
                Image(systemName: icon)
                    .foregroundStyle(tint.opacity(0.8))
                    .accessibilityHidden(true)
            }
            HStack(alignment: .lastTextBaseline, spacing: 4) {
                Text(value)
                    .font(.system(size: 26, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
                    // Smooth number morph on live updates — the classic Weather app trick.
                    // `value:` is a direction hint; Double-parsing handles plain numbers and
                    // degrades to a gentle cross-fade for compound strings like "1.2 / 0.8".
                    .contentTransition(.numericText(value: Double(value) ?? 0))
                    .animation(.easeOut(duration: 0.35), value: value)
                    .monospacedDigit()
                Text(unit)
                    .font(.subheadline)
                    .foregroundStyle(Palette.subtleText)
                if let badge = trailingBadge {
                    Text(badge)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(tint.opacity(0.9))
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(tint.opacity(0.15), in: Capsule())
                        .accessibilityLabel("Estimated")
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("\(title) \(value) \(unit)")
            footer
                .font(.caption)
                .foregroundStyle(.white.opacity(0.85))
        }
        .padding(14)
        .card()
    }
}
