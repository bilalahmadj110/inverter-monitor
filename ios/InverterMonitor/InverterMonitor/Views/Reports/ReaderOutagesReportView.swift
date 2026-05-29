import SwiftUI

/// Reader Outages report — periods where the Pi-side continuous reader wasn't
/// producing data. Mirrors the web's "Reader Outages" tab (distinct from Grid
/// Outages, which tracks AC voltage drops). Useful for spotting Pi reboots,
/// USB disconnects, or systemd service restarts.
struct ReaderOutagesReportView: View {
    @EnvironmentObject var reports: ReportsViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            controls
            PhaseIndicator(phase: reports.readerOutagesPhase)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
                SummaryKpi(title: "Gaps", tint: Color.red,
                           value: "\(reports.readerOutages.count)", subtitle: "count")
                SummaryKpi(title: "Downtime", tint: Color.orange,
                           value: String(format: "%.2f", Double(reports.readerOutages.totalDownSeconds) / 3600.0),
                           subtitle: "hours")
                SummaryKpi(title: "Availability", tint: Color.mint,
                           value: String(format: "%.2f", reports.readerOutages.availability * 100),
                           subtitle: "%")
                SummaryKpi(title: "Threshold", tint: Palette.grid,
                           value: "\(reports.readerOutages.thresholdSeconds)",
                           subtitle: "seconds")
            }

            VStack(alignment: .leading, spacing: 10) {
                Text("Gap List")
                    .font(.headline)
                    .foregroundStyle(.white)
                if reports.readerOutages.gaps.isEmpty {
                    HStack {
                        Spacer()
                        VStack(spacing: 8) {
                            Image(systemName: "checkmark.seal.fill")
                                .font(.title)
                                .foregroundStyle(Color.mint)
                            Text("Reader was up the whole window")
                                .font(.footnote)
                                .foregroundStyle(Palette.subtleText)
                        }
                        Spacer()
                    }
                    .frame(minHeight: 140)
                } else {
                    VStack(spacing: 0) {
                        ForEach(reports.readerOutages.gaps) { gap in
                            GapRow(gap: gap)
                        }
                    }
                }
            }
            .padding(14)
            .card()
        }
    }

    private var controls: some View {
        VStack(spacing: 10) {
            HStack(spacing: 8) {
                Text("From")
                    .font(.caption)
                    .foregroundStyle(Palette.subtleText)
                DatePicker("", selection: $reports.readerOutagesFrom, displayedComponents: .date)
                    .labelsHidden()
                Text("To")
                    .font(.caption)
                    .foregroundStyle(Palette.subtleText)
                DatePicker("", selection: $reports.readerOutagesTo, displayedComponents: .date)
                    .labelsHidden()
                Spacer(minLength: 0)
            }
            HStack(spacing: 8) {
                Button("7d") { Task { await reports.applyReaderOutagePreset(days: 7) } }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                Button("30d") { Task { await reports.applyReaderOutagePreset(days: 30) } }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                Spacer(minLength: 0)
                Button("Apply") { Task { await reports.loadReaderOutages() } }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
            }
        }
        .padding(12)
        .card()
    }
}

private struct GapRow: View {
    let gap: DataGap

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(Self.fmt.string(from: gap.startDate))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white)
                Text(Self.fmt.string(from: gap.endDate))
                    .font(.caption2)
                    .foregroundStyle(Palette.subtleText)
            }
            Spacer(minLength: 0)
            Text(formatDuration(gap.durationSeconds))
                .font(.footnote.monospacedDigit())
                .foregroundStyle(Color.orange)
        }
        .padding(.vertical, 8)
        .overlay(Rectangle().frame(height: 1).foregroundStyle(Palette.divider), alignment: .bottom)
    }

    private func formatDuration(_ seconds: Int) -> String {
        if seconds < 60 { return "\(seconds)s" }
        let mins = seconds / 60
        let secs = seconds % 60
        if mins < 60 { return secs > 0 ? "\(mins)m \(secs)s" : "\(mins)m" }
        let hours = mins / 60
        let remMin = mins % 60
        return remMin > 0 ? "\(hours)h \(remMin)m" : "\(hours)h"
    }

    private static let fmt: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .short
        return f
    }()
}
