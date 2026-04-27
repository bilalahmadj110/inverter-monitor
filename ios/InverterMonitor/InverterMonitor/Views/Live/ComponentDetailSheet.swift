import SwiftUI

struct ComponentDetailSheet: View {
    let component: FlowComponent
    @EnvironmentObject var live: LiveDashboardViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    header
                    nowSection
                    componentSpecificSection
                }
                .padding(20)
            }
            .background(Palette.backgroundTop)
            .navigationTitle(component.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.gray)
                    }
                }
            }
            .task {
                // Only refresh-extras if we don't already have config — i.e. the initial
                // app-launch fetch hasn't landed yet. For everything else, the user
                // triggers a refresh explicitly via the nav-bar refresh button, and the
                // sheet already reflects whatever live.config has. Avoids talking to
                // the inverter's USB every time the user opens a sheet.
                if needsConfig && live.config.isEmpty {
                    await live.refreshExtras()
                }
            }
        }
        .preferredColorScheme(.dark)
    }

    private var needsConfig: Bool {
        component == .battery || component == .load || component == .inverter
    }

    private var header: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(component.tint.opacity(0.15))
                    .frame(width: 44, height: 44)
                Image(systemName: component.icon)
                    .font(.title3)
                    .foregroundStyle(component.tint)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(component.title)
                    .font(.title3.bold())
                    .foregroundStyle(.white)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(Palette.subtleText)
            }
            Spacer(minLength: 0)
        }
    }

    private var subtitle: String {
        switch component {
        case .solar: return "Live readings"
        case .grid: return "Utility input"
        case .battery: return "Storage"
        case .load: return "House consumption"
        case .inverter: return "System"
        }
    }

    // MARK: - Now ------------------------------------------------------------

    @ViewBuilder
    private var nowSection: some View {
        Section(header: sectionHeader("Now")) {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                switch component {
                case .solar:
                    let s = live.status.metrics.solar
                    StatTile(label: "Power", value: "\(Int(s.power.rounded()))", unit: "W", accent: Palette.solar)
                    StatTile(label: "Voltage", value: String(format: "%.1f", s.voltage), unit: "V", accent: .white)
                    StatTile(label: "Current", value: String(format: "%.2f", s.current), unit: "A", accent: .white)
                    StatTile(label: "To Battery", value: String(format: "%.2f", s.pvToBatteryCurrent), unit: "A", accent: .white)
                case .grid:
                    let g = live.status.metrics.grid
                    StatTile(label: "Voltage", value: "\(Int(g.voltage.rounded()))", unit: "V", accent: .white)
                    StatTile(label: "Frequency", value: String(format: "%.1f", g.frequency), unit: "Hz", accent: .white)
                    StatTile(label: "Power", value: "\(Int(g.power.rounded()))", unit: "W", accent: Palette.grid)
                    StatTile(label: "Status", value: g.inUse ? "In use" : "Idle / Backup", accent: .white)
                case .battery:
                    let b = live.status.metrics.battery
                    StatTile(label: "State of Charge", value: "\(Int(b.percentage.rounded()))", unit: "%", accent: Palette.battery)
                    StatTile(label: "Voltage", value: String(format: "%.2f", b.voltage), unit: "V", accent: .white)
                    StatTile(label: "Current", value: String(format: "%.2f", abs(b.current)), unit: "A", accent: .white)
                    StatTile(label: "Direction", value: b.direction.label, accent: .white)
                case .load:
                    let l = live.status.metrics.load
                    StatTile(label: "Active", value: "\(Int(l.effectivePower.rounded()))", unit: "W", accent: Palette.load)
                    StatTile(label: "Apparent", value: "\(Int(l.apparentPower.rounded()))", unit: "VA", accent: .white)
                    StatTile(label: "Voltage", value: "\(Int(l.voltage.rounded()))", unit: "V", accent: .white)
                    StatTile(label: "Load", value: "\(Int(l.percentage.rounded()))", unit: "%", accent: .white)
                case .inverter:
                    let system = live.status.system
                    StatTile(label: "Temperature",
                             value: system.temperature > 0 ? "\(Int(system.temperature.rounded()))" : "—",
                             unit: "°C", accent: .white)
                    StatTile(label: "Bus Voltage",
                             value: system.busVoltage > 0 ? "\(Int(system.busVoltage.rounded()))" : "—",
                             unit: "V", accent: .white)
                    StatTile(label: "Mode", value: system.modeLabel, accent: .white)
                    StatTile(label: "Charge Stage",
                             value: system.chargeStage.label,
                             accent: .white)
                }
            }
        }
    }

    // MARK: - Component-specific sections -----------------------------------

    @ViewBuilder
    private var componentSpecificSection: some View {
        switch component {
        case .solar:
            Section(header: sectionHeader("Notes")) {
                Text("PV settings on this inverter are read-only. Output / charger routing is controlled from the Load and Battery panels.")
                    .font(.footnote)
                    .foregroundStyle(Palette.mutedText)
                    .padding(12)
                    .card()
            }
        case .grid:
            Section(header: sectionHeader("Notes")) {
                Text("Grid-related write operations (input voltage range, AC charging current) aren't exposed yet. The readings above are live from the inverter.")
                    .font(.footnote)
                    .foregroundStyle(Palette.mutedText)
                    .padding(12)
                    .card()
            }
        case .load:
            LoadPrioritySection()
        case .battery:
            BatteryPrioritySection()
            BatteryInfoSection()
        case .inverter:
            InverterConfigSection()
        }
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.caption.weight(.semibold))
            .tracking(0.8)
            .foregroundStyle(Palette.subtleText)
    }
}

