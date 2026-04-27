import SwiftUI

struct StatusPill: View {
    let label: String
    var systemImage: String? = nil
    var tint: Color = .white
    var backgroundTint: Color = Palette.cardSurface
    var dotColor: Color? = nil
    var dashed: Bool = false

    var body: some View {
        HStack(spacing: 6) {
            if let dotColor {
                Circle()
                    .fill(dotColor)
                    .frame(width: 8, height: 8)
            }
            if let systemImage {
                Image(systemName: systemImage)
                    .imageScale(.small)
                    .foregroundStyle(tint)
            }
            Text(label)
                .font(.caption.weight(.semibold))
                .foregroundStyle(tint)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(
            Capsule(style: .continuous)
                .fill(backgroundTint)
        )
        .overlay(
            Capsule(style: .continuous)
                .strokeBorder(
                    Palette.cardBorder,
                    style: StrokeStyle(lineWidth: 1, dash: dashed ? [3, 3] : [])
                )
        )
    }
}
