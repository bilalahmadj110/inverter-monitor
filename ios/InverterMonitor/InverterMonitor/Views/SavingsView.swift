import SwiftUI

/// Top-level Savings tab — mirrors the web's /savings page as its own bottom-nav
/// entry. The heavy rendering lives in `SavingsReportView` so the markup stays
/// consistent if we ever decide to re-embed a compact version inside Reports.
struct SavingsView: View {
    @EnvironmentObject var reports: ReportsViewModel

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    SavingsReportView()
                }
                .padding(.horizontal, 16)
                .padding(.top, 16)
                .padding(.bottom, 40)
            }
            .scrollIndicators(.hidden)
            .immersiveBackground()
            .navigationTitle("Savings")
            .task { await reports.loadSavings() }
            .refreshable { await reports.loadSavings() }
        }
    }
}
