import SwiftUI

struct LoginView: View {
    @EnvironmentObject var auth: AuthViewModel
    @EnvironmentObject var appEnv: AppEnvironment

    @FocusState private var focusedField: Field?
    @State private var showServerSheet = false

    enum Field: Hashable { case username, password }

    var body: some View {
        ZStack {
            ScrollView {
                VStack(spacing: 20) {
                    Spacer(minLength: 60)
                    brandMark
                    card
                    Spacer(minLength: 40)
                }
                .frame(maxWidth: 420)
                .padding(.horizontal, 20)
                .frame(maxWidth: .infinity)
            }
        }
        .immersiveBackground()
        .sheet(isPresented: $showServerSheet) {
            ServerURLEditor()
                .environmentObject(appEnv.settings)
                .presentationDetents([.medium, .large])
        }
    }

    private var brandMark: some View {
        VStack(spacing: 10) {
            Image(systemName: "sun.max.trianglebadge.exclamationmark.fill")
                .renderingMode(.original)
                .font(.system(size: 52))
                .foregroundStyle(Palette.solar)
                .shadow(color: Palette.solar.opacity(0.35), radius: 18, x: 0, y: 0)
            Text("Inverter Monitor")
                .font(.title2.bold())
                .foregroundStyle(.white)
            Text("Sign in to continue")
                .font(.footnote)
                .foregroundStyle(Palette.mutedText)
        }
    }

    private var card: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let error = auth.loginError {
                HStack(spacing: 10) {
                    Image(systemName: "exclamationmark.triangle.fill")
                    Text(error)
                        .font(.footnote)
                    Spacer(minLength: 0)
                }
                .foregroundStyle(Color(red: 0.996, green: 0.792, blue: 0.792))
                .padding(10)
                .background(Color.red.opacity(0.15), in: RoundedRectangle(cornerRadius: 10))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .strokeBorder(Color.red.opacity(0.4))
                )
            }

            field(title: "Username") {
                TextField("admin", text: $auth.username)
                    .textContentType(.username)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled(true)
                    .focused($focusedField, equals: .username)
                    .submitLabel(.next)
                    .onSubmit { focusedField = .password }
            }

            field(title: "Password") {
                SecureField("••••••••", text: $auth.password)
                    .textContentType(.password)
                    .focused($focusedField, equals: .password)
                    .submitLabel(.go)
                    .onSubmit { submit() }
            }

            Button(action: submit) {
                HStack(spacing: 8) {
                    if auth.isBusy {
                        ProgressView().tint(.white)
                    }
                    Text("Sign in")
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 11)
                .background(Color.blue, in: RoundedRectangle(cornerRadius: 10))
                .foregroundStyle(.white)
            }
            .disabled(auth.isBusy)
            .buttonStyle(.plain)

            Divider().background(Palette.divider).padding(.vertical, 2)

            Button {
                showServerSheet = true
            } label: {
                HStack {
                    Image(systemName: "server.rack")
                    Text(serverHost)
                        .font(.footnote)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right")
                        .font(.caption)
                }
                .foregroundStyle(Palette.mutedText)
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .card()
            }
            .buttonStyle(.plain)
        }
        .padding(18)
        .card(cornerRadius: 18)
    }

    private func field<Content: View>(title: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(Palette.subtleText)
            content()
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(Color.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .strokeBorder(Palette.cardBorder)
                )
                .foregroundStyle(.white)
                .tint(.white)
        }
    }

    private var serverHost: String {
        appEnv.settings.serverURL
    }

    private func submit() {
        Task { await auth.signIn() }
    }
}

struct ServerURLEditor: View {
    @EnvironmentObject var settings: AppSettings
    @Environment(\.dismiss) private var dismiss
    @State private var url: String = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Server URL") {
                    TextField("http://192.168.1.50:5000", text: $url)
                        .keyboardType(.URL)
                        .textContentType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)
                }
                Section {
                    Text("Enter the base URL of the Flask server. If you omit the scheme, HTTP is assumed.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Server")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        settings.serverURL = url.trimmingCharacters(in: .whitespacesAndNewlines)
                        dismiss()
                    }
                    .disabled(url.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .onAppear { url = settings.serverURL }
    }
}
