import SwiftUI

/// Navigation-bar refresh button with a continuous spin when in-flight. Rendered this
/// way rather than via `symbolEffect(.rotate)` because that SF Symbol effect requires
/// iOS 18 and we target iOS 17.
struct RefreshToolbarButton: View {
    let isRefreshing: Bool
    let action: () -> Void

    @State private var rotation: Double = 0

    var body: some View {
        Button(action: action) {
            Image(systemName: "arrow.clockwise")
                .rotationEffect(.degrees(rotation))
                .accessibilityLabel("Refresh mode and warnings from inverter")
                .accessibilityHint("Sends fresh QMOD, QPIWS, and QPIRI commands")
        }
        .disabled(isRefreshing)
        .onAppear {
            // If we come onscreen while a refresh is already in flight (tab switch,
            // scene-phase resume mid-refresh), kick the spin now — onChange only fires
            // on transitions, so it wouldn't catch this case.
            if isRefreshing { startSpinning() }
        }
        .onChange(of: isRefreshing) { _, refreshing in
            if refreshing {
                startSpinning()
            } else {
                withAnimation(.easeOut(duration: 0.25)) { rotation = 0 }
            }
        }
    }

    private func startSpinning() {
        withAnimation(.linear(duration: 0.9).repeatForever(autoreverses: false)) {
            rotation = 360
        }
    }
}
