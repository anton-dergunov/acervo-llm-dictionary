import AppKit
import ServiceManagement
import SwiftUI

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
/// in the replica and is edited in the interface.
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

/// Drives the selected pane from outside the SwiftUI hierarchy, so a menu item can open Settings
/// on the pane it is about.
@MainActor
final class SettingsRouter: ObservableObject {
    static let shared = SettingsRouter()
    @Published var pane: SettingsView.Pane = .general
    private init() {}
}

@MainActor
final class SettingsWindowController {
    private var window: NSWindow?

    /// The Settings window, once there is one. Offered so the application can ask whether anything
    /// of its own is still on screen before it goes back to being a menu-bar accessory.
    var openWindow: NSWindow? { window }

    func show(
        updates: UpdateService,
        pane: SettingsView.Pane,
        checkNow: @escaping () -> Void,
        installUpdate: @escaping () -> Void,
        restartNow: @escaping () -> Void
    ) {
        SettingsRouter.shared.pane = pane
        if let window {
            AppActivation.bringForward(window)
            return
        }
        let controller = NSHostingController(
            rootView: SettingsView(
                updates: updates,
                checkNow: checkNow,
                installUpdate: installUpdate,
                restartNow: restartNow
            )
            .environmentObject(AppSettings.shared)
            .environmentObject(SettingsRouter.shared)
        )
        let window = NSWindow(contentViewController: controller)
        window.title = "Acervo Settings"
        window.styleMask = [.titled, .closable, .miniaturizable, .resizable]
        window.collectionBehavior = [.fullScreenAuxiliary]
        window.isReleasedWhenClosed = false
        window.setContentSize(NSSize(width: 620, height: 440))
        window.minSize = NSSize(width: 560, height: 380)
        window.setFrameAutosaveName("AcervoSettingsWindow")
        window.center()
        self.window = window
        AppActivation.bringForward(window)
    }
}
