import SwiftUI

@main
struct TrustFirstApp: App {
    @State private var config: AppConfig
    @State private var auth: AuthStore
    @State private var database: Database

    init() {
        let config = AppConfig()
        let auth = AuthStore(config: config)
        _config = State(initialValue: config)
        _auth = State(initialValue: auth)
        _database = State(initialValue: Database(config: config, auth: auth))
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(config)
                .environment(auth)
                .environment(database)
                .tint(TF.Colour.accent)
                .task {
                    // Config first: the auth store cannot reach Supabase until
                    // it knows where Supabase is.
                    await config.load()
                    await auth.restore()

                    // Screenshot builds only. Compiled out of Release entirely,
                    // and a no-op unless the environment carries an account.
                    #if DEBUG
                    if case .signedOut = auth.state, let account = Automation.credentials {
                        do {
                            try await auth.signIn(
                                identifier: account.identifier,
                                password: account.password
                            )
                        } catch {
                            // Say which step failed, never what was tried with.
                            print("Automated sign-in failed: \(error.localizedDescription)")
                        }
                    }
                    #endif
                }
        }
    }
}

struct RootView: View {
    @Environment(AppConfig.self) private var config
    @Environment(AuthStore.self) private var auth

    var body: some View {
        Group {
            if let failure = config.loadFailure {
                StartupFailureView(message: failure)
            } else {
                switch auth.state {
                case .loading:
                    ProgressView().controlSize(.large)
                case .signedOut:
                    SignInView()
                case .signedIn:
                    MainTabView()
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(TF.Colour.canvas)
    }
}

/// Boot failed before the app knew where its own backend was. Says what
/// happened and offers the one action that can help, rather than spinning.
struct StartupFailureView: View {
    let message: String
    @Environment(AppConfig.self) private var config

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "wifi.exclamationmark")
                .font(.system(size: 44))
                .foregroundStyle(TF.Colour.tertiaryLabel)
            Text("TrustFirst could not start")
                .font(TF.Typography.screenTitle)
                .foregroundStyle(TF.Colour.label)
            Text(message)
                .font(TF.Typography.rowBody)
                .foregroundStyle(TF.Colour.secondaryLabel)
                .multilineTextAlignment(.center)
            Button("Try again") {
                Task { await config.load() }
            }
            .buttonStyle(.glassProminent)
        }
        .padding(32)
    }
}
