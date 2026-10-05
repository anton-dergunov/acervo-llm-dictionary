import AppKit
import WebKit

@MainActor
func makeEditMenu() -> NSMenu {
    let menu = NSMenu(title: "Edit")
    menu.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
    let redoItem = menu.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "z")
    redoItem.keyEquivalentModifierMask = [.command, .shift]
    menu.addItem(.separator())
    menu.addItem(withTitle: "Cut", action: Selector(("cut:")), keyEquivalent: "x")
    menu.addItem(withTitle: "Copy", action: Selector(("copy:")), keyEquivalent: "c")
    menu.addItem(withTitle: "Paste", action: Selector(("paste:")), keyEquivalent: "v")
    menu.addItem(withTitle: "Select All", action: Selector(("selectAll:")), keyEquivalent: "a")
    return menu
}

/// The vocabulary itself is the web app's, so these items open the surface that already owns each
/// action rather than reimplementing it natively. A menu, not a second implementation.
@MainActor
func makeVocabularyMenu(target: AnyObject?) -> NSMenu {
    let menu = NSMenu(title: "Vocabulary")
    let export = menu.addItem(
        withTitle: "Export Vocabulary…", action: #selector(AppDelegate.exportVocabulary), keyEquivalent: "e"
    )
    export.keyEquivalentModifierMask = [.command, .shift]
    let load = menu.addItem(
        withTitle: "Import Vocabulary…", action: #selector(AppDelegate.importVocabulary), keyEquivalent: "i"
    )
    load.keyEquivalentModifierMask = [.command, .shift]
    menu.addItem(.separator())
    // No shortcut on deletion: it is the one action re-syncing cannot undo.
    menu.addItem(
        withTitle: "Delete All Words…", action: #selector(AppDelegate.deleteAllWords), keyEquivalent: ""
    )
    for item in menu.items where item.action != nil { item.target = target }
    return menu
}

