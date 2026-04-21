import SwiftUI

@main
struct InverterMonitorApp: App {
    @StateObject private var appEnv = AppEnvironment()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appEnv)
                .environmentObject(appEnv.authViewModel)
                .environmentObject(appEnv.liveViewModel)
                .environmentObject(appEnv.reportsViewModel)
                .preferredColorScheme(.dark)
                .tint(.orange)
        }
    }
}
