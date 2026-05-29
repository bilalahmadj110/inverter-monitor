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
                AnimatedMetric(text: String(format: "%.1f V", metrics.solar.voltage))
                Spacer()
                AnimatedMetric(text: String(format: "%.2f A", metrics.solar.current))
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
                    AnimatedMetric(text: "\(Int(abs(metrics.battery.power).rounded())) W")
                }
                HStack {
                    AnimatedMetric(text: String(format: "%.2f V", metrics.battery.voltage))
                    Spacer()
                    AnimatedMetric(text: String(format: "%.2f A", abs(metrics.battery.current)))
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
                AnimatedMetric(text: "\(Int(metrics.grid.voltage.rounded())) V")
                Spacer()
                AnimatedMetric(text: String(format: "%.1f Hz", metrics.grid.frequency))
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
                    AnimatedMetric(text: "\(Int(metrics.load.apparentPower.rounded())) VA")
                    Spacer()
                    AnimatedMetric(text: String(format: "PF %.2f", metrics.load.powerFactor))
                }
                HStack {
                    AnimatedMetric(text: "\(Int(metrics.load.voltage.rounded())) V")
                    Spacer()
                    AnimatedMetric(text: "\(Int(metrics.load.percentage.rounded()))%")
                }
                .foregroundStyle(Palette.subtleText)
            }
        }
    }
}

/// Number-morph wrapper that reuses the same `.numericText` content transition +
/// ease-out animation the primary card values already use. Scrapes the first Double
/// out of the string so the morph direction hint is accurate even for strings like
/// "PF 0.98" or "27.3 V"; falls back to a plain cross-fade otherwise.
struct AnimatedMetric: View {
    let text: String
    var font: Font = .caption

    var body: some View {
        Text(text)
            .font(font)
            .monospacedDigit()
            .contentTransition(.numericText(value: Self.firstNumber(in: text)))
            .animation(.easeOut(duration: 0.35), value: text)
    }

    /// Extracts the first signed decimal the scanner can find. Used purely as the
    /// `value:` hint for `.numericText` so the digit morph knows which way to roll.
    private static func firstNumber(in s: String) -> Double {
        let scanner = Scanner(string: s)
        scanner.charactersToBeSkipped = CharacterSet(charactersIn: " ")
            .union(.letters)
            .union(.punctuationCharacters.subtracting(CharacterSet(charactersIn: "-.")))
        return scanner.scanDouble() ?? 0
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
            // Trailing spacer so Solar/Grid (one-line footers) don't collapse
            // to a shorter intrinsic height than Battery/Load (two-line
            // footers). Combined with the `.frame(maxHeight: .infinity)` +
            // fixed minHeight below, this gives all four cards identical
            // visual height without tying the layout to a magic pixel count.
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        // 134pt is the tallest natural content size when the footer has two
        // lines (Battery / Load); Solar / Grid pad to the same via the
        // trailing Spacer above so all four cards stay visually uniform
        // without wasting vertical real estate.
        .frame(maxWidth: .infinity, minHeight: 134, maxHeight: .infinity, alignment: .topLeading)
        .card()
    }
}
