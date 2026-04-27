import SwiftUI

struct OutagesReportView: View {
    @EnvironmentObject var reports: ReportsViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            controls
            PhaseIndicator(phase: reports.outagesPhase)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
                SummaryKpi(title: "Outages", tint: Color.red,
                           value: "\(reports.outages.count)", subtitle: "count")
                SummaryKpi(title: "Downtime", tint: Color.orange,
                           value: String(format: "%.2f", Double(reports.outages.totalDownSeconds) / 3600.0),
                           subtitle: "hours")
                SummaryKpi(title: "Availability", tint: Color.mint,
                           value: String(format: "%.2f", reports.outages.availability * 100),
                           subtitle: "%")
            }

            VStack(alignment: .leading, spacing: 10) {
                Text("Outage List")
                    .font(.headline)
                    .foregroundStyle(.white)
                if reports.outages.outages.isEmpty {
                    HStack {
                        Spacer()
                        VStack(spacing: 8) {
                            Image(systemName: "checkmark.seal.fill")
                                .font(.title)
                                .foregroundStyle(Color.mint)
                            Text("No outages in this range")
                                .font(.footnote)
                                .foregroundStyle(Palette.subtleText)
                        }
                        Spacer()
                    }
                    .frame(minHeight: 140)
                } else {
                    VStack(spacing: 0) {
                        ForEach(reports.outages.outages) { outage in
                            OutageRow(outage: outage)
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
                DatePicker("", selection: $reports.outagesFrom, displayedComponents: .date)
                    .labelsHidden()
                Text("To")
                    .font(.caption)
                    .foregroundStyle(Palette.subtleText)
                DatePicker("", selection: $reports.outagesTo, displayedComponents: .date)
                    .labelsHidden()
                Button("Apply") { Task { await reports.loadOutages() } }
                    .buttonStyle(.borderedProminent)
            }
            HStack(spacing: 8) {
                Button("7d") { Task { await reports.applyOutagePreset(days: 7) } }
                    .buttonStyle(.bordered)
                Button("30d") { Task { await reports.applyOutagePreset(days: 30) } }
                    .buttonStyle(.bordered)
                Spacer(minLength: 0)
            }
        }
        .padding(12)
        .card()
    }
}

private struct OutageRow: View {
    let outage: Outage

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(Self.fmt.string(from: outage.startDate))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white)
                Text(Self.fmt.string(from: outage.endDate))
                    .font(.caption2)
                    .foregroundStyle(Palette.subtleText)
            }
            Spacer(minLength: 0)
            Text(formatDuration(outage.durationSeconds))
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
