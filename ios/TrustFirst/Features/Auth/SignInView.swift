import SwiftUI

/// Sign in by username or email. Username goes through Django because
/// resolving it to an email needs the service key; email goes straight to
/// Supabase. Which one someone typed is worked out from the text rather than
/// asked, because nobody should have to tell an app what a username looks like.
struct SignInView: View {
    @Environment(AuthStore.self) private var auth

    @State private var identifier = ""
    @State private var password = ""
    @State private var isWorking = false
    @State private var failure: String?
    @FocusState private var focus: Field?

    private enum Field { case identifier, password }

    var body: some View {
        VStack(spacing: 18) {
            Spacer(minLength: 0)

            VStack(spacing: 6) {
                Text("TrustFirst")
                    .font(.system(size: 30, weight: .bold))
                    .foregroundStyle(TF.Colour.label)
                Text("Sign in to pick up where you left off.")
                    .font(TF.Typography.rowBody)
                    .foregroundStyle(TF.Colour.secondaryLabel)
            }
            .padding(.bottom, 10)

            // Plain fields with the shared style, rather than TFSearchField:
            // .focused() has to land on the real TextField, and it cannot reach
            // one nested inside a composite view.
            TextField("Username or email", text: $identifier)
                .tfFieldStyle()
                .textContentType(.username)
                .keyboardType(.emailAddress)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .focused($focus, equals: .identifier)
                .submitLabel(.next)
                .onSubmit { focus = .password }

            SecureField("Password", text: $password)
                .tfFieldStyle()
                .textContentType(.password)
                .focused($focus, equals: .password)
                .submitLabel(.go)
                .onSubmit(submit)

            if let failure {
                Text(failure)
                    .font(TF.Typography.caption)
                    .foregroundStyle(TF.Colour.destructive)
                    .multilineTextAlignment(.center)
                    .transition(.opacity)
            }

            Button(action: submit) {
                Group {
                    if isWorking {
                        ProgressView().tint(.white)
                    } else {
                        Text("Sign in").font(.system(size: 17, weight: .semibold))
                    }
                }
                .frame(maxWidth: .infinity)
                .frame(height: TF.Metric.fieldHeight)
            }
            .buttonStyle(.glassProminent)
            .disabled(!canSubmit)

            Spacer(minLength: 0)
        }
        .padding(.horizontal, 28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(TF.Colour.canvas)
    }

    private var canSubmit: Bool {
        !isWorking && identifier.count >= 3 && password.count >= 6
    }

    private func submit() {
        guard canSubmit else { return }
        focus = nil
        isWorking = true
        withAnimation(TF.Motion.settle) { failure = nil }

        Task {
            do {
                try await auth.signIn(identifier: identifier, password: password)
            } catch {
                withAnimation(TF.Motion.settle) { failure = error.localizedDescription }
            }
            isWorking = false
        }
    }
}
