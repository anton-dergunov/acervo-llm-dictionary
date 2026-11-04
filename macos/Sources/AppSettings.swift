import Combine
import Foundation
import ServiceManagement

/// "Open at login", kept in one place because the answer has to come from the system rather than
/// from a remembered setting: a person can remove a login item in System Settings, and a switch
/// that disagreed with that would be worse than no switch.
enum LoginItem {
    private static let initialised = "AcervoLoginItemInitialised"

    static var isEnabled: Bool { SMAppService.mainApp.status == .enabled }

    @discardableResult
    static func setEnabled(_ enabled: Bool) -> Bool {
        do {
            if enabled {
                if SMAppService.mainApp.status != .enabled { try SMAppService.mainApp.register() }
            } else {
                if SMAppService.mainApp.status == .enabled { try SMAppService.mainApp.unregister() }
            }
            return true
        } catch {
            // The switch reads the real status, so a refusal simply shows as the switch returning
            // to where it was rather than as a lie about what is configured.
            NSLog("Acervo could not change its login item: \(error.localizedDescription)")
            return false
        }
    }

    /// Acervo's update mark lives in the menu bar, so it is only seen once Acervo is running: it
    /// starts at login by default. Done exactly once, and remembered, so that turning it off stays
    /// off -- and remembered only once it has worked, so a refusal is tried again next time.
    ///
    /// A copy run from a build directory and the test host share the installed application's
    /// bundle identifier and therefore its preferences; neither may register itself or spend the
    /// one attempt.
    static var isInstalledBuild: Bool {
        !AppVersion.isDevelopmentBuild
            && Bundle.main.bundlePath.contains("/Applications/")
            && ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] == nil
    }

    static func enableOnFirstLaunch(
        defaults: UserDefaults = .standard,
        isInstalledBuild: Bool = LoginItem.isInstalledBuild
    ) {
        guard isInstalledBuild, !defaults.bool(forKey: initialised) else { return }
        if setEnabled(true) { defaults.set(true, forKey: initialised) }
    }
}

/// The preferences that belong to this copy of Acervo rather than to the vocabulary, which lives
/// in the replica and is edited in the interface. Shown in the interface's Settings ▸ General,
/// through `HostSettings`.
@MainActor
final class AppSettings: ObservableObject {
    static let shared = AppSettings()

    private let defaults: UserDefaults

    @Published var showWindowAtLogin: Bool {
        didSet { defaults.set(showWindowAtLogin, forKey: LaunchContext.showWindowAtLoginKey) }
    }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.showWindowAtLogin = defaults.bool(forKey: LaunchContext.showWindowAtLoginKey)
    }
}
