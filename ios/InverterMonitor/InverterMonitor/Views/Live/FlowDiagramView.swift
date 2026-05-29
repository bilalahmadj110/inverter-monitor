import SwiftUI

enum FlowComponent: String, Identifiable, CaseIterable {
    case solar, grid, battery, load, inverter

    var id: String { rawValue }

    var title: String {
        switch self {
        case .solar: return "Solar"
        case .grid: return "Grid"
        case .battery: return "Battery"
        case .load: return "Load"
        case .inverter: return "Inverter"
        }
    }

    var icon: String {
        switch self {
        case .solar: return "sun.max.fill"
        case .grid: return "powerplug.fill"
        case .battery: return "battery.100"
        case .load: return "house.fill"
        case .inverter: return "cpu.fill"
        }
    }

    var tint: Color {
        switch self {
        case .solar: return Palette.solar
        case .grid: return Palette.grid
        case .battery: return Palette.battery
        case .load: return Palette.load
        case .inverter: return Palette.inverterAmber
        }
    }
}

/// The diamond-shaped solar/grid/load/battery + central inverter flow diagram, with
/// animated dashed connection lines that reflect live power direction.
struct FlowDiagramView: View {
    let status: InverterStatus
    let onTap: (FlowComponent) -> Void

    var body: some View {
        GeometryReader { proxy in
            let size = proxy.size
            // How far inside the container the corner nodes' *centers* sit, in points.
            // Keeps the node's outer edge on screen regardless of screen width.
            let margin: CGFloat = 86
            let topY = size.height * 0.19
            let botY = size.height * 0.81
            ZStack {
                // Lines + particles get their own Metal layer so the 60 FPS dash
                // scroll + sliding-dot animations don't fight the parent
                // ScrollView's layout loop. Kept INSIDE drawingGroup because
                // those are shape/path animations that benefit from rasterization.
                ConnectionsLayer(size: size, status: status)
                    .compositingGroup()
                    .drawingGroup(opaque: false)

                // Labels + icons live OUTSIDE drawingGroup so SwiftUI's
                // `.contentTransition(.numericText)` on the corner-node value
                // strings and the in-flow W / V / Hz labels actually animates.
                // drawingGroup rasterizes its subtree to a bitmap, which
                // bypasses per-text morph transitions.
                LinkLabelsLayer(size: size, status: status)
                // Sliding dots also live outside drawingGroup — their
                // `withAnimation(.linear.repeatForever)` doesn't survive the
                // Metal rasterization and was leaving them frozen at their
                // start positions.
                FlowParticlesLayer(size: size, status: status)

                cornerNode(.grid,    center: CGPoint(x: margin, y: topY), alignLeading: false)
                cornerNode(.load,    center: CGPoint(x: size.width - margin, y: topY), alignLeading: true)
                cornerNode(.solar,   center: CGPoint(x: margin, y: botY), alignLeading: false)
                cornerNode(.battery, center: CGPoint(x: size.width - margin, y: botY), alignLeading: true)

                centerNode(size: size)
            }
        }
        .frame(height: 320)
        .padding(.vertical, 6)
    }

    // MARK: Corner node ------------------------------------------------------

    private func cornerNode(_ component: FlowComponent, center: CGPoint, alignLeading: Bool) -> some View {
        let values = valuesFor(component)
        let isActive = isActive(component)
        // Grid/solar live on the LEFT side: icon on the left, value text to its right.
        // Load/battery on the RIGHT: value text on the left, icon on the right.
        // `alignLeading` here means "text flows to the right of the icon".
        return Button {
            onTap(component)
        } label: {
            HStack(spacing: 10) {
                if alignLeading {
                    valueStack(values: values, alignment: .trailing)
                    componentIcon(component, isActive: isActive)
                } else {
                    componentIcon(component, isActive: isActive)
                    valueStack(values: values, alignment: .leading)
                }
            }
            .padding(.horizontal, 4)
            .padding(.vertical, 4)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .frame(width: 148, alignment: alignLeading ? .trailing : .leading)
        .position(center)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(component.title), \(values.primary), \(values.secondary)")
        .accessibilityHint("Double tap to view details and settings")
        .accessibilityAddTraits(.isButton)
    }

    @ViewBuilder
    private func componentIcon(_ component: FlowComponent, isActive: Bool) -> some View {
        if component == .battery {
            BatteryGauge(percentage: status.metrics.battery.percentage, isActive: isActive)
                .frame(width: 56, height: 56)
                .overlay(alignment: .topTrailing) { activeDot(isActive: isActive) }
                .opacity(isActive ? 1 : 0.55)
        } else {
            ZStack {
                Circle()
                    .fill(component.tint.opacity(isActive ? 0.22 : 0.10))
                    .frame(width: 56, height: 56)
                Image(systemName: component.icon)
                    .font(.system(size: 24, weight: .semibold))
                    .foregroundStyle(isActive ? component.tint : component.tint.opacity(0.4))
            }
            .overlay(alignment: .topTrailing) { activeDot(isActive: isActive) }
            .opacity(isActive ? 1 : 0.55)
        }
    }

    private func activeDot(isActive: Bool) -> some View {
        Circle()
            .fill(isActive ? Color.green : Color.gray)
            .frame(width: 10, height: 10)
            .shadow(color: isActive ? Color.green : .clear, radius: 4)
            .offset(x: 2, y: -2)
    }

    private func valueStack(values: (primary: String, secondary: String), alignment: HorizontalAlignment) -> some View {
        // Both lines use `.numericText` content transitions so voltage / watts /
        // percentage / frequency morph smoothly at the 600ms poll cadence,
        // matching the Today tile behavior. The `value:` hint is parsed out of
        // the string so the digit roll knows which direction to go.
        VStack(alignment: alignment, spacing: 2) {
            Text(values.primary)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.white)
                .monospacedDigit()
                .contentTransition(.numericText(value: Self.firstNumber(in: values.primary)))
                .animation(.easeOut(duration: 0.35), value: values.primary)
            Text(values.secondary)
                .font(.system(size: 11))
                .foregroundStyle(Palette.subtleText)
                .monospacedDigit()
                .contentTransition(.numericText(value: Self.firstNumber(in: values.secondary)))
                .animation(.easeOut(duration: 0.35), value: values.secondary)
        }
    }

