import Carbon
import CryptoKit
import WebKit
import XCTest
@testable import Acervo

final class NavigationProbe: NSObject, WKNavigationDelegate {
    let finished: XCTestExpectation
    init(_ finished: XCTestExpectation) { self.finished = finished }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { finished.fulfill() }
}

final class StubURLProtocol: URLProtocol {
    nonisolated(unsafe) static var body = Data()
    nonisolated(unsafe) static var ignoresRanges = false
    nonisolated(unsafe) static var rangesAsked: [String] = []

    static func reset() {
        body = Data()
        ignoresRanges = false
        rangesAsked = []
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        var payload = Self.body
        var status = 200
        if let header = request.value(forHTTPHeaderField: "Range") {
            Self.rangesAsked.append(header)
            if !Self.ignoresRanges, let range = Self.slice(header, of: Self.body.count) {
                payload = Self.body.subdata(in: range)
                status = 206
            }
        }
        let response = HTTPURLResponse(
            url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: nil
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: payload)
        client?.urlProtocolDidFinishLoading(self)
    }

    private static func slice(_ header: String, of count: Int) -> Range<Int>? {
        let numbers = header.replacingOccurrences(of: "bytes=", with: "").split(separator: "-")
        guard numbers.count == 2, let first = Int(numbers[0]), let last = Int(numbers[1]),
              first < count else { return nil }
        return first..<min(last + 1, count)
    }
}

final class AcervoTests: XCTestCase {
    @MainActor
    func testVocabularyMenuOffersTransferAndDeletion() {
        let menu = makeVocabularyMenu(target: nil)
        XCTAssertEqual(
            menu.items.map(\.title),
            ["Export Vocabulary…", "Import Vocabulary…", "", "Delete All Words…"]
        )
        // Deleting has no shortcut on purpose: it is the one action re-syncing cannot undo.
        XCTAssertEqual(menu.items[0].keyEquivalent, "e")
        XCTAssertEqual(menu.items[0].keyEquivalentModifierMask, [.command, .shift])
        XCTAssertEqual(menu.items[1].keyEquivalent, "i")
        XCTAssertEqual(menu.items[3].keyEquivalent, "")
    }

    /// Opening the app is a request to see it. Being started at login is not, and the system says
    /// which this is in the event that opens the application.
    func testALoginLaunchStaysInTheMenuBarAndOpeningTheAppDoesNot() {
        func openEvent(asLoginItem: Bool) -> NSAppleEventDescriptor {
            let event = NSAppleEventDescriptor(
                eventClass: AEEventClass(kCoreEventClass),
                eventID: AEEventID(kAEOpenApplication),
                targetDescriptor: nil,
                returnID: AEReturnID(kAutoGenerateReturnID),
                transactionID: AETransactionID(kAnyTransactionID)
            )
            if asLoginItem {
                event.setParam(
                    NSAppleEventDescriptor(enumCode: OSType(keyAELaunchedAsLogInItem)),
                    forKeyword: AEKeyword(keyAEPropData)
                )
            }
            return event
        }

        XCTAssertTrue(LaunchContext.startsInMenuBarOnly(
            launchEvent: openEvent(asLoginItem: true), showWindowAtLogin: false))
        XCTAssertFalse(LaunchContext.startsInMenuBarOnly(
            launchEvent: openEvent(asLoginItem: false), showWindowAtLogin: false))
        // Someone who would rather see the window at login says so, and that answer wins.
        XCTAssertFalse(LaunchContext.startsInMenuBarOnly(
            launchEvent: openEvent(asLoginItem: true), showWindowAtLogin: true))
        // No evidence at all means someone opened it, which is the only safe way to be wrong.
        XCTAssertFalse(LaunchContext.startsInMenuBarOnly(launchEvent: nil, showWindowAtLogin: false))
    }