@main
struct AcervoApplication {
    static func main() {
        let application = NSApplication.shared
        let delegate = AppDelegate()
        application.delegate = delegate
        application.run()
        withExtendedLifetime(delegate) {}
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    private var window: NSWindow!
    private var webView: AcervoWebView!
    private var interfaceServer: InterfaceServer?
    private var interfaceFailure: String?
    private let sessionBridge = SessionBridge()
    private var menuBar: MenuBarController!
    private let updates = UpdateService()
    private let settings = SettingsWindowController()
    /// Where each in-flight download is going, so the finished file can be revealed rather than lost.
    private var downloadDestinations: [ObjectIdentifier: URL] = [:]

    func applicationDidFinishLaunching(_ notification: Notification) {
        installMainMenu()
        createWindow()
        menuBar = MenuBarController(
            openWindow: { [weak self] in self?.showWindow() },
            restartToUpdate: { [weak self] in self?.updates.restartNow() },
            checkForUpdates: { [weak self] in self?.checkForUpdates() }
        )
        // Started at login, Acervo is here for the menu bar; a window over whatever someone is doing
        // as they log in is an interruption nobody asked for. Opening it yourself always shows the
        // window. The interface is loaded either way.
        let startsQuietly = LaunchContext.startsInMenuBarOnly(
            launchEvent: NSAppleEventManager.shared().currentAppleEvent,
            showWindowAtLogin: AppSettings.shared.showWindowAtLogin
        )
        if startsQuietly {
            NSApp.setActivationPolicy(.accessory)
        } else {
            showWindow()
        }
        LoginItem.enableOnFirstLaunch()

        // An update never opens a window or takes focus; the menu bar carries it until it is wanted.
        updates.onUpdateMarkChanged = { [weak self] mark in self?.menuBar.setUpdateMark(mark) }
        menuBar.setUpdateMark(updates.currentMark)
        updates.start()

        // Asking for the address is a window too, so a quiet start leaves it for the next opening.
        if !updates.hasServerURL, !startsQuietly {
            DispatchQueue.main.async { [weak self] in self?.showSettings(.general) }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showWindow()
        return true
    }

    /// Hides the Dock icon once nothing of Acervo's is left on screen; the status item stays. Both
    /// the main window and the Settings window report their closing here, and neither of them going
    /// away is on its own a reason to give up the menu bar.
    func windowWillClose(_ notification: Notification) {
        AppActivation.returnToMenuBar(owning: [window, settings.openWindow])
    }

    private func createWindow() {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.userContentController.addScriptMessageHandler(sessionBridge, contentWorld: .page, name: "acervo")
        configuration.userContentController.addUserScript(WKUserScript(
            source: WebInterface.startupDiagnostics,
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        ))
        // Loopback HTTP rather than the custom scheme, so the page has a real web origin and can
        // embed somebody else's player. See `InterfaceServer` for why the port never moves.
        //
        // The scheme handler stays registered for the tests and for anything still addressing it,
        // but it is deliberately *not* a fallback: its storage is a different origin, so falling
        // back would open on an empty replica and call it your vocabulary.
        if let interfaceRoot = WebInterface.bundledInterfaceDirectory() {
            let server = InterfaceServer(root: interfaceRoot)
            do {
                try server.start()
                interfaceServer = server
            } catch {
                if case .message(let said)? = error as? UpdateFailure {
                    interfaceFailure = said
                } else {
                    interfaceFailure = error.localizedDescription
                }
            }
            configuration.setURLSchemeHandler(WebInterfaceSchemeHandler(root: interfaceRoot), forURLScheme: WebInterface.scheme)
        }
        webView = AcervoWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        // Without this the file input for importing a bundle opens no panel at all, silently.
        webView.uiDelegate = self

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 960, height: 680),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Acervo"
        window.minSize = NSSize(width: 560, height: 420)
        window.contentView = webView
        window.delegate = self
        window.isReleasedWhenClosed = false
        window.setFrameAutosaveName("AcervoMainWindow")
        window.center()

        if let served = interfaceServer?.startURL {
            webView.load(URLRequest(url: served))
        } else if let failure = interfaceFailure {
            showLoadError(failure)
        } else {
            showLoadError("The bundled web interface is missing. Rebuild the application.")
        }
    }

    private func showWindow() {
        AppActivation.bringForward(window)
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping @MainActor @Sendable (WKNavigationActionPolicy) -> Void
    ) {
        // Exporting hands the page a blob to save. Allowing it instead of downloading it drops the
        // file on the floor with no error anywhere.
        if navigationAction.shouldPerformDownload {
            decisionHandler(.download)
        } else if navigationAction.navigationType == .linkActivated,
           let url = navigationAction.request.url,
           ["http", "https"].contains(url.scheme?.lowercased() ?? "") {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
        } else { decisionHandler(.allow) }
    }

    // MARK: - Saving and choosing files

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    func download(
        _ download: WKDownload,
        decideDestinationUsing response: URLResponse,
        suggestedFilename: String,
        completionHandler: @escaping @MainActor @Sendable (URL?) -> Void
    ) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        panel.canCreateDirectories = true
        showWindow()
        panel.beginSheetModal(for: window) { [weak self] outcome in
            guard outcome == .OK, let url = panel.url else {
                completionHandler(nil)
                return
            }
            // The panel already asked about replacing; WKDownload refuses a destination that exists.
            try? FileManager.default.removeItem(at: url)
            self?.downloadDestinations[ObjectIdentifier(download)] = url
            completionHandler(url)
        }
    }

    func downloadDidFinish(_ download: WKDownload) {
        if let url = downloadDestinations.removeValue(forKey: ObjectIdentifier(download)) {
            NSWorkspace.shared.activateFileViewerSelecting([url])
        }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        downloadDestinations.removeValue(forKey: ObjectIdentifier(download))
        let alert = NSAlert()
        alert.messageText = "The export could not be saved"
        alert.informativeText = error.localizedDescription
        alert.runModal()
    }