// MARK: - Load output priority ------------------------------------------------

struct LoadPrioritySection: View {
    @EnvironmentObject var live: LiveDashboardViewModel
    @State private var pending: OutputPriority?
    @State private var confirmationShown = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("OUTPUT SOURCE PRIORITY")
                .font(.caption.weight(.semibold))
                .tracking(0.8)
                .foregroundStyle(Palette.subtleText)
            Text("Where the load gets its power from. Current: \(currentLabel)")
                .font(.caption)
                .foregroundStyle(Palette.mutedText)
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                ForEach(OutputPriority.allCases) { mode in
                    priorityButton(mode)
                }
            }
            if let msg = live.priorityFlash {
                ToastBanner(message: msg, style: .success)
            }
            if let err = live.priorityError {
                ToastBanner(message: err, style: .error)
            }
        }
        .sensoryFeedback(.success, trigger: live.priorityFlash) { old, new in old != new && new != nil }
        .sensoryFeedback(.error, trigger: live.priorityError) { old, new in old != new && new != nil }
        .confirmationDialog(
            "Apply \(pending?.title ?? "") as output priority?",
            isPresented: $confirmationShown,
            titleVisibility: .visible
        ) {
            Button("Apply") {
                guard let pending else { return }
                Task { await live.setOutputPriority(pending) }
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            if let pending {
                Text(pending.detail)
            }
        }
    }

    private var currentLabel: String {
        live.config.outputPriority?.shortLabel ?? "—"
    }

    private func priorityButton(_ mode: OutputPriority) -> some View {
        let isCurrent = live.config.outputPriority == mode
        let isBusy = live.isApplyingPriority && pending == mode
        return Button {
            pending = mode
            confirmationShown = true
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(mode.title)
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(.white)
                    if isCurrent {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(Color.green)
                            .font(.caption)
                            .accessibilityLabel("Currently applied")
                    }
                    Spacer(minLength: 0)
                    if isBusy {
                        ProgressView().controlSize(.mini).tint(.white)
                    }
                }
                Text(mode.detail)
                    .font(.caption2)
                    .foregroundStyle(Palette.subtleText)
                    .multilineTextAlignment(.leading)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(10)
            .background(
                isCurrent
                ? Color.green.opacity(0.15)
                : Color.white.opacity(0.05),
                in: RoundedRectangle(cornerRadius: 10)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(isCurrent ? Color.green.opacity(0.6) : Palette.cardBorder)
            )
        }
        .buttonStyle(.plain)
        .disabled(live.isApplyingPriority)
        .animation(.easeInOut(duration: 0.2), value: isCurrent)
    }
}

// MARK: - Battery charger priority -------------------------------------------