    /// Scrapes the first signed decimal out of a formatted string — used as the
    /// direction hint for `.numericText` so digit rolls go the right way.
    /// Values like "231 V" / "27.3 V" / "12%" / "50.3 Hz" all parse cleanly.
    fileprivate static func firstNumber(in s: String) -> Double {
        let scanner = Scanner(string: s)
        scanner.charactersToBeSkipped = CharacterSet(charactersIn: " ")
            .union(.letters)
            .union(.punctuationCharacters.subtracting(CharacterSet(charactersIn: "-.")))
        return scanner.scanDouble() ?? 0
    }

    private func centerNode(size: CGSize) -> some View {
        Button {
            onTap(.inverter)
        } label: {
            VStack(spacing: 4) {
                ZStack {
                    Circle()
                        .fill(Palette.inverterAmber.opacity(0.18))
                        .frame(width: 92, height: 92)
                    Image(systemName: "bolt.batteryblock.fill")
                        .font(.system(size: 36))
                        .foregroundStyle(Palette.inverterAmber)
                }
                Text(tempLabel)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.white.opacity(0.75))
                    .contentTransition(.numericText())
                    .animation(.easeOut(duration: 0.35), value: tempLabel)
            }
        }
        .buttonStyle(.plain)
        .position(x: size.width * 0.5, y: size.height * 0.5)
        .accessibilityLabel("Inverter. Temperature \(tempLabel), mode \(status.system.modeLabel)")
        .accessibilityHint("Double tap to view system configuration")
        .accessibilityAddTraits(.isButton)
    }

    private var tempLabel: String {
        if status.system.temperature <= 0 { return "—°C" }
        return "\(Int(status.system.temperature.rounded()))°C"
    }

    // MARK: Helpers ----------------------------------------------------------

    private func valuesFor(_ component: FlowComponent) -> (primary: String, secondary: String) {
        switch component {
        case .solar:
            let power = Int(status.metrics.solar.power.rounded())
            return ("\(power) W", String(format: "%.1f V", status.metrics.solar.voltage))
        case .grid:
            return (
                "\(Int(status.metrics.grid.voltage.rounded())) V",
                String(format: "%.1f Hz", status.metrics.grid.frequency)
            )
        case .battery:
            return (
                "\(Int(status.metrics.battery.percentage.rounded()))%",
                String(format: "%.1f V", status.metrics.battery.voltage)
            )
        case .load:
            let w = Int(status.metrics.load.effectivePower.rounded())
            let pct = Int(status.metrics.load.percentage.rounded())
            return ("\(w) W", "\(Int(status.metrics.load.voltage.rounded())) V · \(pct)%")
        case .inverter:
            return (tempLabel, "")
        }
    }

    private func isActive(_ component: FlowComponent) -> Bool {
        switch component {
        case .solar: return status.metrics.solar.power > 5
        case .grid: return status.metrics.grid.inUse
        case .battery: return status.metrics.battery.voltage > 20
        case .load: return status.metrics.load.effectivePower > 5
        case .inverter: return true
        }
    }
}

/// Dashed animated SVG-like connection lines drawn under the corner nodes.
private struct ConnectionsLayer: View {
    let size: CGSize
    let status: InverterStatus

