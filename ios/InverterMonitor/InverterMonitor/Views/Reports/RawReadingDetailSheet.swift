import SwiftUI

/// Bottom sheet that appears when a row in the Raw readings table is tapped.
/// Shows every field from the reading, not just the four shown in the condensed row.
struct RawReadingDetailSheet: View {
    let reading: RawReading
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    header

                    section("Power (W)") {
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                            StatTile(label: "Solar", value: "\(Int(reading.solarPower.rounded()))",
                                     unit: "W", accent: Palette.solar)
                            StatTile(label: "Grid", value: "\(Int(reading.gridPower.rounded()))",
                                     unit: "W", accent: Palette.grid)
                            StatTile(label: "Load", value: "\(Int(reading.loadPower.rounded()))",
                                     unit: "W", accent: Palette.load)
                            StatTile(label: "Battery", value: "\(Int(reading.batteryPower.rounded()))",
                                     unit: "W", accent: Palette.battery)
                        }
                    }

                    section("Battery") {
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                            StatTile(label: "State of Charge",
                                     value: "\(Int(reading.batteryPercentage.rounded()))",
                                     unit: "%",
                                     accent: socColor(reading.batteryPercentage))
                            StatTile(label: "Direction",
                                     value: directionLabel,
                                     accent: .white)
                        }
                    }

                    section("Grid") {
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                            StatTile(label: "Voltage",
                                     value: "\(Int(reading.gridVoltage.rounded()))",
                                     unit: "V",
                                     accent: .white)
                            StatTile(label: "Temp",
                                     value: "\(Int(reading.temperature.rounded()))",
                                     unit: "°C",
                                     accent: .white)
                        }
                    }

                    section("Raw") {
                        VStack(spacing: 0) {
                            InfoRow(label: "Timestamp", value: reading.timestampFormatted)
                            InfoRow(label: "Epoch seconds", value: "\(Int(reading.timestamp))")
                            InfoRow(label: "Cycle duration",
                                    value: String(format: "%.1f ms", reading.durationMs))
                        }
                        .padding(12)
                        .card()
                    }
                }
                .padding(20)
            }
            .background(Palette.backgroundTop)
            .navigationTitle("Reading detail")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.gray)
                    }
                    .accessibilityLabel("Close")
                }
            }
        }
        .preferredColorScheme(.dark)
    }

    private var header: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Palette.inverterAmber.opacity(0.15))
                    .frame(width: 44, height: 44)
                Image(systemName: "waveform.path.ecg")
                    .font(.title3)
                    .foregroundStyle(Palette.inverterAmber)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(reading.timestampFormatted)
                    .font(.title3.bold())
                    .foregroundStyle(.white)
                Text("Inverter reading")
                    .font(.caption)
                    .foregroundStyle(Palette.subtleText)
            }
            Spacer(minLength: 0)
        }
    }

    private func section<Content: View>(_ title: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title.uppercased())
                .font(.caption.weight(.semibold))
                .tracking(0.8)
                .foregroundStyle(Palette.subtleText)
            content()
        }
    }

    private var directionLabel: String {
        // battery_power is signed: positive = charging, negative = discharging.
        if reading.batteryPower > 5 { return "Charging" }
        if reading.batteryPower < -5 { return "Discharging" }
        return "Idle"
    }

    private func socColor(_ pct: Double) -> Color {
        if pct >= 50 { return Palette.battery }
        if pct >= 20 { return .orange }
        return .red
    }
}
