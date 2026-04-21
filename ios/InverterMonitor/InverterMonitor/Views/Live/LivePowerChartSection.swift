import SwiftUI
import Charts

struct LivePowerChartSection: View {
    let readings: RecentReadings
    @Binding var range: LiveDashboardViewModel.LiveRange
    let isLoading: Bool

    /// Current drag position on the chart. When non-nil, we render a crosshair
    /// rule-mark + dot markers + a floating tooltip with per-series values.
    @State private var selectedDate: Date?

    private var selectedPoint: RecentReadingPoint? {
        guard let selectedDate, !readings.points.isEmpty else { return nil }
        // Snap to the nearest bucket — server-side bucketing already quantizes x.
        return readings.points.min(by: {
            abs($0.date.timeIntervalSince(selectedDate)) < abs($1.date.timeIntervalSince(selectedDate))
        })
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Live Power")
                    .font(.headline)
                    .foregroundStyle(.white)
                Spacer(minLength: 0)
                rangePicker
            }

            if readings.points.isEmpty {
                EmptyChartState(loading: isLoading)
            } else {
                // Chart auto-fits the points' date range; new polls bring new rightmost points,
                // which slides naturally. We removed the 1 Hz TimelineView rebuild that was
                // causing the whole list view to jitter while scrolling.
                chart.frame(height: 260)
            }

            legend
        }
        .padding(14)
        .card()
    }

    private var rangePicker: some View {
        HStack(spacing: 0) {
            ForEach(LiveDashboardViewModel.LiveRange.allCases) { option in
                Button {
                    range = option
                } label: {
                    Text(option.label)
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .foregroundStyle(range == option ? .white : Palette.mutedText)
                        .background(range == option ? Color.blue : Color.clear)
                }
                .buttonStyle(.plain)
            }
        }
        .background(Color.white.opacity(0.06), in: Capsule())
        .overlay(Capsule().strokeBorder(Palette.cardBorder))
    }

    private var chart: some View {
        Chart {
            ForEach(readings.points) { point in
                LineMark(
                    x: .value("Time", point.date),
                    y: .value("W", point.solarAvg),
                    series: .value("Series", "Solar")
                )
                .foregroundStyle(by: .value("Series", "Solar"))
                .interpolationMethod(.catmullRom)
            }
            ForEach(readings.points) { point in
                LineMark(
                    x: .value("Time", point.date),
                    y: .value("W", point.gridAvg),
                    series: .value("Series", "Grid")
                )
                .foregroundStyle(by: .value("Series", "Grid"))
                .interpolationMethod(.catmullRom)
            }
            ForEach(readings.points) { point in
                LineMark(
                    x: .value("Time", point.date),
                    y: .value("W", point.loadAvg),
                    series: .value("Series", "Load")
                )
                .foregroundStyle(by: .value("Series", "Load"))
                .interpolationMethod(.catmullRom)
            }
            ForEach(readings.points) { point in
                LineMark(
                    x: .value("Time", point.date),
                    y: .value("W", point.batteryAvg),
                    series: .value("Series", "Battery")
                )
                .foregroundStyle(by: .value("Series", "Battery"))
                .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [4, 3]))
                .interpolationMethod(.catmullRom)
            }

            // Crosshair + series dots + floating tooltip appear only while dragging.
            if let point = selectedPoint {
                RuleMark(x: .value("Time", point.date))
                    .foregroundStyle(Color.white.opacity(0.35))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                    .annotation(position: .top, spacing: 4, overflowResolution: .init(x: .fit, y: .disabled)) {
                        CrosshairTooltip(point: point)
                    }

                PointMark(x: .value("Time", point.date), y: .value("W", point.solarAvg))
                    .foregroundStyle(Palette.solar)
                    .symbolSize(60)
                PointMark(x: .value("Time", point.date), y: .value("W", point.gridAvg))
                    .foregroundStyle(Palette.grid)
                    .symbolSize(60)
                PointMark(x: .value("Time", point.date), y: .value("W", point.loadAvg))
                    .foregroundStyle(Palette.load)
                    .symbolSize(60)
                PointMark(x: .value("Time", point.date), y: .value("W", point.batteryAvg))
                    .foregroundStyle(Palette.battery)
                    .symbolSize(60)
            }
        }
        .chartForegroundStyleScale([
            "Solar": Palette.solar,
            "Grid": Palette.grid,
            "Load": Palette.load,
            "Battery": Palette.battery
        ])
        .chartLegend(.hidden)
        // Apple's built-in `.chartXSelection` requires a long-press-drag on iOS 17,
        // which is unintuitive. An overlay with a minimumDistance:0 DragGesture fires
        // immediately on tap AND follows a drag — much more expected behavior.
        .chartOverlay { proxy in
            GeometryReader { geo in
                Rectangle().fill(.clear).contentShape(Rectangle())
                    .gesture(
                        DragGesture(minimumDistance: 0)
                            .onChanged { value in
                                let frame = geo[proxy.plotFrame!]
                                let x = value.location.x - frame.origin.x
                                guard x >= 0, x <= frame.size.width else { return }
                                if let date: Date = proxy.value(atX: x) {
                                    selectedDate = date
                                }
                            }
                            .onEnded { _ in }
                    )
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5)).foregroundStyle(Palette.cardBorder)
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text("\(Int(v.rounded())) W")
                            .font(.caption2)
                            .foregroundStyle(Palette.mutedText)
                    }
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 5)) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5)).foregroundStyle(Palette.cardBorder)
                AxisValueLabel {
                    if let d = value.as(Date.self) {
                        Text(Self.timeFormatter.string(from: d))
                            .font(.caption2)
                            .foregroundStyle(Palette.mutedText)
                    }
                }
            }
        }
    }

    private var legend: some View {
        HStack(spacing: 16) {
            LegendDot(color: Palette.solar, label: "Solar")
            LegendDot(color: Palette.grid, label: "Grid")
            LegendDot(color: Palette.load, label: "Load")
            LegendDot(color: Palette.battery, label: "Battery", dashed: true)
        }
        .font(.caption2)
    }

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        return f
    }()
}

