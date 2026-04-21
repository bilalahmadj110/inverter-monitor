import SwiftUI

enum Palette {
    /// Amber-orange used for solar across the web app.
    static let solar = Color(red: 0.988, green: 0.827, blue: 0.302) // #FCD34D
    static let solarFill = solar.opacity(0.22)
    /// Sky-blue for grid.
    static let grid = Color(red: 0.376, green: 0.647, blue: 0.980) // #60A5FA
    static let gridFill = grid.opacity(0.22)
    /// Violet for load.
    static let load = Color(red: 0.655, green: 0.545, blue: 0.980) // #A78BFA
    static let loadFill = load.opacity(0.22)
    /// Mint-green for battery.
    static let battery = Color(red: 0.204, green: 0.827, blue: 0.600) // #34D399
    static let batteryFill = battery.opacity(0.22)

    static let inverterAmber = Color(red: 0.984, green: 0.749, blue: 0.141) // #FBBF24

    /// Slate ink backgrounds, close to the web app's gradient.
    static let backgroundTop = Color(red: 0.06, green: 0.09, blue: 0.16)    // #0F172A
    static let backgroundMid = Color(red: 0.05, green: 0.12, blue: 0.24)
    static let backgroundBottom = Color(red: 0.10, green: 0.10, blue: 0.30) // indigo-ish

    static let cardSurface = Color.white.opacity(0.08)
    static let cardBorder = Color.white.opacity(0.12)
    static let subtleText = Color.white.opacity(0.55)
    static let mutedText = Color.white.opacity(0.75)
    static let divider = Color.white.opacity(0.08)
}

extension View {
    /// Standard card chrome used all over the app — white fill @ 8% + faint border + rounded corners.
    func card(cornerRadius: CGFloat = 14) -> some View {
        self
            .background(Palette.cardSurface, in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .strokeBorder(Palette.cardBorder, lineWidth: 1)
            )
    }

    /// Immersive dark gradient backdrop used on the Live + Reports tabs.
    func immersiveBackground() -> some View {
        self.background(
            LinearGradient(
                colors: [Palette.backgroundTop, Palette.backgroundMid, Palette.backgroundBottom],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()
        )
    }
}
