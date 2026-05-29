import SwiftUI

struct LiveDashboardView: View {
    @EnvironmentObject var live: LiveDashboardViewModel
    @State private var selectedComponent: FlowComponent?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    header
                    if live.showWarningsBanner {
                        WarningsBanner(
                            warnings: live.activeWarnings,
                            onDismiss: { live.dismissedWarnings = true }
                        )
                    }
                    FlowDiagramView(status: live.status) { component in
                        selectedComponent = component
                    }
                    PowerCardsGrid(metrics: live.status.metrics, showEstimated: live.status.metrics.grid.inUse)
                    TodaySummarySection(
                        summary: live.summary,
                        monthStats: live.monthStats,
                        yearStats: live.yearStats
                    )
                    SystemInfoGrid(live: live)
                    LivePowerChartSection(
                        readings: live.recentReadings,
                        liveTail: live.liveTail,
                        range: Binding(get: { live.liveRange }, set: { live.liveRange = $0 }),
                        isLoading: live.isLoadingRecent
                    )
                }
                .padding(.horizontal, 16)
                .padding(.top, 8)
                .padding(.bottom, 40)
                // The 600 ms status tick republishes `live.status` and
                // `live.liveTail` — attaching a nil animation to each of those
                // keyed change events prevents SwiftUI from cascading an
                // implicit animation transaction down the whole scroll-view
                // subtree. The explicit `.animation(.easeOut, value: value)`
                // we apply directly to each numeric Text view still runs,
                // because those are scoped to the Text and not inherited from
                // here. Without this guard, every poll tick ran an implicit
                // animation on the overall layout, which during a bottom-edge
                // scroll bounce manifested as Today / power cards visibly
                // escaping their cells.
                .animation(nil, value: live.status)
                .animation(nil, value: live.liveTail)
                .animation(nil, value: live.recentReadings)
                // Tap anywhere in the scroll surface that isn't the chart
                // itself — cards, flow diagram, empty padding — dismisses a
                // lingering crosshair + tooltip. The chart's own overlay has
                // a higher-priority DragGesture so it still handles its own
                // pointer events first.
                .contentShape(Rectangle())
                .onTapGesture {
                    LivePowerChartSection.broadcastDismiss()
                }
            }
            .scrollIndicators(.hidden)
            // Must keep bouncing enabled in both axes — `.refreshable` relies on
            // the pull-past-top overscroll to trigger. The bottom-edge jitter
            // we used to see on force-flick is now mostly fixed by moving the
            // FlowDiagram's per-poll text out of its drawingGroup.
            .refreshable {
                _ = await live.fetchStatus()
                await live.fetchStats()
                await live.loadRecentReadings()
            }
            .immersiveBackground()
            .navigationTitle("Inverter Monitor")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    RefreshToolbarButton(isRefreshing: live.isRefreshingExtras) {
                        Task { await live.refreshExtras() }
                    }
                }
            }
            .sheet(item: $selectedComponent) { component in
                ComponentDetailSheet(component: component)
                    .presentationDetents([.medium, .large])
                    .presentationDragIndicator(.visible)
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Image(systemName: "sun.max.fill")
                    .font(.title2)
                    .foregroundStyle(Palette.solar)
                VStack(alignment: .leading, spacing: 0) {
                    Text("Solar Energy System")
                        .font(.title3.bold())
                        .foregroundStyle(.white)
                    Text("Real-time status")
                        .font(.caption)
                        .foregroundStyle(Palette.subtleText)
                }
                Spacer(minLength: 0)
            }

            // Mode/charge/grid pills can add up to more width than the viewport on
            // narrow screens (iPhone SE, split-view) and the SwiftUI HStack wraps
            // into an ugly second line. A horizontal ScrollView keeps every pill
            // on one row, lets the user pan to the overflow, and hides scroll
            // indicators so the row still looks like a static chip strip.
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ModePill(system: live.status.system)
                        .fixedSize()
                    if live.status.system.chargeStage != .idle {
                        StatusPill(
                            label: live.status.system.chargeStage.label,
                            systemImage: "bolt.fill",
                            tint: Color.green,
                            backgroundTint: Palette.batteryFill
                        )
                        .fixedSize()
                    }
                    if live.status.system.isAcChargingOn || live.status.metrics.grid.inUse {
                        StatusPill(
                            label: live.gridFlowLabel.isEmpty ? "Grid" : live.gridFlowLabel,
                            systemImage: "powerplug.fill",
                            tint: Color.blue,
                            backgroundTint: Palette.gridFill
                        )
                        .fixedSize()
                    }
                }
                // A tiny trailing pad so the last pill doesn't kiss the screen edge
                // when the user has scrolled it fully into view.
                .padding(.trailing, 4)
            }
            .scrollClipDisabled()
        }
    }
}

struct ModePill: View {
    let system: SystemInfo

    var body: some View {
        let style = ModePillStyle.style(for: system.mode)
        let tint = hexColor(style.primary)
        let bg = hexColor(style.background).opacity(0.35)
        let dot = hexColor(style.dot)
        StatusPill(
            label: system.modeLabel.isEmpty ? style.label : system.modeLabel,
            tint: tint,
            backgroundTint: bg,
            dotColor: dot,
            dashed: system.modeSource == "derived"
        )
    }

    private func hexColor(_ hex: String) -> Color {
        let cleaned = hex.replacingOccurrences(of: "#", with: "")
        guard cleaned.count == 6, let rgb = Int(cleaned, radix: 16) else { return .gray }
        let r = Double((rgb >> 16) & 0xFF) / 255
        let g = Double((rgb >> 8) & 0xFF) / 255
        let b = Double(rgb & 0xFF) / 255
        return Color(red: r, green: g, blue: b)
    }
}

struct WarningsBanner: View {
    let warnings: [InverterWarning]
    let onDismiss: () -> Void

    var body: some View {
        let hasFault = warnings.contains { $0.severity == .fault }
        let accent = hasFault ? Color.red : Color.orange
        return HStack(alignment: .top, spacing: 10) {
            Image(systemName: hasFault ? "exclamationmark.octagon.fill" : "exclamationmark.triangle.fill")
                .foregroundStyle(accent)
            VStack(alignment: .leading, spacing: 4) {
                Text(
                    hasFault
                    ? "\(warnings.count) active fault\(warnings.count == 1 ? "" : "s")"
                    : "\(warnings.count) active warning\(warnings.count == 1 ? "" : "s")"
                )
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                Text(warnings.map(\.label).joined(separator: " · "))
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.9))
            }
            Spacer(minLength: 0)
            Button {
                onDismiss()
            } label: {
                Image(systemName: "xmark")
                    .foregroundStyle(.white.opacity(0.7))
            }
            .buttonStyle(.plain)
        }
        .padding(12)
        .background(accent.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(accent.opacity(0.4))
        )
    }
}
