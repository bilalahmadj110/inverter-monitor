import SwiftUI

/// Pill-shaped battery gauge that fills from the bottom according to state-of-charge.
/// Mirrors the SVG `battery-fill` rect in `templates/solar_flow.html` — green / amber / red at 50 / 20.
struct BatteryGauge: View {
    let percentage: Double
    let isActive: Bool

    private var clamped: CGFloat {
        CGFloat(max(0, min(100, percentage)) / 100)
    }

    private var fillColor: Color {
        if percentage < 20 { return Color.red }
        if percentage < 50 { return Color.orange }
        return Palette.battery
    }

    var body: some View {
        GeometryReader { proxy in
            let w = proxy.size.width
            let h = proxy.size.height
            let terminalHeight: CGFloat = h * 0.08
            let bodyHeight = h - terminalHeight
            let bodyWidth = w * 0.72
            let terminalWidth = bodyWidth * 0.34

            ZStack(alignment: .bottom) {
                // Terminal
                RoundedRectangle(cornerRadius: 2)
                    .fill(fillColor.opacity(isActive ? 1 : 0.55))
                    .frame(width: terminalWidth, height: terminalHeight)
                    .position(x: w / 2, y: terminalHeight / 2)

                // Body outline
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .strokeBorder(fillColor.opacity(isActive ? 1 : 0.55), lineWidth: 2.5)
                    .background(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(Color.white.opacity(0.06))
                    )
                    .frame(width: bodyWidth, height: bodyHeight)
                    .position(x: w / 2, y: terminalHeight + bodyHeight / 2)

                // Fill
                RoundedRectangle(cornerRadius: 5, style: .continuous)
                    .fill(fillColor.opacity(isActive ? 1 : 0.4))
                    .frame(width: max(0, bodyWidth - 6), height: max(0, (bodyHeight - 6) * clamped))
                    .position(
                        x: w / 2,
                        y: terminalHeight + bodyHeight - 3 - max(0, (bodyHeight - 6) * clamped) / 2
                    )
                    .animation(.easeOut(duration: 0.45), value: clamped)
                    .animation(.easeOut(duration: 0.25), value: fillColor)
            }
        }
    }
}
