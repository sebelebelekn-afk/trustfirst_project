import Foundation

/// A Supabase session, exactly as GoTrue returns it.
struct AuthSession: Decodable, Sendable {
    let accessToken: String
    let refreshToken: String
    var expiresAt: Date

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case expiresIn = "expires_in"
        case expiresAt = "expires_at"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        accessToken = try container.decode(String.self, forKey: .accessToken)
        refreshToken = try container.decode(String.self, forKey: .refreshToken)
        // GoTrue sends expires_in (seconds from now); Django's username-login
        // passes it straight through. Some responses also carry an absolute
        // expires_at. Prefer the absolute one when it is there.
        if let absolute = try container.decodeIfPresent(Double.self, forKey: .expiresAt) {
            expiresAt = Date(timeIntervalSince1970: absolute)
        } else {
            let seconds = try container.decodeIfPresent(Double.self, forKey: .expiresIn) ?? 3600
            expiresAt = Date().addingTimeInterval(seconds)
        }
    }

    /// Refreshed a minute early, so a request is never sent with a token that
    /// expires while it is in flight.
    var isFresh: Bool { expiresAt.timeIntervalSinceNow > 60 }
}

@MainActor
@Observable
final class AuthStore {
    enum State: Equatable {
        case loading
        case signedOut
        case signedIn(userID: String)
    }

    private(set) var state: State = .loading
    private(set) var session: AuthSession?

    private let config: AppConfig
    private let http = HTTP()
    private static let refreshTokenKey = "supabase.refresh_token"

    init(config: AppConfig) {
        self.config = config
    }

    var accessToken: String? { session?.accessToken }

    /// Called once on launch. A stored refresh token is exchanged for a live
    /// session; anything else means signed out, including a refresh token the
    /// server has since revoked — which is what "sign out other devices" does.
    func restore() async {
        guard let refreshToken = Keychain.get(Self.refreshTokenKey) else {
            state = .signedOut
            return
        }
        do {
            try await exchange(grant: "refresh_token", body: ["refresh_token": refreshToken])
        } catch {
            Keychain.remove(Self.refreshTokenKey)
            state = .signedOut
        }
    }

    /// Username sign-in goes through Django, because resolving a username to an
    /// email needs the service key and that key never leaves the server.
    func signIn(username: String, password: String) async throws {
        let request = try URLRequest.json(
            "POST",
            url: AppConfig.backendOrigin.appending(path: "api/auth/username-login/"),
            body: ["username": username, "password": password]
        )
        let session = try await http.send(request, as: AuthSession.self)
        try adopt(session)
    }

    /// Signs in with whatever someone typed, working out for itself whether it
    /// is an email or a username. One rule, in one place, so the sign-in screen
    /// and any automated sign-in can never disagree about what "@" means.
    func signIn(identifier: String, password: String) async throws {
        let trimmed = identifier.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.contains("@") && trimmed.contains(".") {
            try await signIn(email: trimmed, password: password)
        } else {
            try await signIn(username: trimmed, password: password)
        }
    }

    /// Email sign-in can go straight to GoTrue — no server-side lookup needed.
    func signIn(email: String, password: String) async throws {
        try await exchange(grant: "password", body: ["email": email, "password": password])
    }

    func signOut() async {
        if let supabaseURL = config.supabaseURL, let token = accessToken {
            // Best effort: revoke server-side so the refresh token dies too.
            // A failure here still signs this device out locally.
            let request = try? URLRequest.json(
                "POST",
                url: supabaseURL.appending(path: "auth/v1/logout"),
                headers: ["apikey": config.anonKey, "Authorization": "Bearer \(token)"],
                body: [String: String]()
            )
            if let request { _ = try? await http.send(request) }
        }
        Keychain.remove(Self.refreshTokenKey)
        session = nil
        state = .signedOut
    }

    /// Hands back a token guaranteed live, refreshing first if it is close to
    /// expiry. Every authenticated call goes through here.
    func validAccessToken() async throws -> String {
        if let session, session.isFresh { return session.accessToken }
        guard let refreshToken = session?.refreshToken ?? Keychain.get(Self.refreshTokenKey) else {
            state = .signedOut
            throw HTTPError(status: 401, message: "You have been signed out.", body: nil)
        }
        try await exchange(grant: "refresh_token", body: ["refresh_token": refreshToken])
        guard let token = accessToken else {
            throw HTTPError(status: 401, message: "You have been signed out.", body: nil)
        }
        return token
    }

    private func exchange(grant: String, body: [String: String]) async throws {
        guard let supabaseURL = config.supabaseURL else {
            throw HTTPError(status: -1, message: "The app has not finished starting up.", body: nil)
        }
        var components = URLComponents(
            url: supabaseURL.appending(path: "auth/v1/token"),
            resolvingAgainstBaseURL: false
        )!
        components.queryItems = [URLQueryItem(name: "grant_type", value: grant)]
        let request = try URLRequest.json(
            "POST",
            url: components.url!,
            headers: ["apikey": config.anonKey],
            body: body
        )
        let session = try await http.send(request, as: AuthSession.self)
        try adopt(session)
    }

    private func adopt(_ session: AuthSession) throws {
        self.session = session
        Keychain.set(session.refreshToken, for: Self.refreshTokenKey)
        state = .signedIn(userID: try Self.userID(fromJWT: session.accessToken))
    }

    /// The user's id is the JWT's `sub`. Read locally rather than fetched: it
    /// saves a round trip on every launch, and the value is only used to scope
    /// queries that row-level security checks again on the server anyway.
    private static func userID(fromJWT token: String) throws -> String {
        let segments = token.split(separator: ".")
        guard segments.count == 3 else {
            throw HTTPError(status: 401, message: "That sign-in was not accepted.", body: nil)
        }
        var payload = String(segments[1])
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        // Base64url drops the padding that Data(base64Encoded:) insists on.
        while payload.count % 4 != 0 { payload += "=" }
        guard let data = Data(base64Encoded: payload),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let subject = object["sub"] as? String else {
            throw HTTPError(status: 401, message: "That sign-in was not accepted.", body: nil)
        }
        return subject
    }
}