/// Floating tooltip that appears above the crosshair showing per-series values for
/// the selected bucket. Time is formatted in the user's locale.
private struct CrosshairTooltip: View {
    let point: RecentReadingPoint

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(Self.timeFormatter.string(from: point.date))
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.white)
            row(color: Palette.solar, label: "Solar", value: point.solarAvg)
            row(color: Palette.grid, label: "Grid", value: point.gridAvg)
            row(color: Palette.load, label: "Load", value: point.loadAvg)
            row(color: Palette.battery, label: "Battery", value: point.batteryAvg)
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 7)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.black.opacity(0.85))
                .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Color.white.opacity(0.15)))
        )
    }

    private func row(color: Color, label: String, value: Double) -> some View {
        HStack(spacing: 6) {
            RoundedRectangle(cornerRadius: 1.5).fill(color).frame(width: 10, height: 3)
            Text(label).foregroundStyle(.white.opacity(0.75)).font(.caption2)
            Spacer(minLength: 8)
            Text("\(Int(value.rounded())) W")
                .foregroundStyle(.white)
                .font(.caption2.weight(.semibold))
                .monospacedDigit()
        }
    }

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f
    }()
}

private struct LegendDot: View {
    let color: Color
    let label: String
    var dashed: Bool = false

    var body: some View {
        HStack(spacing: 4) {
            RoundedRectangle(cornerRadius: 2)
                .fill(color)
                .frame(width: 16, height: 3)
                .overlay(
                    dashed
                    ? RoundedRectangle(cornerRadius: 2)
                        .strokeBorder(color, style: StrokeStyle(lineWidth: 1, dash: [2, 2]))
                    : nil
                )
            Text(label)
                .foregroundStyle(Palette.mutedText)
        }
    }
}

private struct EmptyChartState: View {
    let loading: Bool

    var body: some View {
        VStack(spacing: 10) {
            if loading {
                ProgressView().tint(.white)
            } else {
                Image(systemName: "chart.line.downtrend.xyaxis")
                    .font(.title)
                    .foregroundStyle(Palette.subtleText)
            }
            Text(loading ? "Loading…" : "No data yet")
                .font(.footnote)
                .foregroundStyle(Palette.subtleText)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 240)
    }
}