    /// Closing the main window used to drop straight back to the menu bar, which took the Dock icon
    /// and the menu bar out from under the Settings window standing beside it.
    @MainActor
    func testTheMenuBarIsKeptWhileAnyAcervoWindowIsStillOnScreen() {
        func testWindow() -> NSWindow {
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 200, height: 120),
                styleMask: [.titled, .closable],
                backing: .buffered,
                defer: false
            )
            window.isReleasedWhenClosed = false
            return window
        }
        let main = testWindow()
        let settings = testWindow()
        defer { main.orderOut(nil); settings.orderOut(nil) }

        settings.orderFront(nil)
        XCTAssertFalse(AppActivation.shouldReturnToMenuBar(owning: [main, settings]),
                       "the Dock icon was given up with Settings still open")

        settings.orderOut(nil)
        XCTAssertTrue(AppActivation.shouldReturnToMenuBar(owning: [main, settings]))
        XCTAssertTrue(AppActivation.shouldReturnToMenuBar(owning: [nil, nil]))
    }

    /// The menu bar follows activation rather than the activation policy, so coming forward has to
    /// put Acervo's own menu back even when the application already believes it is active.
    @MainActor
    func testComingForwardRestoresAcervosOwnMenuBar() async {
        let ours = NSApp.mainMenu
        let held = AppActivation.mainMenu
        defer { AppActivation.mainMenu = held; NSApp.mainMenu = ours }
        let menu = NSMenu(title: "Acervo")
        AppActivation.mainMenu = menu
        NSApp.mainMenu = NSMenu(title: "Another application")

        AppActivation.bringForward(nil)
        let settled = expectation(description: "the deferred pass has run")
        DispatchQueue.main.async { settled.fulfill() }
        await fulfillment(of: [settled], timeout: 2)

        XCTAssertTrue(NSApp.mainMenu === menu, "coming forward left another application's menu on show")
    }

    @MainActor
    func testShowingTheWindowAtLoginIsRememberedAndOffUntilAsked() throws {
        let suite = "AcervoTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }

        XCTAssertFalse(AppSettings(defaults: defaults).showWindowAtLogin)
        AppSettings(defaults: defaults).showWindowAtLogin = true
        XCTAssertTrue(AppSettings(defaults: defaults).showWindowAtLogin)
    }

    /// A development build and the test host share the installed application's preferences, so
    /// neither may spend the one attempt at registering.
    func testOnlyAnInstalledBuildRegistersItselfAtFirstLaunch() throws {
        let suite = "AcervoTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }

        LoginItem.enableOnFirstLaunch(defaults: defaults, isInstalledBuild: false)
        XCTAssertNil(defaults.object(forKey: "AcervoLoginItemInitialised"))
    }

    func testReleaseComparisonUsesBuildStamp() {
        let release = MacRelease(version: "0.1.0", build: "202608271230", file: "a.zip", size: 1, sha256: "x", url: "/a.zip")
        XCTAssertTrue(release.isNewer(than: "202608271229"))
        XCTAssertFalse(release.isNewer(than: "202608271230"))
        XCTAssertFalse(release.isNewer(than: "202608271231"))
    }

    func testServerAddressRequiresSecurePublicOrigin() throws {
        XCTAssertEqual(try ServerAddress.normalize(" https://acervo.example.com/api/acervo/v1/ "), "https://acervo.example.com")
        XCTAssertEqual(try ServerAddress.normalize("http://localhost:27702/"), "http://localhost:27702")
        XCTAssertThrowsError(try ServerAddress.normalize("http://acervo.example.com"))
        XCTAssertThrowsError(try ServerAddress.normalize("https://user:secret@acervo.example.com"))
    }

    func testStatusClicksSeparateOpenAndContextMenu() {
        XCTAssertEqual(statusClickAction(for: .leftMouseUp), .openWindow)
        XCTAssertEqual(statusClickAction(for: .rightMouseUp), .showMenu)
        XCTAssertEqual(statusClickAction(for: nil), .openWindow)
    }

    @MainActor
    func testTheContextMenuKeepsEverythingButTheWaysToNavigateAway() {
        // Acervo has no routing, so each of these throws away the open word and lands on the default
        // list. What is left is what a context menu is actually for here.
        let menu = NSMenu()
        for (title, identifier) in [
            ("Back", "WKMenuItemIdentifierGoBack"),
            ("Forward", "WKMenuItemIdentifierGoForward"),
            ("Reload", "WKMenuItemIdentifierReload"),
        ] {
            let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
            item.identifier = NSUserInterfaceItemIdentifier(identifier)
            menu.addItem(item)
        }
        menu.addItem(.separator())
        let copy = NSMenuItem(title: "Copy", action: nil, keyEquivalent: "")
        copy.identifier = NSUserInterfaceItemIdentifier("WKMenuItemIdentifierCopy")
        menu.addItem(copy)
        menu.addItem(NSMenuItem(title: "Inspect Element", action: nil, keyEquivalent: ""))

        pruneNavigationItems(from: menu)

        XCTAssertEqual(menu.items.map(\.title), ["Copy", "Inspect Element"])
    }

    @MainActor
    func testAMenuOfNothingButNavigationIsLeftEmptyRatherThanARule() {
        let menu = NSMenu()
        let reload = NSMenuItem(title: "Reload", action: nil, keyEquivalent: "")
        reload.identifier = NSUserInterfaceItemIdentifier("WKMenuItemIdentifierReload")
        menu.addItem(reload)
        menu.addItem(.separator())

        pruneNavigationItems(from: menu)

        XCTAssertTrue(menu.items.isEmpty)
    }

    @MainActor
    func testEditMenuProvidesStandardTextFieldShortcuts() throws {
        let menu = makeEditMenu()
        let expected = ["Cut": "x", "Copy": "c", "Paste": "v", "Select All": "a"]
        for (title, shortcut) in expected {
            let item = try XCTUnwrap(menu.item(withTitle: title))
            XCTAssertEqual(item.keyEquivalent, shortcut)
            XCTAssertEqual(item.keyEquivalentModifierMask, .command)
        }
        XCTAssertEqual(menu.item(withTitle: "Paste")?.action, Selector(("paste:")))
    }

    @MainActor
    func testMenuBarIconIsACompactTemplateImage() {
        let icon = makeMenuBarIcon(accessibilityDescription: "Acervo")
        // Wider than the book: the trailing points are reserved for the update mark.
        XCTAssertEqual(icon.size, NSSize(width: 27, height: 18))
        XCTAssertTrue(icon.isTemplate)
        XCTAssertEqual(icon.accessibilityDescription, "Acervo")
        XCTAssertNotNil(icon.tiffRepresentation)
    }

    @MainActor
    func testMenuBarIconCanShowAnUpdateMark() {
        let icon = makeMenuBarIcon(
            accessibilityDescription: "Acervo; an update is available",
            updateAvailable: true
        )
        XCTAssertTrue(icon.isTemplate)
        XCTAssertEqual(icon.accessibilityDescription, "Acervo; an update is available")
        // The mark must actually be drawn, not merely described.
        XCTAssertNotEqual(
            icon.tiffRepresentation,
            makeMenuBarIcon(accessibilityDescription: "Acervo").tiffRepresentation
        )
    }

    @MainActor
    func testStatusMenuOffersARestartOnlyWhenAnUpdateIsWaiting() {
        XCTAssertEqual(makeStatusMenu(mark: nil, target: nil).items.map(\.title), ["Quit Acervo"])
        XCTAssertEqual(
            makeStatusMenu(mark: .pendingRestart(build: "202608271230"), target: nil).items.map(\.title),
            ["Restart to Update", "", "Quit Acervo"]
        )
        let release = MacRelease(version: "0.1.0", build: "202608271230", file: "a.zip", size: 1, sha256: "x", url: "/a.zip")
        XCTAssertEqual(
            makeStatusMenu(mark: .available(release), target: nil).items.map(\.title),
            ["Check for Updates…", "", "Quit Acervo"]
        )
    }

    @MainActor
    func testAnInstalledUpdateIsNotOfferedAgainAndKeepsMarkingTheMenuBar() async throws {
        defer { StubURLProtocol.reset() }
        StubURLProtocol.body = Data(
            #"{"data":{"version":"9.9.9","build":"999999999999","file":"Acervo.zip","size":1,"sha256":"x","url":"/api/acervo/downloads/Acervo.zip"}}"#.utf8
        )
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubURLProtocol.self]
        let defaultsSuite = UUID().uuidString
        let defaults = UserDefaults(suiteName: defaultsSuite)!
        defer { defaults.removePersistentDomain(forName: defaultsSuite) }
        defaults.set("https://acervo.example.com", forKey: UpdateService.serverURLKey)
        // Already installed by an earlier background check, waiting for the next launch.
        defaults.set("999999999999", forKey: "AcervoPendingUpdateBuild")

        let updates = UpdateService(defaults: defaults, session: URLSession(configuration: configuration))
        XCTAssertEqual(updates.pendingBuild, "999999999999")
        await updates.check(force: true)

        XCTAssertNil(updates.available, "An installed build must not be downloaded again on every check")
        XCTAssertEqual(updates.currentMark, .pendingRestart(build: "999999999999"))
    }

    func testSchemeHandlerRefusesTraversalAndKnowsTypes() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try Data("ok".utf8).write(to: root.appendingPathComponent("index.html"))
        let handler = WebInterfaceSchemeHandler(root: root)
        XCTAssertNotNil(handler.resolveForTesting(URL(string: "acervo://app/index.html")!))
        XCTAssertNil(handler.resolveForTesting(URL(string: "acervo://app/../outside")!))
        XCTAssertEqual(WebInterfaceSchemeHandler.contentType(for: "js"), "text/javascript; charset=utf-8")
        XCTAssertEqual(WebInterfaceSchemeHandler.contentType(for: "webmanifest"), "application/json; charset=utf-8")
    }

    func testChecksumAndSizeAreVerified() throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let data = Data("acervo".utf8)
        try data.write(to: file)
        defer { try? FileManager.default.removeItem(at: file) }
        let checksum = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        XCTAssertNoThrow(try UpdateService.verify(file, size: data.count, sha256: checksum))
        XCTAssertThrowsError(try UpdateService.verify(file, size: data.count + 1, sha256: checksum))
        XCTAssertThrowsError(try UpdateService.verify(file, size: data.count, sha256: String(repeating: "0", count: 64)))
    }

    @MainActor
    func testArchiveIsAssembledFromRangedChunks() async throws {
        defer { StubURLProtocol.reset() }
        let size = 1_048_576 * 2 + 500
        StubURLProtocol.body = Data((0..<size).map { UInt8($0 % 251) })
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubURLProtocol.self]
        let defaultsSuite = UUID().uuidString
        let defaults = UserDefaults(suiteName: defaultsSuite)!
        defer { defaults.removePersistentDomain(forName: defaultsSuite) }
        let updates = UpdateService(
            defaults: defaults,
            session: URLSession(configuration: configuration)
        )
        let url = try XCTUnwrap(URL(string: "https://acervo.example.com/api/acervo/downloads/Acervo.zip"))

        let file = try await updates.downloadForTesting(url, size: size)
        defer { try? FileManager.default.removeItem(at: file) }

        XCTAssertEqual(try Data(contentsOf: file), StubURLProtocol.body)
        XCTAssertEqual(StubURLProtocol.rangesAsked, [
            "bytes=0-1048575",
            "bytes=1048576-2097151",
            "bytes=2097152-2097651",
        ])
    }

    func testReleaseManifestEnvelopeDecodesAbsentAndPresentReleases() throws {
        let decoder = JSONDecoder()
        XCTAssertNil(try decoder.decode(MacRelease.Envelope.self, from: Data(#"{"data":null}"#.utf8)).data)
        let manifest = Data(#"{"data":{"version":"0.1.0","build":"202608270001","file":"Acervo.zip","size":42,"sha256":"abc","url":"/api/acervo/downloads/Acervo.zip"}}"#.utf8)
        let release = try decoder.decode(MacRelease.Envelope.self, from: manifest).data
        XCTAssertEqual(release?.build, "202608270001")
        XCTAssertEqual(release?.size, 42)
    }

    @MainActor
    func testBundledInterfaceRendersAndHasIndexedDB() async throws {
        guard let root = WebInterface.bundledInterfaceDirectory() else {
            return XCTFail("The test host did not bundle web/dist")
        }
        let defaultsSuite = "AcervoTests.WebInterface.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: defaultsSuite))
        addTeardownBlock { defaults.removePersistentDomain(forName: defaultsSuite) }
        let configuration = WKWebViewConfiguration()
        let bridge = SessionBridge(defaults: defaults)
        configuration.userContentController.addScriptMessageHandler(bridge, contentWorld: .page, name: "acervo")
        configuration.setURLSchemeHandler(WebInterfaceSchemeHandler(root: root), forURLScheme: WebInterface.scheme)
        let webView = WKWebView(frame: .init(x: 0, y: 0, width: 800, height: 600), configuration: configuration)
        let window = NSWindow(contentRect: webView.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = webView
        window.orderFront(nil)
        addTeardownBlock { @MainActor in
            window.close()
            configuration.userContentController.removeScriptMessageHandler(forName: "acervo")
        }
        let loaded = expectation(description: "Acervo interface loaded")
        let probe = NavigationProbe(loaded)
        webView.navigationDelegate = probe
        webView.load(URLRequest(url: WebInterface.startURL))
        await fulfillment(of: [loaded], timeout: 10)
        try await Task.sleep(for: .milliseconds(500))
        let title = try await webView.evaluateJavaScript("document.querySelector('h1')?.textContent") as? String
        XCTAssertEqual(title, "Acervo")
        let signInField = try await webView.evaluateJavaScript(
            "document.querySelector('#serverUrl') ? true : false"
        ) as? Bool
        XCTAssertEqual(signInField, true, "The host must load the real interface, not a placeholder")
        let indexedDB = try await webView.callAsyncJavaScript(
            "return await new Promise(resolve => { const request = indexedDB.open('acervo-host-test'); request.onsuccess = () => { request.result.close(); resolve(true); }; request.onerror = () => resolve(false); });",
            arguments: [:],
            in: nil,
            contentWorld: .page
        ) as? Bool
        XCTAssertEqual(indexedDB, true)
        withExtendedLifetime((probe, bridge)) {}
    }
}

final class InterfaceServerTests: XCTestCase {
    /// A fresh preferences suite per case, so a remembered port never leaks between tests.
    /// Named rather than torn down in a `@Sendable` block: the server is not `Sendable`, and every
    /// case below stops it with `defer` instead.
    private func suite(_ name: String) throws -> UserDefaults {
        let domain = "AcervoTests.InterfaceServer.\(name)"
        UserDefaults.standard.removePersistentDomain(forName: domain)
        return try XCTUnwrap(UserDefaults(suiteName: domain))
    }

    private func bundled() throws -> URL {
        guard let root = WebInterface.bundledInterfaceDirectory() else {
            throw XCTSkip("The test host did not bundle web/dist")
        }
        return root
    }

    func testItServesTheInterfaceFromALoopbackOrigin() async throws {
        // The whole reason this exists: `acervo://app` is not a web origin, so an embedded YouTube
        // player answers with error 153 and nothing the page does can satisfy it.
        let server = InterfaceServer(root: try bundled(), defaults: try suite(#function))
        try server.start()
        defer { server.stop() }

        let start = try XCTUnwrap(server.startURL)
        XCTAssertEqual(start.scheme, "http")
        XCTAssertEqual(start.host, "127.0.0.1", "must be loopback: it is a secure context, a LAN address is not")

        let (data, response) = try await URLSession.shared.data(from: start)
        let http = try XCTUnwrap(response as? HTTPURLResponse)
        XCTAssertEqual(http.statusCode, 200)
        XCTAssertEqual(http.value(forHTTPHeaderField: "Content-Type"), "text/html; charset=utf-8")
        XCTAssertTrue(String(decoding: data, as: UTF8.self).contains("<title>Acervo</title>"))
    }

    func testTheOriginIsTheSameOnEveryLaunch() throws {
        // Storage is keyed by origin and the origin contains the port, so a port that moved between
        // launches would throw the replica away — and a thrown-away replica can only be refilled
        // from the server, which is precisely what is missing when you are offline.
        let root = try bundled()
        let defaults = try suite(#function)

        let first = InterfaceServer(root: root, defaults: defaults)
        try first.start()
        let origin = first.origin
        XCTAssertEqual(first.port, InterfaceServer.defaultPort)
        first.stop()

        let second = InterfaceServer(root: root, defaults: defaults)
        try second.start()
        defer { second.stop() }
        XCTAssertEqual(second.origin, origin, "the origin must not move between launches")
    }

    func testThePortIsOutsideTheRangeTheSystemHandsOut() {
        // Ephemeral ports are what the system assigns to outbound connections, so a port taken from
        // there could be held by any program's client socket by the time Acervo next opens.
        XCTAssertLessThan(InterfaceServer.defaultPort, 49152)
        XCTAssertGreaterThan(InterfaceServer.defaultPort, 1023, "and not a privileged one")
    }

    func testAPortSomebodyElseHoldsIsSaidRatherThanWorkedAround() throws {
        // Moving to another port would open on a different origin, show an empty vocabulary, and
        // call it yours. Naming the port is something a person can act on.
        let root = try bundled()
        let defaults = try suite(#function)

        let holder = InterfaceServer(root: root, defaults: defaults)
        try holder.start()
        defer { holder.stop() }

        let second = InterfaceServer(root: root, defaults: defaults)
        XCTAssertThrowsError(try second.start()) { error in
            guard case UpdateFailure.message(let said) = error else {
                return XCTFail("expected a message naming the port, got \(error)")
            }
            XCTAssertTrue(said.contains(String(InterfaceServer.defaultPort)), said)
            XCTAssertTrue(said.contains("AcervoInterfacePort"), "and how to move it deliberately")
        }
        XCTAssertEqual(second.port, 0, "nothing is served, so nothing can be served from elsewhere")
    }

    func testTheOverrideIsHonoured() throws {
        let defaults = try suite(#function)
        defaults.set(28999, forKey: InterfaceServer.portDefaultsKey)
        let server = InterfaceServer(root: try bundled(), defaults: defaults)
        try server.start()
        defer { server.stop() }
        XCTAssertEqual(server.port, 28999)
    }

    func testItServesNothingOutsideTheBundledRoot() throws {
        let root = try bundled()
        for escape in ["/../../../../etc/passwd", "/..%2f..%2fetc%2fpasswd", "/does-not-exist.js"] {
            XCTAssertNil(InterfaceServer.resolve(escape, root: root), "\(escape) must not resolve")
        }
        XCTAssertNotNil(InterfaceServer.resolve("/index.html", root: root))
        XCTAssertNotNil(InterfaceServer.resolve("/", root: root), "the root is the entry point")
    }

    func testOnlyGetIsAnswered() {
        XCTAssertEqual(InterfaceServer.requestedPath(Data("GET /index.html HTTP/1.1\r\n\r\n".utf8)), "/index.html")
        XCTAssertEqual(InterfaceServer.requestedPath(Data("GET /a.js?v=1 HTTP/1.1\r\n\r\n".utf8)), "/a.js")
        // The interface is static; anything that writes is the Acervo server's business, not this one's.
        XCTAssertNil(InterfaceServer.requestedPath(Data("POST /index.html HTTP/1.1\r\n\r\n".utf8)))
        XCTAssertNil(InterfaceServer.requestedPath(Data("garbage".utf8)))
    }

    @MainActor
    func testTheInterfaceRunsFromTheServedOriginWithASecureContext() async throws {
        // `crypto.getRandomValues` mints every record id, and it is only available in a secure
        // context. `http://127.0.0.1` is one by specification; a LAN address would not be.
        let server = InterfaceServer(root: try bundled(), defaults: try suite(#function))
        try server.start()
        defer { server.stop() }

        let webView = WKWebView(frame: .init(x: 0, y: 0, width: 800, height: 600))
        let window = NSWindow(contentRect: webView.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = webView
        window.orderFront(nil)
        defer { window.close() }

        let loaded = expectation(description: "interface loaded over loopback")
        let probe = NavigationProbe(loaded)
        webView.navigationDelegate = probe
        let port = server.port
        webView.load(URLRequest(url: try XCTUnwrap(server.startURL)))
        await fulfillment(of: [loaded], timeout: 15)
        try await Task.sleep(for: .milliseconds(500))

        let origin = try await webView.evaluateJavaScript("window.location.origin") as? String
        XCTAssertEqual(origin, "http://127.0.0.1:\(port)")
        XCTAssertEqual(port, InterfaceServer.defaultPort)
        let secure = try await webView.evaluateJavaScript("window.isSecureContext") as? Bool
        XCTAssertEqual(secure, true, "without this, crypto.getRandomValues is unavailable and no id can be minted")
        let minted = try await webView.evaluateJavaScript(
            "(() => { const b = new Uint8Array(4); crypto.getRandomValues(b); return b.length; })()"
        ) as? Int
        XCTAssertEqual(minted, 4)
    }
}
