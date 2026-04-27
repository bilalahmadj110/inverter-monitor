import SwiftUI

struct RawReadingsView: View {
    @EnvironmentObject var reports: ReportsViewModel
    @State private var selectedReading: RawReading?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            controls
            PhaseIndicator(phase: reports.rawPhase)
            if !reports.rawReadings.data.isEmpty {
                table
                paginator
            } else if reports.rawPhase == .loaded || reports.rawPhase == .empty {
                HStack {
                    Spacer()
                    VStack(spacing: 8) {
                        Image(systemName: "tray").font(.title)
                            .foregroundStyle(Palette.subtleText)
                        Text("No readings recorded yet.")
                            .font(.footnote)
                            .foregroundStyle(Palette.subtleText)
                    }
                    Spacer()
                }
                .frame(minHeight: 160)
                .card()
                .padding(.vertical, 8)
            }
        }
        .sheet(item: $selectedReading) { reading in
            RawReadingDetailSheet(reading: reading)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
    }

    private var controls: some View {
        HStack(spacing: 10) {
            Text("Page size")
                .font(.caption)
                .foregroundStyle(Palette.subtleText)
            Picker("Page size", selection: $reports.rawPageSize) {
                Text("10").tag(10)
                Text("25").tag(25)
                Text("50").tag(50)
                Text("100").tag(100)
            }
            .pickerStyle(.segmented)
            .onChange(of: reports.rawPageSize) { _, _ in
                Task {
                    await reports.goToPage(1)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .card()
    }

    private var table: some View {
        VStack(spacing: 0) {
            header
            ForEach(reports.rawReadings.data) { row in
                rawRow(row)
            }
        }
        .card()
    }

    private var header: some View {
        HStack(spacing: 12) {
            Text("Time").frame(maxWidth: .infinity, alignment: .leading)
            Text("Solar").frame(width: 60, alignment: .trailing)
            Text("Grid").frame(width: 60, alignment: .trailing)
            Text("Load").frame(width: 60, alignment: .trailing)
            Text("Bat %").frame(width: 60, alignment: .trailing)
        }
        .font(.caption2.weight(.semibold))
        .tracking(0.6)
        .foregroundStyle(Palette.subtleText)
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .overlay(Rectangle().frame(height: 1).foregroundStyle(Palette.divider), alignment: .bottom)
    }

    private func rawRow(_ row: RawReading) -> some View {
        Button {
            selectedReading = row
        } label: {
            HStack(spacing: 12) {
                Text(row.timestampFormatted)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .font(.caption)
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Text("\(Int(row.solarPower.rounded()))")
                    .frame(width: 60, alignment: .trailing)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(solarColor(row.solarPower))
                Text("\(Int(row.gridPower.rounded()))")
                    .frame(width: 60, alignment: .trailing)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(Palette.grid)
                Text("\(Int(row.loadPower.rounded()))")
                    .frame(width: 60, alignment: .trailing)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(Palette.load)
                Text("\(Int(row.batteryPercentage.rounded()))%")
                    .frame(width: 60, alignment: .trailing)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(batteryColor(row.batteryPercentage))
                Image(systemName: "chevron.right")
                    .font(.caption2)
                    .foregroundStyle(Palette.subtleText)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .overlay(Rectangle().frame(height: 1).foregroundStyle(Palette.divider), alignment: .bottom)
    }

    /// Matches `dashboard.js:getStatusClass('solar')`: >100W is good, 1-100W warning, 0 dim.
    private func solarColor(_ w: Double) -> Color {
        if w > 100 { return Palette.solar }
        if w > 0 { return Palette.solar.opacity(0.6) }
        return Palette.subtleText
    }

    /// Matches the classic dashboard's battery thresholds: >50% green, 20-50 amber, <20 red.
    private func batteryColor(_ pct: Double) -> Color {
        if pct >= 50 { return Palette.battery }
        if pct >= 20 { return .orange }
        return .red
    }

    private var paginator: some View {
        HStack(spacing: 10) {
            Button {
                Task { await reports.goToPage(1) }
            } label: {
                Image(systemName: "chevron.left.2")
            }
            .buttonStyle(.bordered)
            .disabled(reports.rawReadings.page == 1)

            Button {
                Task { await reports.goToPage(reports.rawReadings.page - 1) }
            } label: {
                Image(systemName: "chevron.left")
            }
            .buttonStyle(.bordered)
            .disabled(reports.rawReadings.page == 1)

            Spacer(minLength: 0)

            Text("Page \(reports.rawReadings.page) of \(max(1, reports.rawReadings.totalPages))")
                .font(.footnote)
                .foregroundStyle(.white)
            Text("(\(reports.rawReadings.totalCount) rows)")
                .font(.caption)
                .foregroundStyle(Palette.subtleText)

            Spacer(minLength: 0)

            Button {
                Task { await reports.goToPage(reports.rawReadings.page + 1) }
            } label: {
                Image(systemName: "chevron.right")
            }
            .buttonStyle(.bordered)
            .disabled(reports.rawReadings.page >= reports.rawReadings.totalPages)

            Button {
                Task { await reports.goToPage(reports.rawReadings.totalPages) }
            } label: {
                Image(systemName: "chevron.right.2")
            }
            .buttonStyle(.bordered)
            .disabled(reports.rawReadings.page >= reports.rawReadings.totalPages)
        }
    }
}