struct BatteryPrioritySection: View {
    @EnvironmentObject var live: LiveDashboardViewModel
    @State private var pending: ChargerPriority?
    @State private var confirmationShown = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("CHARGER SOURCE PRIORITY")
                .font(.caption.weight(.semibold))
                .tracking(0.8)
                .foregroundStyle(Palette.subtleText)
            Text("What's allowed to charge the battery. Current: \(currentLabel)")
                .font(.caption)
                .foregroundStyle(Palette.mutedText)
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                ForEach(ChargerPriority.allCases) { mode in
                    priorityButton(mode)
                }
            }
            if let msg = live.priorityFlash {
                ToastBanner(message: msg, style: .success)
            }
            if let err = live.priorityError {
                ToastBanner(message: err, style: .error)
            }
        }
        .sensoryFeedback(.success, trigger: live.priorityFlash) { old, new in old != new && new != nil }
        .sensoryFeedback(.error, trigger: live.priorityError) { old, new in old != new && new != nil }
        .confirmationDialog(
            "Apply \(pending?.title ?? "") as charger priority?",
            isPresented: $confirmationShown,
            titleVisibility: .visible
        ) {
            Button("Apply") {
                guard let pending else { return }
                Task { await live.setChargerPriority(pending) }
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            if let pending {
                Text(pending.detail)
            }
        }
    }

    private var currentLabel: String {
        live.config.chargerPriority?.title ?? "—"
    }

    private func priorityButton(_ mode: ChargerPriority) -> some View {
        let isCurrent = live.config.chargerPriority == mode
        let isBusy = live.isApplyingPriority && pending == mode
        return Button {
            pending = mode
            confirmationShown = true
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(mode.title)
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(.white)
                    if isCurrent {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(Color.green)
                            .font(.caption)
                            .accessibilityLabel("Currently applied")
                    }
                    Spacer(minLength: 0)
                    if isBusy {
                        ProgressView().controlSize(.mini).tint(.white)
                    }
                }
                Text(mode.detail)
                    .font(.caption2)
                    .foregroundStyle(Palette.subtleText)
                    .multilineTextAlignment(.leading)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(10)
            .background(
                isCurrent
                ? Color.green.opacity(0.15)
                : Color.white.opacity(0.05),
                in: RoundedRectangle(cornerRadius: 10)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(isCurrent ? Color.green.opacity(0.6) : Palette.cardBorder)
            )
        }
        .buttonStyle(.plain)
        .disabled(live.isApplyingPriority)
        .animation(.easeInOut(duration: 0.2), value: isCurrent)
    }
}

// MARK: - Battery config extras ---------------------------------------------

struct BatteryInfoSection: View {
    @EnvironmentObject var live: LiveDashboardViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("BATTERY INFO")
                .font(.caption.weight(.semibold))
                .tracking(0.8)
                .foregroundStyle(Palette.subtleText)
            VStack(spacing: 0) {
                InfoRow(label: "Type", value: live.config.batteryType ?? "—")
                InfoRow(label: "Max Charging Current",
                        value: formatOpt(live.config.maxChargingCurrent, unit: "A"))
                InfoRow(label: "Max AC Charging Current",
                        value: formatOpt(live.config.maxAcChargingCurrent, unit: "A"))
                InfoRow(label: "Under Voltage",
                        value: formatOpt(live.config.batteryUnderVoltage, unit: "V"))
                InfoRow(label: "Bulk Charge",
                        value: formatOpt(live.config.batteryBulkChargeVoltage, unit: "V"))
                InfoRow(label: "Float Charge",
                        value: formatOpt(live.config.batteryFloatChargeVoltage, unit: "V"))
            }
            .padding(12)
            .card()
        }
    }

    private func formatOpt(_ value: Double?, unit: String) -> String {
        guard let value else { return "—" }
        if value == value.rounded() { return "\(Int(value)) \(unit)" }
        return String(format: "%.1f %@", value, unit)
    }
}

// MARK: - Inverter full config (QPIRI) ---------------------------------------

struct InverterConfigSection: View {
    @EnvironmentObject var live: LiveDashboardViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("FULL CONFIGURATION (QPIRI)")
                .font(.caption.weight(.semibold))
                .tracking(0.8)
                .foregroundStyle(Palette.subtleText)

            if live.config.rows.isEmpty {
                HStack(spacing: 10) {
                    ProgressView().tint(Palette.subtleText)
                    Text(live.isRefreshingExtras ? "Reading inverter…" : "No config loaded. Pull to refresh.")
                        .font(.footnote)
                        .foregroundStyle(Palette.mutedText)
                    Spacer(minLength: 0)
                }
                .padding(12)
                .card()
            } else {
                VStack(spacing: 0) {
                    ForEach(live.config.rows) { row in
                        InfoRow(label: row.label, value: row.unit.isEmpty ? row.value : "\(row.value) \(row.unit)")
                    }
                }
                .padding(12)
                .card()
            }

            Button {
                Task { await live.refreshExtras() }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "arrow.clockwise")
                    Text("Refresh now")
                }
                .font(.footnote.weight(.semibold))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 10)
                .background(Color.blue, in: RoundedRectangle(cornerRadius: 10))
            }
            .buttonStyle(.plain)
            .disabled(live.isRefreshingExtras)
        }
    }
}

// MARK: - Toast --------------------------------------------------------------

struct ToastBanner: View {
    enum Style { case success, error, info }
    let message: String
    let style: Style

    private var accent: Color {
        switch style {
        case .success: return .green
        case .error: return .red
        case .info: return .blue
        }
    }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
            Text(message)
                .font(.footnote)
            Spacer(minLength: 0)
        }
        .foregroundStyle(accent)
        .padding(10)
        .background(accent.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(accent.opacity(0.4))
        )
    }

    private var icon: String {
        switch style {
        case .success: return "checkmark.circle.fill"
        case .error: return "exclamationmark.triangle.fill"
        case .info: return "info.circle.fill"
        }
    }
}