    func webView(
        _ webView: WKWebView,
        runOpenPanelWith parameters: WKOpenPanelParameters,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping @MainActor @Sendable ([URL]?) -> Void
    ) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.beginSheetModal(for: window) { outcome in
            completionHandler(outcome == .OK ? panel.urls : nil)
        }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        showLoadError(error.localizedDescription)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        showLoadError(error.localizedDescription)
    }

    private func showLoadError(_ message: String) {
        let escaped = message
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
        webView.loadHTMLString("<main style='font:16px -apple-system;padding:48px'><h1>Unable to open Acervo</h1><p>\(escaped)</p></main>", baseURL: nil)
    }

    private func installMainMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        let aboutItem = appMenu.addItem(withTitle: "About Acervo", action: #selector(showAbout), keyEquivalent: "")
        aboutItem.target = self
        let updateItem = appMenu.addItem(withTitle: "Check for Updates…", action: #selector(checkForUpdates), keyEquivalent: "")
        updateItem.target = self
        appMenu.addItem(.separator())
        let settingsItem = appMenu.addItem(withTitle: "Settings…", action: #selector(showSettingsMenu), keyEquivalent: ",")
        settingsItem.target = self
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit Acervo", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        main.addItem(appItem)

        let editItem = NSMenuItem()
        editItem.submenu = makeEditMenu()
        main.addItem(editItem)

        let vocabularyItem = NSMenuItem()
        vocabularyItem.submenu = makeVocabularyMenu(target: self)
        main.addItem(vocabularyItem)

        let windowItem = NSMenuItem()
        let windowMenu = NSMenu(title: "Window")
        windowMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        windowItem.submenu = windowMenu
        main.addItem(windowItem)
        NSApp.mainMenu = main
        // Held so coming forward from the menu bar can put it back: the bar is rebuilt for whichever
        // application is frontmost, and a policy change alone does not make that happen.
        AppActivation.mainMenu = main
        NSApp.windowsMenu = windowMenu
    }

    @objc private func showAbout() {
        NSApp.orderFrontStandardAboutPanel(options: [
            .applicationName: "Acervo",
            .applicationVersion: AppVersion.name,
            .version: AppVersion.build
        ])
    }

    @objc private func checkForUpdates() {
        showSettings(.updates)
        Task { [weak self] in await self?.updates.check(force: true) }
    }

    @objc private func showSettingsMenu() { showSettings(.general) }

    @objc fileprivate func exportVocabulary() { open("export") }
    @objc fileprivate func importVocabulary() { open("import") }
    @objc fileprivate func deleteAllWords() { open("delete") }

    /// Every confirmation, and every write, stays on the side that owns the vocabulary.
    ///
    /// The name travels as an argument rather than inside the source. Today it is one of three
    /// literals, so nothing can go wrong; a command that one day carries text somebody selected must
    /// not be able to close the string literal it was pasted into and run as script in the origin
    /// that holds the session.
    private func open(_ command: String) {
        showWindow()
        webView.callAsyncJavaScript(
            "window.acervo?.command(name)",
            arguments: ["name": command],
            in: nil,        // every frame
            in: .page,      // the page's own world, where `window.acervo` is installed
            // Fire and forget, as the call it replaced was: the menu asks, and the surface that owns
            // the vocabulary decides what to show. Naming the handler also picks this overload over
            // the `async throws` one, which a menu action cannot await.
            completionHandler: nil
        )
    }

    private func showSettings(_ pane: SettingsView.Pane) {
        settings.show(
            updates: updates,
            pane: pane,
            checkNow: { [weak self] in Task { await self?.updates.check(force: true) } },
            installUpdate: { [weak self] in Task { await self?.updates.install(thenRestart: true) } },
            restartNow: { [weak self] in self?.updates.restartNow() }
        )
        settings.openWindow?.delegate = self
    }
}
