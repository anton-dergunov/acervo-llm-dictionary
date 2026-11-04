import Combine
import Foundation

/// This copy of Acervo's own settings, as the interface's Settings ▸ General shows them.
///
/// There used to be a second Settings window here for these: whether Acervo opens at login, how it
/// takes new versions of itself, and which server it belongs to. They are still the application's —
/// stored in its preferences, answered by the system for the login item — but they are shown and
/// changed in the one Settings the interface already has. The interface reads them through the
/// bridge (`hostSettings`), asks for a change (`setHostSetting`, `checkForUpdates`, …), and is told
/// of every change it did not ask for — a download moving on, a build arriving — through `onChange`.
///
/// Nothing about the vocabulary is here; that lives in the owner's records, which only the
/// interface reads and writes. The server address is shown and not edited: changing server is
/// signing in again, which the interface's sign-in screen does, and saving that session is what
/// writes the address the updater reads.
@MainActor
final class HostSettings {
    struct Update: Encodable, Equatable {
        let state: String
        let progress: Double?
        let message: String?
        let available: String?
        let pendingBuild: String?
        let lastCheck: String?
    }

    struct Snapshot: Encodable, Equatable {
        let serverURL: String
        let openAtLogin: Bool
        let showWindowAtLogin: Bool
        let automaticChecks: Bool
        let automaticInstall: Bool
        let version: String
        let update: Update
    }

    /// Called with the new state whenever it changes, however it changed.
    var onChange: ((Snapshot) -> Void)?

    private let updates: UpdateService
    private let appSettings: AppSettings
    private let loginItem: () -> Bool
    private let setLoginItem: (Bool) -> Bool
    private var observed: Set<AnyCancellable> = []
    private var last: Snapshot?

    init(
        updates: UpdateService,
        appSettings: AppSettings = .shared,
        loginItem: @escaping () -> Bool = { LoginItem.isEnabled },
        setLoginItem: @escaping (Bool) -> Bool = { LoginItem.setEnabled($0) }
    ) {
        self.updates = updates
        self.appSettings = appSettings
        self.loginItem = loginItem
        self.setLoginItem = setLoginItem
        // `objectWillChange` fires before the change lands, so the state is read on the next turn.
        for publisher in [updates.objectWillChange.eraseToAnyPublisher(),
                          appSettings.objectWillChange.eraseToAnyPublisher()] {
            publisher
                .receive(on: DispatchQueue.main)
                .sink { [weak self] _ in self?.publish() }
                .store(in: &observed)
        }
    }

    func snapshot() -> Snapshot {
        Snapshot(
            serverURL: updates.storedServerURL,
            openAtLogin: loginItem(),
            showWindowAtLogin: appSettings.showWindowAtLogin,
            automaticChecks: updates.automaticChecks,
            automaticInstall: updates.automaticInstall,
            version: AppVersion.label,
            update: update()
        )
    }

    /// One switch. The answer is read back rather than assumed: the system can refuse a login item,
    /// and a switch that disagreed with System Settings would be worse than no switch.
    func set(_ name: String, to value: Bool) throws -> Snapshot {
        switch name {
        case "openAtLogin":
            if !setLoginItem(value) {
                throw HostSettingsError.refused(
                    "macOS did not let Acervo \(value ? "open" : "stop opening") at login. System Settings ▸ General ▸ Login Items has the switch."
                )
            }
        case "showWindowAtLogin": appSettings.showWindowAtLogin = value
        case "automaticChecks": updates.automaticChecks = value
        case "automaticInstall": updates.automaticInstall = value
        default: throw HostSettingsError.refused("Acervo has no setting called \(name).")
        }
        return publish()
    }

    func checkForUpdates() -> Snapshot {
        Task { await updates.check(force: true) }
        return snapshot()
    }

    /// The label names the restart, so nothing confirms it afterwards.
    func installUpdate() -> Snapshot {
        Task { await updates.install(thenRestart: true) }
        return snapshot()
    }

    func restartNow() -> Snapshot {
        updates.restartNow()
        return snapshot()
    }

    @discardableResult
    private func publish() -> Snapshot {
        let now = snapshot()
        if now != last {
            last = now
            onChange?(now)
        }
        return now
    }

    private func update() -> Update {
        let checked = updates.lastCheck.map { ISO8601DateFormatter().string(from: $0) }
        let idle = { (message: String?) in
            Update(state: "idle", progress: nil, message: message, available: self.updates.available?.build,
                   pendingBuild: self.updates.pendingBuild, lastCheck: checked)
        }
        switch updates.state {
        case .idle: return idle(updates.statusMessage)
        case .checking:
            return Update(state: "checking", progress: nil, message: nil, available: nil, pendingBuild: nil, lastCheck: checked)
        case .downloading(let fraction):
            return Update(state: "downloading", progress: fraction, message: nil, available: nil, pendingBuild: nil, lastCheck: checked)
        case .installing:
            return Update(state: "installing", progress: nil, message: nil, available: nil, pendingBuild: nil, lastCheck: checked)
        case .failed(let message):
            return Update(state: "failed", progress: nil, message: message, available: nil, pendingBuild: nil, lastCheck: checked)
        }
    }
}

enum HostSettingsError: LocalizedError {
    case refused(String)
    var errorDescription: String? { if case .refused(let message) = self { message } else { nil } }
}