    var body: some View {
        // Must match FlowDiagramView's layout constants.
        let margin: CGFloat = 86
        let topY = size.height * 0.19
        let botY = size.height * 0.81
        let centerX = size.width * 0.5
        let centerTopY = size.height * 0.38
        let centerBotY = size.height * 0.62
        // Pull the corner endpoints slightly inward from the icon center so the line
        // meets the icon's edge instead of its centre.
        let inwardGrid    = CGPoint(x: margin + 28, y: topY + 10)
        let inwardLoad    = CGPoint(x: size.width - margin - 28, y: topY + 10)
        let inwardSolar   = CGPoint(x: margin + 28, y: botY - 10)
        let inwardBattery = CGPoint(x: size.width - margin - 28, y: botY - 10)

        ZStack {
            link(from: inwardGrid, to: CGPoint(x: centerX - 36, y: centerTopY),
                 color: Palette.grid,
                 active: status.metrics.grid.inUse,
                 reversed: false)
            link(from: CGPoint(x: centerX + 36, y: centerTopY), to: inwardLoad,
                 color: Palette.load,
                 active: status.metrics.load.effectivePower > 5,
                 reversed: false)
            link(from: inwardSolar, to: CGPoint(x: centerX - 36, y: centerBotY),
                 color: Palette.solar,
                 active: status.metrics.solar.power > 5,
                 reversed: false)
            link(from: CGPoint(x: centerX + 36, y: centerBotY), to: inwardBattery,
                 color: Palette.battery,
                 active: status.metrics.battery.direction != .idle,
                 reversed: status.metrics.battery.direction == .charging)
        }
    }

    @ViewBuilder
    private func link(from start: CGPoint, to end: CGPoint, color: Color, active: Bool, reversed: Bool) -> some View {
        AnimatedDashLine(
            start: start,
            end: end,
            color: color,
            active: active,
            reversed: reversed
        )
        // FlowParticle + labels used to live here, but they were getting
        // rasterized by the enclosing drawingGroup and their onAppear-driven
        // animations never fired. Both are now drawn outside drawingGroup:
        // particles in FlowParticlesLayer, labels in LinkLabelsLayer.
    }
}

/// Sliding glow-dots rendered on top of the dashed flow lines. Lives OUTSIDE
/// the drawingGroup so the `.onAppear` → `withAnimation(.linear…)` driving
/// `FlowParticle.progress` actually runs — drawingGroup rasterizes the subtree
/// and its animation was effectively freezing the dots in place at 0.
private struct FlowParticlesLayer: View {
    let size: CGSize
    let status: InverterStatus

    var body: some View {
        let margin: CGFloat = 86
        let topY = size.height * 0.19
        let botY = size.height * 0.81
        let centerX = size.width * 0.5
        let centerTopY = size.height * 0.38
        let centerBotY = size.height * 0.62
        let inwardGrid    = CGPoint(x: margin + 28, y: topY + 10)
        let inwardLoad    = CGPoint(x: size.width - margin - 28, y: topY + 10)
        let inwardSolar   = CGPoint(x: margin + 28, y: botY - 10)
        let inwardBattery = CGPoint(x: size.width - margin - 28, y: botY - 10)

        return ZStack {
            if status.metrics.grid.inUse {
                FlowParticle(start: inwardGrid, end: CGPoint(x: centerX - 36, y: centerTopY),
                             color: Palette.grid, reversed: false)
            }
            if status.metrics.load.effectivePower > 5 {
                FlowParticle(start: CGPoint(x: centerX + 36, y: centerTopY), end: inwardLoad,
                             color: Palette.load, reversed: false)
            }
            if status.metrics.solar.power > 5 {
                FlowParticle(start: inwardSolar, end: CGPoint(x: centerX - 36, y: centerBotY),
                             color: Palette.solar, reversed: false)
            }
            if status.metrics.battery.direction != .idle {
                FlowParticle(start: CGPoint(x: centerX + 36, y: centerBotY), end: inwardBattery,
                             color: Palette.battery,
                             reversed: status.metrics.battery.direction == .charging)
            }
        }
        // `.allowsHitTesting(false)` so the moving dots don't swallow taps
        // meant for the corner nodes behind them.
        .allowsHitTesting(false)
    }
}

/// Same connection endpoints as ConnectionsLayer but renders *only* the in-flow
/// text labels ("231 W", "Charging 480 W", …). Lives outside the drawingGroup
/// so each label can morph via `.contentTransition(.numericText)` at the
/// 600 ms poll cadence — otherwise the rasterized Metal layer eats the
/// animation and the user sees the numbers snap.
private struct LinkLabelsLayer: View {
    let size: CGSize
    let status: InverterStatus

