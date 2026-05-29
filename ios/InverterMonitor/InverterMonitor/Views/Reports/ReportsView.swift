import SwiftUI

struct ReportsView: View {
    @EnvironmentObject var reports: ReportsViewModel
    @State private var tab: ReportsViewModel.Tab = .day

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Segmented Picker wraps labels when there are many tabs on narrow
                // screens. A horizontal ScrollView with chip buttons keeps every
                // tab on a single line and matches the web nav's pill style.
                tabBar
                    .padding(.horizontal, 16)
                    .padding(.top, 8)

                ScrollView {
                    VStack(spacing: 20) {
                        Group {
                            switch tab {
                            case .day: DayReportView()
                            case .month: MonthReportView()
                            case .year: YearReportView()
                            case .outages: OutagesReportView()
                            case .readerOutages: ReaderOutagesReportView()
                            case .raw: RawReadingsView()
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 16)
                    .padding(.bottom, 40)
                }
                .scrollIndicators(.hidden)
            }
            .immersiveBackground()
            .navigationTitle("Reports")
            .task(id: tab) {
                await loadTab()
            }
            .refreshable {
                // Pull-to-refresh reloads the active tab + invalidates the history cache
                // so Month/Year pick up fresh daily rows.
                reports.invalidateHistoryCache()
                await loadTab()
            }
        }
    }

    private var tabBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(ReportsViewModel.Tab.allCases) { candidate in
                    Button {
                        tab = candidate
                    } label: {
                        Text(candidate.title)
                            .font(.footnote.weight(.semibold))
                            .lineLimit(1)
                            .fixedSize()
                            .padding(.horizontal, 12)
                            .padding(.vertical, 7)
                            .foregroundStyle(tab == candidate ? .white : Palette.mutedText)
                            .background(
                                tab == candidate ? Color.blue : Color.white.opacity(0.06),
                                in: Capsule()
                            )
                            .overlay(Capsule().strokeBorder(Palette.cardBorder))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.vertical, 2)
        }
        .scrollClipDisabled()
    }

    private func loadTab() async {
        switch tab {
        case .day: await reports.loadDay()
        case .month: await reports.loadMonth()
        case .year: await reports.loadYear()
        case .outages: await reports.loadOutages()
        case .readerOutages: await reports.loadReaderOutages()
        case .raw: await reports.loadRaw()
        }
    }
}

// MARK: - Phase indicator ---------------------------------------------------

struct PhaseIndicator: View {
    let phase: ReportsViewModel.LoadPhase

    var body: some View {
        switch phase {
        case .idle, .loaded:
            EmptyView()
        case .loading:
            HStack(spacing: 6) {
                ProgressView().tint(Palette.subtleText)
                Text("Loading…")
                    .font(.caption)
                    .foregroundStyle(Palette.subtleText)
            }
            .padding(.vertical, 4)
        case .empty:
            HStack(spacing: 6) {
                Image(systemName: "tray")
                Text("No data for this range")
            }
            .font(.caption)
            .foregroundStyle(Palette.subtleText)
            .padding(.vertical, 4)
        case .error(let msg):
            HStack(spacing: 6) {
                Image(systemName: "exclamationmark.triangle.fill")
                Text(msg).lineLimit(2)
            }
            .font(.caption)
            .foregroundStyle(.red)
            .padding(.vertical, 4)
        }
    }
}
