import SwiftUI
import Charts
import UniformTypeIdentifiers

struct DayReportView: View {
    @EnvironmentObject var reports: ReportsViewModel
    @State private var showExportDialog = false
    @State private var exportItem: ExportDocumentItem?
    @State private var selectedDate: Date?

    private var selectedPoint: DayReadingPoint? {
        guard let selectedDate, !reports.dayReadings.points.isEmpty else { return nil }
        return reports.dayReadings.points.min(by: {
            abs($0.date.timeIntervalSince(selectedDate)) < abs($1.date.timeIntervalSince(selectedDate))
        })
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            controls
            PhaseIndicator(phase: reports.dayPhase)
            summaryGrid
            chart
            if let err = reports.exportError {
                ToastBanner(message: err, style: .error)
            }
        }
        .confirmationDialog("Export day", isPresented: $showExportDialog, titleVisibility: .visible) {
            Button("Raw 3s · CSV") { doExport(format: .csv, bucket: nil) }
            Button("Raw 3s · JSON") { doExport(format: .json, bucket: nil) }
            Button("1-min · CSV") { doExport(format: .csv, bucket: 60) }
            Button("1-min · JSON") { doExport(format: .json, bucket: 60) }
            Button("5-min · CSV") { doExport(format: .csv, bucket: 300) }
            Button("5-min · JSON") { doExport(format: .json, bucket: 300) }
            Button("Cancel", role: .cancel) { }
        }
        .sheet(item: $exportItem) { item in
            ShareSheet(url: item.url)
                .presentationDetents([.medium, .large])
        }
    }

    private var controls: some View {
        VStack(spacing: 10) {
            HStack(spacing: 8) {
                Button {
                    Task { await reports.shiftDay(by: -1) }
                } label: {
                    Image(systemName: "chevron.left")
                }
                .buttonStyle(.bordered)

                DatePicker("", selection: $reports.dayDate, displayedComponents: .date)
                    .labelsHidden()
                    .onChange(of: reports.dayDate) { _, _ in
                        Task { await reports.loadDay() }
                    }

                Button {
                    Task { await reports.shiftDay(by: 1) }
                } label: {
                    Image(systemName: "chevron.right")
                }
                .buttonStyle(.bordered)

                Button("Today") {
                    Task { await reports.jumpToToday() }
                }
                .buttonStyle(.borderedProminent)

                Spacer(minLength: 0)

                Button {
                    showExportDialog = true
                } label: {
                    Image(systemName: "square.and.arrow.up")
                }
                .buttonStyle(.bordered)
            }
        }
        .padding(12)
        .card()
    }

    private var summaryGrid: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
            SummaryKpi(title: "Solar", tint: Palette.solar,
                       value: kwh(reports.daySummary.solarKwh),
                       subtitle: "Peak \(Int(reports.daySummary.solarPeakW.rounded()))W")
            SummaryKpi(title: "Grid Import", tint: Palette.grid,
                       value: kwh(reports.daySummary.gridKwh),
                       subtitle: "Peak \(Int(reports.daySummary.gridPeakW.rounded()))W")
            SummaryKpi(title: "Load", tint: Palette.load,
                       value: kwh(reports.daySummary.loadKwh),
                       subtitle: "Peak \(Int(reports.daySummary.loadPeakW.rounded()))W")
            SummaryKpi(title: "Bat. +/-", tint: Palette.battery,
                       value: "\(kwh(reports.daySummary.batteryChargeKwh)) / \(kwh(reports.daySummary.batteryDischargeKwh))",
                       subtitle: "kWh")
            SummaryKpi(title: "Self-Sufficiency", tint: Color.mint,
                       value: "\(Int((reports.daySummary.selfSufficiency * 100).rounded()))%",
                       subtitle: "Solar share \(Int((reports.daySummary.solarFraction * 100).rounded()))%")
        }
    }

    private var chart: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Power Timeline")
                .font(.headline)
                .foregroundStyle(.white)
            if reports.dayReadings.points.isEmpty {
                placeholderChart
            } else {
                Chart {
                    ForEach(reports.dayReadings.points) { p in
                        LineMark(
                            x: .value("Time", p.date),
                            y: .value("Solar", p.solarPower),
                            series: .value("Series", "Solar")
                        )
                        .foregroundStyle(by: .value("Series", "Solar"))
                        .interpolationMethod(.catmullRom)
                    }
                    ForEach(reports.dayReadings.points) { p in
                        LineMark(
                            x: .value("Time", p.date),
                            y: .value("Grid", p.gridPower),
                            series: .value("Series", "Grid")
                        )
                        .foregroundStyle(by: .value("Series", "Grid"))
                        .interpolationMethod(.catmullRom)
                    }
                    ForEach(reports.dayReadings.points) { p in
                        LineMark(
                            x: .value("Time", p.date),
                            y: .value("Load", p.loadPower),
                            series: .value("Series", "Load")
                        )
                        .foregroundStyle(by: .value("Series", "Load"))
                        .interpolationMethod(.catmullRom)
                    }
                    ForEach(reports.dayReadings.points) { p in
                        LineMark(
                            x: .value("Time", p.date),
                            y: .value("Battery", p.batteryPower),
                            series: .value("Series", "Battery")
                        )
                        .foregroundStyle(by: .value("Series", "Battery"))
                        .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [4, 3]))
                        .interpolationMethod(.catmullRom)
                    }

                    if let p = selectedPoint {
                        RuleMark(x: .value("Time", p.date))
                            .foregroundStyle(Color.white.opacity(0.35))
                            .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                            .annotation(position: .top, spacing: 4, overflowResolution: .init(x: .fit, y: .disabled)) {
                                DayCrosshairTooltip(point: p)
                            }
                        PointMark(x: .value("Time", p.date), y: .value("W", p.solarPower))
                            .foregroundStyle(Palette.solar).symbolSize(60)
                        PointMark(x: .value("Time", p.date), y: .value("W", p.gridPower))
                            .foregroundStyle(Palette.grid).symbolSize(60)
                        PointMark(x: .value("Time", p.date), y: .value("W", p.loadPower))
                            .foregroundStyle(Palette.load).symbolSize(60)
                        PointMark(x: .value("Time", p.date), y: .value("W", p.batteryPower))
                            .foregroundStyle(Palette.battery).symbolSize(60)
                    }
                }
                .chartForegroundStyleScale([
                    "Solar": Palette.solar,
                    "Grid": Palette.grid,
                    "Load": Palette.load,
                    "Battery": Palette.battery
                ])
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
                .frame(height: 320)
                .chartYAxis {
                    AxisMarks(position: .leading) { value in
                        AxisGridLine().foregroundStyle(Palette.cardBorder)
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
                    AxisMarks(values: .automatic(desiredCount: 6)) { value in
                        AxisGridLine().foregroundStyle(Palette.cardBorder)
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
        }
        .padding(14)
        .card()
    }

    private var placeholderChart: some View {
        VStack(spacing: 10) {
            Image(systemName: "chart.line.uptrend.xyaxis")
                .font(.title2)
                .foregroundStyle(Palette.subtleText)
            Text("No readings for this day")
                .font(.footnote)
                .foregroundStyle(Palette.subtleText)
        }
        .frame(maxWidth: .infinity, minHeight: 240)
    }

    private func kwh(_ v: Double) -> String {
        String(format: "%.2f", v)
    }

    private func doExport(format: InverterService.ExportFormat, bucket: Int?) {
        Task {
            guard let result = await reports.exportDay(format: format, bucketSeconds: bucket) else { return }
            let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(result.filename)
            try? result.data.write(to: tmp)
            await MainActor.run {
                exportItem = ExportDocumentItem(url: tmp)
            }
        }
    }

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        return f
    }()
}

