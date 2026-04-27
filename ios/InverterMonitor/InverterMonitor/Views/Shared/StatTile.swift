import SwiftUI

struct StatTile: View {
    let label: String
    let value: String
    var unit: String? = nil
    var accent: Color = .white

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label.uppercased())
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Palette.subtleText)
                .tracking(0.6)
            HStack(alignment: .lastTextBaseline, spacing: 3) {
                Text(value)
                    .font(.system(size: 22, weight: .bold, design: .rounded))
                    .foregroundStyle(accent)
                if let unit {
                    Text(unit)
                        .font(.caption)
                        .foregroundStyle(Palette.subtleText)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .card()
    }
}

struct InfoRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .font(.footnote)
                .foregroundStyle(Palette.mutedText)
            Spacer()
            Text(value)
                .font(.footnote.weight(.medium))
                .foregroundStyle(.white)
        }
        .padding(.vertical, 6)
        .overlay(
            Rectangle()
                .frame(height: 1)
                .foregroundStyle(Palette.divider),
            alignment: .bottom
        )
    }
}
