import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var live: LiveDashboardViewModel
    @EnvironmentObject var reports: ReportsViewModel
    @Environment(\.scenePhase) private var scenePhase

    enum TabSelection: Hashable { case live, reports, settings }
    @State private var selection: TabSelection = .live

    var body: some View {
        TabView(selection: $selection) {
            LiveDashboardView()
                .tabItem { Label("Live", systemImage: "bolt.circle.fill") }
                .tag(TabSelection.live)
            ReportsView()
                .tabItem { Label("Reports", systemImage: "chart.bar.xaxis") }
                .tag(TabSelection.reports)
            SettingsView()
                .tabItem { Label("Settings", systemImage: "gearshape.fill") }
                .tag(TabSelection.settings)
        }
        .tint(Palette.solar)
        .task { live.start() }
        .onDisappear { live.stop() }
        .onChange(of: scenePhase) { _, phase in
            // Pause network polling only when fully backgrounded. `.inactive` fires
            // briefly during task-switcher, Control Center, etc. — cycling polling
            // there would waste fetches on a transient state.
            switch phase {
            case .active:
                live.start()
                Task { _ = await live.fetchStatus(); await live.fetchStats() }
            case .background:
                live.stop()
            default:
                break
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .inverterOpenDayReport)) { note in
            if let date = note.object as? Date {
                selection = .reports
                Task {
                    await reports.loadDay(date: date)
                }
            }
        }
    }
}

extension Notification.Name {
    /// Fired when another part of the app asks to jump to the Reports > Day tab
    /// for a specific date (e.g. tapping the Today summary card on Live).
    static let inverterOpenDayReport = Notification.Name("InverterOpenDayReport")
}
