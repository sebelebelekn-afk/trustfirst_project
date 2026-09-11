import SwiftUI

/// Starting a chat: search a username, pick people, create. Create stays
/// disabled until at least one person is picked, so the button never promises
/// something it cannot do.
struct NewChatView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(Database.self) private var database
    @Environment(AuthStore.self) private var auth

    @State private var term = ""
    @State private var results: [TFUser] = []
    @State private var selected: [TFUser] = []
    @State private var isSearching = false
    @State private var searchTask: Task<Void, Never>?

    /// Below this the result set is everybody, which is neither useful nor
    /// cheap — hence the "at least 3 characters" hint rather than a spinner.
    private let minimumTerm = 3

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            header

            Text("Search for people by username to chat with them.")
                .font(TF.Type.rowBody)
                .foregroundStyle(TF.Colour.secondaryLabel)

            TFSearchField(placeholder: "Search for a username", text: $term)
                .onChange(of: term) { _, newValue in scheduleSearch(newValue) }

            if !selected.isEmpty {
                selectedRow
            }

            if term.count < minimumTerm {
                Text("Type at least \(minimumTerm) characters to search for a username.")
                    .font(TF.Type.rowBody)
                    .foregroundStyle(TF.Colour.secondaryLabel)
            } else if isSearching {
                HStack { ProgressView(); Spacer() }
            } else if results.isEmpty {
                Text("Nobody by that name.")
                    .font(TF.Type.rowBody)
                    .foregroundStyle(TF.Colour.secondaryLabel)
            } else {
                resultsList
            }

            Spacer(minLength: 0)
        }
        .padding(.horizontal, TF.Metric.gutter)
        .padding(.top, TF.Metric.gutter)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(TF.Colour.canvas)
    }

    private var header: some View {
        HStack {
            TFGlassIconButton(systemImage: "xmark", accessibilityLabel: "Close") {
                dismiss()
            }
            Spacer()
            Button("Create") {
                // Creating the conversation is the next piece of work; the
                // people are already chosen and validated by this point.
            }
            .font(.system(size: 17, weight: .medium))
            .foregroundStyle(selected.isEmpty ? TF.Colour.tertiaryLabel : TF.Colour.label)
            .padding(.horizontal, 22)
            .frame(height: TF.Metric.toolbarButton)
            .glassEffect(.regular, in: .capsule)
            .disabled(selected.isEmpty)
        }
    }

    private var selectedRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(selected) { user in
                    Button {
                        selected.removeAll { $0.id == user.id }
                    } label: {
                        HStack(spacing: 6) {
                            TFAvatar(url: user.avatarURL, fallback: user.displayName, size: 22)
                            Text(user.handle).font(TF.Type.caption)
                            Image(systemName: "xmark").font(.system(size: 10, weight: .bold))
                        }
                        .foregroundStyle(TF.Colour.label)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 7)
                    }
                    .glassEffect(.regular.interactive(), in: .capsule)
                    .accessibilityLabel("Remove \(user.handle)")
                }
            }
        }
    }

    private var resultsList: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(results) { user in
                    Button {
                        if !selected.contains(where: { $0.id == user.id }) {
                            selected.append(user)
                        }
                        term = ""
                        results = []
                    } label: {
                        HStack(spacing: 12) {
                            TFAvatar(url: user.avatarURL, fallback: user.displayName)
                            VStack(alignment: .leading, spacing: 2) {
                                HStack(spacing: 4) {
                                    Text(user.displayName)
                                        .font(TF.Type.rowTitle)
                                        .foregroundStyle(TF.Colour.label)
                                    if let badge = user.badge { TFBadge(badge: badge) }
                                }
                                Text(user.handle)
                                    .font(TF.Type.caption)
                                    .foregroundStyle(TF.Colour.secondaryLabel)
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(.vertical, 10)
                        .contentShape(.rect)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    /// Debounced, and the previous search is cancelled rather than left to
    /// land after a newer one — otherwise typing fast shows stale results.
    private func scheduleSearch(_ value: String) {
        searchTask?.cancel()
        guard value.count >= minimumTerm else {
            results = []
            isSearching = false
            return
        }
        isSearching = true
        searchTask = Task {
            try? await Task.sleep(for: .milliseconds(280))
            guard !Task.isCancelled else { return }
            await search(value)
        }
    }

    private func search(_ value: String) async {
        let term = value.trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .trimmingCharacters(in: CharacterSet(charactersIn: "@"))
        guard case .signedIn(let me) = auth.state else { return }
        do {
            results = try await database.fetch(
                Query("users")
                    .select("id,username,full_name,avatar_url,badge_tier,verified")
                    .ilike("username", contains: term)
                    .neq("id", me)
                    .limit(20),
                as: TFUser.self
            )
        } catch {
            results = []
        }
        isSearching = false
    }
}