    var body: some View {
        let margin: CGFloat = 86
        let topY = size.height * 0.19
        let botY = size.height * 0.81
        let centerX = size.width * 0.5
        let centerTopY = size.height * 0.38
        let centerBotY = size.height * 0.62
        let inwardGrid    = CGPoint(x: margin + 28, y: topY + 10)
        let inwardLoad    = CGPoint(x: size.width - margin - 28, y: topY + 10)
        let inwardSolar   = CGPoint(x: margin + 28, y: botY - 10)
        let inwardBattery = CGPoint(x: size.width - margin - 28, y: botY - 10)

        return ZStack {
            if status.metrics.grid.inUse {
                flowLabel(gridLabel, color: Palette.grid,
                          at: midpoint(inwardGrid, CGPoint(x: centerX - 36, y: centerTopY)))
            }
            if status.metrics.load.effectivePower > 5, !loadLabel.isEmpty {
                flowLabel(loadLabel, color: Palette.load,
                          at: midpoint(CGPoint(x: centerX + 36, y: centerTopY), inwardLoad))
            }
            if status.metrics.solar.power > 5, !solarLabel.isEmpty {
                flowLabel(solarLabel, color: Palette.solar,
                          at: midpoint(inwardSolar, CGPoint(x: centerX - 36, y: centerBotY)))
            }
            if status.metrics.battery.direction != .idle {
                flowLabel(batteryLabel, color: Palette.battery,
                          at: midpoint(CGPoint(x: centerX + 36, y: centerBotY), inwardBattery))
            }
        }
    }

    private func flowLabel(_ text: String, color: Color, at point: CGPoint) -> some View {
        Text(text)
            .font(.caption2.bold())
            .foregroundStyle(color)
            .monospacedDigit()
            .contentTransition(.numericText(value: FlowDiagramView.firstNumber(in: text)))
            .animation(.easeOut(duration: 0.35), value: text)
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .background(Color.black.opacity(0.45), in: Capsule())
            .position(point)
    }

    private func midpoint(_ a: CGPoint, _ b: CGPoint) -> CGPoint {
        CGPoint(x: (a.x + b.x) / 2, y: (a.y + b.y) / 2)
    }

    private var gridLabel: String {
        if status.metrics.grid.inUse {
            let w = Int(status.metrics.grid.power.rounded())
            return w > 0 ? "\(w) W" : "In use"
        }
        return "Backup"
    }

    private var loadLabel: String {
        let w = Int(status.metrics.load.effectivePower.rounded())
        return w > 5 ? "\(w) W" : ""
    }

    private var solarLabel: String {
        let w = Int(status.metrics.solar.power.rounded())
        return w > 5 ? "\(w) W" : ""
    }

    private var batteryLabel: String {
        let w = Int(abs(status.metrics.battery.power).rounded())
        switch status.metrics.battery.direction {
        case .charging: return "Charging \(w) W"
        case .discharging: return "Discharging \(w) W"
        case .idle: return "Idle"
        }
    }
}

/// A straight line rendered with a moving dashed stroke to imply flow direction.
private struct AnimatedDashLine: View {
    let start: CGPoint
    let end: CGPoint
    let color: Color
    let active: Bool
    let reversed: Bool

    @State private var phase: CGFloat = 0

    var body: some View {
        Line(start: start, end: end)
            .stroke(
                color.opacity(active ? 1 : 0.35),
                style: StrokeStyle(
                    lineWidth: 4,
                    lineCap: .round,
                    lineJoin: .round,
                    dash: active ? [8, 6] : [2, 4],
                    dashPhase: active ? (reversed ? -phase : phase) : 0
                )
            )
            .onAppear {
                if active { startAnimating() }
            }
            .onChange(of: active) { _, isActive in
                if isActive {
                    startAnimating()
                } else {
                    withAnimation(.default) { phase = 0 }
                }
            }
    }

    private func startAnimating() {
        withAnimation(.linear(duration: 1.4).repeatForever(autoreverses: false)) {
            phase = 28
        }
    }
}

private struct Line: Shape {
    let start: CGPoint
    let end: CGPoint

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: start)
        path.addLine(to: end)
        return path
    }
}

/// A small glowing dot that slides repeatedly from `start` to `end` (or the reverse),
/// echoing the `energy-particle` <circle animateMotion> in the web SVG.
struct FlowParticle: View {
    let start: CGPoint
    let end: CGPoint
    let color: Color
    let reversed: Bool

    @State private var progress: CGFloat = 0

    var body: some View {
        let t = reversed ? (1 - progress) : progress
        let x = start.x + (end.x - start.x) * t
        let y = start.y + (end.y - start.y) * t
        Circle()
            .fill(color)
            .frame(width: 7, height: 7)
            .shadow(color: color, radius: 5)
            .position(x: x, y: y)
            .onAppear {
                progress = 0
                withAnimation(.linear(duration: 2).repeatForever(autoreverses: false)) {
                    progress = 1
                }
            }
    }
}
