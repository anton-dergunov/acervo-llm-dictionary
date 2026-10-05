import AppKit
import Carbon

/// Whether this launch should put the window on screen, or leave Acervo in the menu bar.
///
/// Opening the app yourself is a request to see it. Being started at login is not: the menu bar is
/// the whole point of running at login, and a window appearing over whatever you were doing while
/// you log in is an interruption nobody asked for.
///
/// The decision is a pure function of the launch's own evidence so it can be tested without logging
/// out and back in.
enum LaunchContext {
    /// Set when someone would rather see the window even on a login launch.
    static let showWindowAtLoginKey = "AcervoShowWindowAtLogin"

    static func startsInMenuBarOnly(launchEvent: NSAppleEventDescriptor?, showWindowAtLogin: Bool) -> Bool {
        if showWindowAtLogin { return false }
        return wasLaunchedAsLoginItem(launchEvent)
    }

    /// The system says so in the event that opens the application. The launchd service name in the
    /// environment looks like the same evidence and is not: every launch through LaunchServices
    /// carries one naming the application, a double-click in the Finder included.
    ///
    /// No event says nothing, which is read as someone having opened it -- the only safe way to be
    /// wrong.
    static func wasLaunchedAsLoginItem(_ event: NSAppleEventDescriptor?) -> Bool {
        guard let event,
              event.eventClass == AEEventClass(kCoreEventClass),
              event.eventID == AEEventID(kAEOpenApplication) else { return false }
        return event.paramDescriptor(forKeyword: AEKeyword(keyAEPropData))?.enumCodeValue
            == OSType(keyAELaunchedAsLogInItem)
    }
}
