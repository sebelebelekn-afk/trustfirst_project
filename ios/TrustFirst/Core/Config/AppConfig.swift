import Foundation

/// What the server tells the app on boot. Same endpoint the web client uses, so
/// there is exactly one place that decides which Supabase project, which
/// storage host and which payment mode this build is pointed at — and rotating
/// any of them never requires shipping a new binary through review.
struct RemoteConfig: Decodable, Sendable {
    let supabaseURL: String
    let supabaseAnonKey: String
    let r2Enabled: Bool
    let r2PublicBase: String
    let appPublicURL: String
    let yocoEnabled: Bool
    let yocoMode: String
    let yocoPublicKey: String

    enum CodingKeys: String, CodingKey {
        case supabaseURL = "supabase_url"
        case supabaseAnonKey = "supabase_anon_key"
        case r2Enabled = "r2_enabled"
        case r2PublicBase = "r2_public_base"
        case appPublicURL = "app_public_url"
        case yocoEnabled = "yoco_enabled"
        case yocoMode = "yoco_mode"
        case yocoPublicKey = "yoco_public_key"
    }

    /// True when the wallet is pointed at test keys. The UI must say so on
    /// screen, or a test card looks exactly like a real deposit.
    var isTestPayments: Bool { yocoMode.lowercased() != "live" }
}

@MainActor
@Observable
final class AppConfig {
    /// The Django origin. Everything else is discovered from it at runtime.
    static let backendOrigin = URL(string: "https://trustfirst-project-bt1h.onrender.com")!

    private(set) var remote: RemoteConfig?
    private(set) var loadFailure: String?

    var supabaseURL: URL? { remote.flatMap { URL(string: $0.supabaseURL) } }
    var anonKey: String { remote?.supabaseAnonKey ?? "" }

    private let http = HTTP()

    func load() async {
        do {
            let request = URLRequest.json("GET", url: Self.backendOrigin.appending(path: "api/config/"))
            remote = try await http.send(request, as: RemoteConfig.self)
            loadFailure = nil
        } catch {
            // Boot cannot proceed without this, so the failure is surfaced
            // rather than retried silently behind a spinner that never ends.
            loadFailure = error.localizedDescription
        }
    }
}
