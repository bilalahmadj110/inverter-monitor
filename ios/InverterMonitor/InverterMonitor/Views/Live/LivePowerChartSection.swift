import SwiftUI
import Charts

struct LivePowerChartSection: View {
    let readings: RecentReadings
    /// Per-poll live ticks captured at the 600ms status cadence. The chart
    /// merges these onto the tail of `readings.points` so the line slides
    /// forward in near-real-time, matching the web dashboard's socket-driven
    /// live append behavior.
    let liveTail: [LiveTick]
    @Binding var range: LiveDashboardViewModel.LiveRange
    let isLoading: Bool

    /// Current drag position on the chart. When non-nil, we render a crosshair
    /// rule-mark + dot markers + a floating tooltip with per-series values.
    @State private var selectedDate: Date?

    /// Fired by LiveDashboardView when the user taps anywhere outside the
    /// chart so a stale crosshair doesn't linger if the user releases and
    /// switches focus to another card.
    private static let dismissNotification = Notification.Name("InverterLiveChartDismissCrosshair")

    static func broadcastDismiss() {
        NotificationCenter.default.post(name: dismissNotification, object: nil)
    }

    /// Points shown on the chart: the server-side bucketed history followed by
    /// the rolling live-tick tail. Live ticks convert into `RecentReadingPoint`
    /// so the crosshair / tooltip logic stays uniform across both sources.
    private var mergedPoints: [RecentReadingPoint] {
        var merged = readings.points
        let serverTail = merged.last?.timestamp ?? 0
        for tick in liveTail where tick.timestamp > serverTail {
            merged.append(tick.asReadingPoint)
        }
        return merged
    }

    private var selectedPoint: RecentReadingPoint? {
        let pts = mergedPoints
        guard let selectedDate, !pts.isEmpty else { return nil }
        // Snap to the nearest bucket — server-side bucketing already quantizes x.
        return pts.min(by: {
            abs($0.date.timeIntervalSince(selectedDate)) < abs($1.date.timeIntervalSince(selectedDate))
        })
    }

    /// Same threshold the web dashboard uses (READER_GAP_MS). Any inter-bucket gap
    /// larger than this is treated as a real reader outage and breaks the line;
    /// smaller gaps stay connected so normal polling jitter doesn't look like an
    /// outage.
    private static let outageGapSeconds: TimeInterval = 60

    /// Flat list of points tagged with a segment index. The segment index bumps
    /// whenever two consecutive polled buckets are more than `outageGapSeconds`
    /// apart, so SwiftUI Charts renders each segment as its own LineMark series
    /// and leaves a visible gap at real reader outages (the "blank zero line"
    /// the web dashboard shows).
    private var taggedPoints: [TaggedPoint] {
        let pts = mergedPoints
        guard !pts.isEmpty else { return [] }
        var out: [TaggedPoint] = []
        out.reserveCapacity(pts.count)
        var segIndex = 0
        var prev: RecentReadingPoint?
        for point in pts {
            if let last = prev, point.date.timeIntervalSince(last.date) > Self.outageGapSeconds {
                segIndex += 1
            }
            out.append(TaggedPoint(segment: segIndex, point: point))
            prev = point
        }
        return out
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

            if readings.points.isEmpty && liveTail.isEmpty {
                EmptyChartState(loading: isLoading)
            } else {
                // Chart auto-fits the points' date range; new polls bring new rightmost points,
                // which slides naturally. We removed the 1 Hz TimelineView rebuild that was
                // causing the whole list view to jitter while scrolling.
                chart
                    .frame(height: 260)
                    // Snap to new data instantly on every 600 ms liveTail append.
                    // The default Charts implicit mark animation would otherwise
                    // run concurrently with any ScrollView bounce at the bottom
                    // edge, producing a layout feedback loop that pushed the
                    // Today / power cards visibly out of their cells.
                    .animation(nil, value: readings.points)
                    .animation(nil, value: liveTail)
            }

            legend
        }
        .padding(14)
        .card()
        // Isolate the chart section's rendering so any internal re-layout
        // during a live-tick append doesn't bleed animation transactions into
        // neighbouring sections of the scroll view.
        .compositingGroup()
        .onReceive(NotificationCenter.default.publisher(for: Self.dismissNotification)) { _ in
            selectedDate = nil
        }
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
        let tagged = taggedPoints
        return Chart {
            // Each polled bucket emits four LineMarks (solar/grid/load/battery),
            // each carrying a `series` id tagged with a per-bucket segment index.
            // Whenever consecutive buckets straddle a reader outage, the segment
            // index increments, Charts treats the next run as a new series, and
            // a visible gap is drawn — matching the web dashboard's break-on-gap
            // behavior instead of interpolating across a real outage.
            ForEach(tagged) { t in
                LineMark(
                    x: .value("Time", t.point.date),
                    y: .value("W", t.point.solarAvg),
                    series: .value("Series", "Solar-\(t.segment)")
                )
                .foregroundStyle(Palette.solar)
                .interpolationMethod(.catmullRom)
            }
            ForEach(tagged) { t in
                LineMark(
                    x: .value("Time", t.point.date),
                    y: .value("W", t.point.gridAvg),
                    series: .value("Series", "Grid-\(t.segment)")
                )
                .foregroundStyle(Palette.grid)
                .interpolationMethod(.catmullRom)
            }
            ForEach(tagged) { t in
                LineMark(
                    x: .value("Time", t.point.date),
                    y: .value("W", t.point.loadAvg),
                    series: .value("Series", "Load-\(t.segment)")
                )
                .foregroundStyle(Palette.load)
                .interpolationMethod(.catmullRom)
            }
            ForEach(tagged) { t in
                LineMark(
                    x: .value("Time", t.point.date),
                    y: .value("W", t.point.batteryAvg),
                    series: .value("Series", "Battery-\(t.segment)")
                )
                .foregroundStyle(Palette.battery)
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
                            // Lifting the finger — anywhere, inside or outside
                            // the chart — clears the crosshair + tooltip.
                            // Previously the selection was sticky after
                            // release, so the ruler stayed pinned until the
                            // user dragged again.
                            .onEnded { _ in
                                selectedDate = nil
                            }
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

/// A polled bucket carrying the index of its reader segment. Consecutive points
/// in the same segment are connected; a bump in `segment` marks a real outage
/// and leaves a gap in the line chart.
private struct TaggedPoint: Identifiable {
    let segment: Int
    let point: RecentReadingPoint
    var id: TimeInterval { point.timestamp }
}

extension LiveTick {
    /// Bridges a per-poll live tick into the same `RecentReadingPoint` shape the
    /// server returns so the chart + crosshair logic doesn't need to branch on
    /// source. Min/Max collapse to the instantaneous value — live ticks aren't
    /// buckets.
    var asReadingPoint: RecentReadingPoint {
        RecentReadingPoint(
            timestamp: timestamp,
            solarAvg: solar, solarMin: solar, solarMax: solar,
            gridAvg: grid, gridMin: grid, gridMax: grid,
            loadAvg: load, loadMin: load, loadMax: load,
            batteryAvg: battery, batteryMin: battery, batteryMax: battery,
            batteryPercentage: batteryPercentage,
            gridVoltage: gridVoltage
        )
    }
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