/// Crosshair tooltip for the Day report line chart.
private struct DayCrosshairTooltip: View {
    let point: DayReadingPoint
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(Self.timeFormatter.string(from: point.date))
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.white)
            row(color: Palette.solar, label: "Solar", value: point.solarPower)
            row(color: Palette.grid, label: "Grid", value: point.gridPower)
            row(color: Palette.load, label: "Load", value: point.loadPower)
            row(color: Palette.battery, label: "Battery", value: point.batteryPower)
            HStack(spacing: 6) {
                Image(systemName: "battery.50")
                    .foregroundStyle(Palette.battery)
                    .font(.caption2)
                Text("SoC \(Int(point.batteryPercentage.rounded()))%")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.white)
                    .monospacedDigit()
            }
            .padding(.top, 2)
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
        f.dateFormat = "HH:mm"
        return f
    }()
}

struct SummaryKpi: View {
    let title: String
    let tint: Color
    let value: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(tint)
            Text(value)
                .font(.system(size: 20, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
                .monospacedDigit()
                .contentTransition(.numericText(value: Double(value) ?? 0))
                .animation(.easeOut(duration: 0.35), value: value)
            Text(subtitle)
                .font(.caption2)
                .foregroundStyle(Palette.subtleText)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .card()
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title) \(value). \(subtitle)")
    }
}

struct ExportDocumentItem: Identifiable {
    let id = UUID()
    let url: URL
}

/// SwiftUI-native share sheet wrapper. Prefers `ShareLink` for typical flows but we
/// present from a sheet because the trigger is a confirmation dialog choice, not a button.
struct ShareSheet: View {
    let url: URL
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(url.lastPathComponent)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer()
                Button("Done") { dismiss() }
            }
            .padding()
            Divider()
            ShareLink(item: url) {
                Label("Share export", systemImage: "square.and.arrow.up")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(Color.blue, in: RoundedRectangle(cornerRadius: 12))
                    .foregroundStyle(.white)
                    .padding()
            }
            Spacer()
        }
        .background(Palette.backgroundTop)
        .preferredColorScheme(.dark)
    }
}
