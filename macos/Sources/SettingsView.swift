import AppKit
import SwiftUI

/// Settings for this copy of Acervo on this Mac: whether it starts with the session, which server
/// it belongs to, and how it takes new versions of itself.
///
/// Nothing about the vocabulary is here. That lives in the owner's records, which only the
/// interface reads and writes.
struct SettingsView: View {
    @ObservedObject var updates: UpdateService
    @EnvironmentObject private var settings: AppSettings
    @EnvironmentObject private var router: SettingsRouter
    @FocusState private var serverFieldIsFocused: Bool
    @State private var openAtLogin = LoginItem.isEnabled
    @State private var serverURL: String
    @State private var serverMessage: String?
    @State private var pendingSave: Task<Void, Never>?

    let checkNow: () -> Void
    let installUpdate: () -> Void
    let restartNow: () -> Void

    enum Pane: Hashable, CaseIterable, Identifiable {
        case general, updates

        var id: Self { self }

        var title: String {
            switch self {
            case .general: "General"
            case .updates: "Updates"
            }
        }

        var icon: String {
            switch self {
            case .general: "gearshape"
            case .updates: "arrow.down.circle"
            }
        }
    }

    init(
        updates: UpdateService,
        checkNow: @escaping () -> Void,
        installUpdate: @escaping () -> Void,
        restartNow: @escaping () -> Void
    ) {
        self.updates = updates
        self.checkNow = checkNow
        self.installUpdate = installUpdate
        self.restartNow = restartNow
        _serverURL = State(initialValue: updates.storedServerURL)
    }

    var body: some View {
        HStack(spacing: 0) {
            List(Pane.allCases, selection: $router.pane) { pane in
                Label(pane.title, systemImage: pane.icon).tag(pane)
            }
            .listStyle(.sidebar)
            .frame(width: 160)

            Divider()

            ScrollView {
                pane
                    .frame(maxWidth: .infinity, alignment: .topLeading)
                    .padding(24)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        // Leaving the pane and closing the window both keep what was typed.
        .onChange(of: router.pane) { _, _ in flushServerURL() }
        .onDisappear { flushServerURL() }
    }

    @ViewBuilder
    private var pane: some View {
        switch router.pane {
        case .general: general
        case .updates: updatesPane
        }
    }

    // MARK: - General

    private var general: some View {
        VStack(alignment: .leading, spacing: 20) {
            Toggle(isOn: $openAtLogin) {
                settingLabel(
                    "Open Acervo at login",
                    "The menu bar marks a waiting update only while Acervo is running."
                )
            }
            .toggleStyle(.switch)
            .onChange(of: openAtLogin) { _, value in
                LoginItem.setEnabled(value)
                openAtLogin = LoginItem.isEnabled
            }

            Toggle(isOn: $settings.showWindowAtLogin) {
                settingLabel(
                    "Show the window when opened at login",
                    "Off, Acervo starts quietly in the menu bar. Opening it yourself always shows the window."
                )
            }
            .toggleStyle(.switch)
            .disabled(!openAtLogin)

            Divider()

            server

            Spacer(minLength: 0)
        }
    }

    private var server: some View {
        VStack(alignment: .leading, spacing: 8) {
            settingLabel(
                "Server",
                "Use the same HTTPS address that opens Acervo in your browser. This Mac uses it to find and download updates."
            )
            .fixedSize(horizontal: false, vertical: true)

            TextField("https://acervo.example.com", text: $serverURL)
                .textFieldStyle(.roundedBorder)
                .focused($serverFieldIsFocused)
                .accessibilityLabel("Acervo server address")
                .onSubmit { saveServerURL() }
                .onChange(of: serverURL) { _, _ in scheduleSave() }
                .onChange(of: serverFieldIsFocused) { wasFocused, isFocused in
                    if wasFocused, !isFocused { saveServerURL() }
                }

            if let serverMessage {
                Text(serverMessage)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: - Updates

    private var updatesPane: some View {
        VStack(alignment: .leading, spacing: 16) {
            Toggle(isOn: Binding(get: { updates.automaticChecks }, set: { updates.automaticChecks = $0 })) {
                settingLabel(
                    "Check for updates automatically",
                    "Looks for a new release on your Acervo server every few hours."
                )
            }
            .toggleStyle(.switch)

            Toggle(isOn: Binding(get: { updates.automaticInstall }, set: { updates.automaticInstall = $0 })) {
                settingLabel(
                    "Install updates automatically",
                    "Updates install quietly in the background and start the next time Acervo opens. Acervo never restarts itself."
                )
            }
            .toggleStyle(.switch)
            .disabled(!updates.automaticChecks)

            Divider()

            HStack(spacing: 10) {
                Button(updates.state == .checking ? "Checking…" : "Check Now", action: checkNow)
                    .disabled(updates.isBusy || !updates.hasServerURL)
                status
            }
            .font(.callout)

            Text("Version \(AppVersion.label)")
                .font(.caption)
                .foregroundStyle(.secondary)

            Spacer(minLength: 0)
        }
    }

    @ViewBuilder
    private var status: some View {
        switch updates.state {
        case .downloading(let fraction):
            ProgressView(value: fraction).frame(width: 90)
            Text("Downloading \(Int(fraction * 100))%").font(.caption).foregroundStyle(.secondary)
        case .installing:
            ProgressView().controlSize(.small)
            Text("Installing…").font(.caption).foregroundStyle(.secondary)
        case .failed(let message):
            Text(message).font(.caption).foregroundStyle(.red).lineLimit(3)
        case .checking:
            ProgressView().controlSize(.small)
        case .idle:
            if let pending = updates.pendingBuild {
                Text("Build \(pending) starts when Acervo restarts").font(.caption).foregroundStyle(.orange)
                Button("Restart Now", action: restartNow).buttonStyle(.borderedProminent).controlSize(.small)
            } else if let release = updates.available {
                Text("Build \(release.build) is available").font(.caption).foregroundStyle(.orange)
                // The label names the restart, so nothing has to confirm it afterwards.
                Button("Update and Restart", action: installUpdate).buttonStyle(.borderedProminent).controlSize(.small)
            } else if let message = updates.statusMessage {
                Text(message).font(.caption).foregroundStyle(.secondary)
            } else if let date = updates.lastCheck {
                Text("Last checked: \(date.formatted(date: .abbreviated, time: .shortened))")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func settingLabel(_ title: String, _ detail: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
            Text(detail)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - Server address

    private func flushServerURL() {
        pendingSave?.cancel()
        saveServerURL(normalizeField: false)
    }

    private func saveServerURL(normalizeField: Bool = true) {
        pendingSave?.cancel()
        guard serverURL != updates.storedServerURL else { return }
        do {
            try updates.saveServerURL(serverURL)
            if normalizeField { serverURL = updates.storedServerURL }
            serverMessage = nil
        } catch {
            guard normalizeField else { return }
            if case let UpdateFailure.message(message) = error { serverMessage = message }
            else { serverMessage = error.localizedDescription }
        }
    }

    private func scheduleSave() {
        serverMessage = nil
        pendingSave?.cancel()
        pendingSave = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(500))
            guard !Task.isCancelled else { return }
            saveServerURL(normalizeField: false)
        }
    }
}
