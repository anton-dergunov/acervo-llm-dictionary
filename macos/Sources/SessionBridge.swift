import Foundation
import WebKit

private struct StoredSession: Codable {
    let baseUrl: String
    let email: String
    let token: String
    let userId: String
}

private struct SessionRequest: Decodable {
    let session: StoredSession
}

private struct HostSettingRequest: Decodable {
    let name: String
    let value: Bool
}

/// The interface's one way into the application: its session, and — on Settings ▸ General — the
/// application's own settings (`HostSettings`). A method this does not name is refused.
@MainActor
final class SessionBridge: NSObject, WKScriptMessageHandlerWithReply {
    private enum Keys {
        static let email = "AcervoBackendEmail"
        static let token = "AcervoBackendToken"
        static let userId = "AcervoBackendUserID"
    }

    private let defaults: UserDefaults
    /// Absent in a test host that only exercises the session; asking for settings then is refused.
    private let host: HostSettings?

    init(defaults: UserDefaults = .standard, host: HostSettings? = nil) {
        self.defaults = defaults
        self.host = host
    }

    func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage,
        replyHandler: @escaping @MainActor @Sendable (Any?, String?) -> Void
    ) {
        do {
            guard let envelope = message.body as? [String: Any], let method = envelope["method"] as? String else {
                throw BridgeError.invalid("Malformed bridge request.")
            }
            switch method {
            case "loadSession":
                try success(loadSession(), replyHandler)
            case "saveSession":
                let request: SessionRequest = try decode(envelope["payload"] ?? [:])
                try saveSession(request.session)
                successVoid(replyHandler)
            case "clearSession":
                clearSession()
                successVoid(replyHandler)
            case "hostSettings":
                try success(hostSettings().snapshot(), replyHandler)
            case "setHostSetting":
                let request: HostSettingRequest = try decode(envelope["payload"] ?? [:])
                try success(hostSettings().set(request.name, to: request.value), replyHandler)
            case "checkForUpdates":
                try success(hostSettings().checkForUpdates(), replyHandler)
            case "installUpdate":
                try success(hostSettings().installUpdate(), replyHandler)
            case "restartNow":
                try success(hostSettings().restartNow(), replyHandler)
            default:
                throw BridgeError.invalid("Unknown bridge method.")
            }
        } catch {
            replyHandler(["error": error.localizedDescription], nil)
        }
    }

    private func hostSettings() throws -> HostSettings {
        guard let host else { throw BridgeError.invalid("This copy of Acervo has no settings of its own to show.") }
        return host
    }

    private func loadSession() -> StoredSession? {
        guard let baseURL = defaults.string(forKey: UpdateService.serverURLKey),
              let email = defaults.string(forKey: Keys.email),
              let userId = defaults.string(forKey: Keys.userId) else { return nil }
        return StoredSession(baseUrl: baseURL, email: email, token: defaults.string(forKey: Keys.token) ?? "", userId: userId)
    }

    private func saveSession(_ session: StoredSession) throws {
        guard !session.baseUrl.isEmpty, !session.email.isEmpty, !session.token.isEmpty, !session.userId.isEmpty else {
            throw BridgeError.invalid("The session is incomplete.")
        }
        defaults.set(session.baseUrl, forKey: UpdateService.serverURLKey)
        defaults.set(session.email, forKey: Keys.email)
        defaults.set(session.token, forKey: Keys.token)
        defaults.set(session.userId, forKey: Keys.userId)
    }

    private func clearSession() {
        defaults.removeObject(forKey: Keys.email)
        defaults.removeObject(forKey: Keys.token)
        defaults.removeObject(forKey: Keys.userId)
    }

    private func decode<T: Decodable>(_ object: Any) throws -> T {
        guard JSONSerialization.isValidJSONObject(object) else { throw BridgeError.invalid("Malformed bridge payload.") }
        return try JSONDecoder().decode(T.self, from: JSONSerialization.data(withJSONObject: object))
    }

    private func success<T: Encodable>(_ value: T, _ reply: @escaping (Any?, String?) -> Void) throws {
        let object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(value), options: [.fragmentsAllowed])
        reply(["data": object], nil)
    }

    private func successVoid(_ reply: @escaping (Any?, String?) -> Void) { reply(["data": NSNull()], nil) }
}

private enum BridgeError: LocalizedError {
    case invalid(String)
    var errorDescription: String? { if case .invalid(let message) = self { message } else { nil } }
}
