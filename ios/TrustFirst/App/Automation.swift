import Foundation

/// How the screenshot build gets past the sign-in screen.
///
/// Every part of this is compiled out of Release. `#if DEBUG` wraps the whole
/// file, so there is no code path in a shipping binary that reads a password
/// out of the environment, and nothing here can be reached by anyone holding
/// the App Store build.
///
/// The credentials arrive as environment variables, never as launch arguments.
/// Arguments are visible in `ps`, in crash reports and in anything that echoes
/// argv — a password in argv is a password in the build log. simctl forwards
/// SIMCTL_CHILD_-prefixed variables into the app's environment instead, which
/// keeps them out of all of those.
///
/// Nothing is ever compiled in. With the variables unset — which is every
/// normal build — this returns nil and the app behaves exactly as it would
/// have.
#if DEBUG
enum Automation {

    /// The account the screenshot run signs in as, if one was provided.
    static var credentials: (identifier: String, password: String)? {
        let environment = ProcessInfo.processInfo.environment
        guard let identifier = environment["TF_TEST_USERNAME"]?.trimmingCharacters(in: .whitespaces),
              let password = environment["TF_TEST_PASSWORD"],
              !identifier.isEmpty, !password.isEmpty
        else { return nil }
        return (identifier, password)
    }

    /// Which tab to open on. The screenshot run relaunches the app once per
    /// tab rather than trying to drive taps, because simctl cannot tap and a
    /// UI test to press three buttons is a great deal of machinery for three
    /// buttons.
    static var startTab: AppTab? {
        switch ProcessInfo.processInfo.environment["TF_START_TAB"]?.lowercased() {
        case "home":  return .home
        case "inbox": return .inbox
        case "you":   return .you
        default:      return nil
        }
    }

    /// True when this launch is a screenshot run, whatever it was given.
    static var isActive: Bool {
        credentials != nil || startTab != nil
    }
}
#endif
