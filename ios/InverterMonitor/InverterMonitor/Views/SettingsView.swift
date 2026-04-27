import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var appEnv: AppEnvironment
    @EnvironmentObject var auth: AuthViewModel
    @EnvironmentObject var live: LiveDashboardViewModel

    @State private var editingServerURL = false
    @State private var checking = false
    @State private var healthResult: HealthRes?
    @State private var healthError: String?
    @State private var recomputing = false
    @State private var recomputeMessage: String?
    @State private var recomputeError: String?
    @State private var confirmRecompute = false

    enum HealthRes: Equatable {
        case ok(String)
        case fail(String)
    }

    var body: some View {
        NavigationStack {
            List {
                Section("Server") {
                    Button {
                        editingServerURL = true
                    } label: {
                        HStack {
                            Label("Server URL", systemImage: "server.rack")
                            Spacer()
                            Text(appEnv.settings.serverURL)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        }
                    }

                    Button {
                        checkHealth()
                    } label: {
                        HStack {
                            Label("Check connection", systemImage: "bolt.horizontal.circle")
                            Spacer()
                            if checking {
                                ProgressView()
                            } else if case let .ok(version) = healthResult {
                                Text("OK · \(version)")
                                    .font(.footnote)
                                    .foregroundStyle(.green)
                            } else if case let .fail(msg) = healthResult {
                                Text(msg)
                                    .font(.footnote)
                                    .foregroundStyle(.red)
                                    .lineLimit(1)
                            }
                        }
                    }
                    if let error = healthError {
                        Text(error)
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }
                }

                Section("Connection status") {
                    LabeledContent("State", value: live.connection.label)
                    if let last = live.lastUpdate {
                        LabeledContent("Last update", value: Self.timeFormatter.string(from: last))
                    }
                    if let stats = live.readingStats {
                        LabeledContent("Total readings", value: "\(stats.totalReadings)")
                        if let errCount = stats.errorCount {
                            LabeledContent("Errors", value: "\(errCount)")
                        }
                        LabeledContent("Avg cycle (ms)", value: String(format: "%.0f", stats.avgDuration * 1000))
                    }
                }

                Section("Maintenance") {
                    Button {
                        confirmRecompute = true
                    } label: {
                        HStack {
                            Label("Recompute daily stats", systemImage: "arrow.counterclockwise.circle")
                            Spacer()
                            if recomputing { ProgressView() }
                        }
                    }
                    .disabled(recomputing)
                    if let msg = recomputeMessage {
                        Text(msg).font(.footnote).foregroundStyle(.green)
                    }
                    if let err = recomputeError {
                        Text(err).font(.footnote).foregroundStyle(.red)
                    }
                    Text("Rebuilds daily energy rows from raw readings. Safe to run; operates on the full history.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Session") {
                    Button(role: .destructive) {
                        Task {
                            live.resetSessionState()
                            await auth.signOut()
                        }
                    } label: {
                        Label("Sign out", systemImage: "rectangle.portrait.and.arrow.right")
                    }
                }

                Section("About") {
                    LabeledContent("Version", value: "1.0 · build 1")
                    LabeledContent("Deployment target", value: "iOS 17")
                    Link(destination: URL(string: "https://github.com/anthropics/claude-code")!) {
                        HStack {
                            Label("Claude Code", systemImage: "terminal")
                            Spacer()
                            Image(systemName: "arrow.up.forward.square")
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .navigationTitle("Settings")
            .sheet(isPresented: $editingServerURL) {
                ServerURLEditor()
                    .environmentObject(appEnv.settings)
                    .presentationDetents([.medium, .large])
            }
            .confirmationDialog(
                "Recompute daily stats from raw readings?",
                isPresented: $confirmRecompute,
                titleVisibility: .visible
            ) {
                Button("Recompute") { runRecompute() }
                Button("Cancel", role: .cancel) { }
            } message: {
                Text("This reads every row in power_readings and rewrites every daily_stats row. Usually quick, but it rate-limits to 5/min on the server.")
            }
        }
    }

    private func runRecompute() {
        recomputeError = nil
        recomputeMessage = nil
        recomputing = true
        Task {
            do {
                let result = try await appEnv.commandService.recomputeDaily()
                await MainActor.run {
                    if let err = result.error {
                        recomputeError = err
                    } else {
                        recomputeMessage = "Recomputed \(result.count) day\(result.count == 1 ? "" : "s")."
                    }
                }
            } catch let err as APIError {
                await MainActor.run { recomputeError = err.errorDescription }
            } catch {
                await MainActor.run { recomputeError = error.localizedDescription }
            }
            await MainActor.run { recomputing = false }
        }
    }

    private func checkHealth() {
        healthError = nil
        checking = true
        Task {
            do {
                let result = try await appEnv.authService.health()
                await MainActor.run {
                    self.healthResult = .ok(result.version ?? "dev")
                }
            } catch let err as APIError {
                await MainActor.run {
                    self.healthResult = .fail(err.errorDescription ?? "Failed")
                }
            } catch {
                await MainActor.run {
                    self.healthResult = .fail(error.localizedDescription)
                }
            }
            await MainActor.run { checking = false }
        }
    }

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .short
        f.timeStyle = .medium
        return f
    }()
}
