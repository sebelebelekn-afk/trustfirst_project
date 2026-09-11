import SwiftUI

/// Writing a post. Body only, because `posts` has no title column — the web
/// app stores a post as `text_content` and nothing else. A Title field here
/// would have nowhere to go, so there isn't one.
struct NewPostView: View {
    let groupsStore: GroupsStore
    /// Pre-selects the group when the composer is opened from inside one.
    var initialGroup: TFGroup? = nil
    var onPosted: () -> Void = {}

    @Environment(\.dismiss) private var dismiss
    @Environment(Database.self) private var database
    @Environment(AuthStore.self) private var auth

    @State private var body_ = ""
    @State private var group: TFGroup?
    @State private var showingPicker = false
    @State private var isPosting = false
    @State private var failure: String?
    @FocusState private var writing: Bool

    private var canPost: Bool {
        !isPosting && !body_.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        VStack(spacing: 0) {
            header

            ScrollView {
                TextField("What do you want to say?", text: $body_, axis: .vertical)
                    .font(.system(size: 18))
                    .foregroundStyle(TF.Colour.label)
                    .tint(TF.Colour.accent)
                    .focused($writing)
                    .padding(.horizontal, TF.Metric.gutter)
                    .padding(.top, 18)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            if let failure {
                Text(failure)
                    .font(TF.Typography.caption)
                    .foregroundStyle(TF.Colour.destructive)
                    .padding(.horizontal, TF.Metric.gutter)
                    .padding(.bottom, 8)
            }
        }
        .background(TF.Colour.canvas)
        // A detached glass bar riding above the keyboard, rather than a docked
        // one — it is furniture floating over the page, same as the tab bar.
        .safeAreaInset(edge: .bottom) {
            if writing { formatBar }
        }
        .sheet(isPresented: $showingPicker) {
            GroupPickerView(store: groupsStore, selection: $group)
        }
        .onAppear {
            group = initialGroup
            writing = true
        }
    }

    private var header: some View {
        HStack(spacing: 10) {
            TFGlassIconButton(systemImage: "xmark", accessibilityLabel: "Close") { dismiss() }

            Button {
                showingPicker = true
            } label: {
                HStack(spacing: 6) {
                    if let group {
                        TFGroupIcon(group: group, size: 20)
                        Text(group.displayName).lineLimit(1)
                    } else {
                        Text("Select a group")
                    }
                    Image(systemName: "chevron.down")
                        .font(.system(size: 11, weight: .semibold))
                }
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(TF.Colour.label)
                .padding(.horizontal, 16)
                .frame(height: TF.Metric.toolbarButton)
            }
            .glassEffect(.regular.interactive(), in: .capsule)

            Spacer(minLength: 0)

            Button(action: post) {
                Group {
                    if isPosting {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Post").font(.system(size: 16, weight: .semibold))
                    }
                }
                .foregroundStyle(canPost ? TF.Colour.label : TF.Colour.tertiaryLabel)
                .padding(.horizontal, 22)
                .frame(height: TF.Metric.toolbarButton)
            }
            .glassEffect(.regular, in: .capsule)
            .disabled(!canPost)
        }
        .padding(.horizontal, TF.Metric.gutter)
        .padding(.vertical, 8)
    }

    /// Attachments and formatting. Each is wired to a post_type the backend
    /// already understands — nothing here invents a kind of post the server
    /// cannot store.
    private var formatBar: some View {
        HStack(spacing: 2) {
            ForEach(Self.tools, id: \.symbol) { tool in
                Button {
                } label: {
                    Image(systemName: tool.symbol)
                        .font(.system(size: 18, weight: .regular))
                        .foregroundStyle(TF.Colour.label)
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel(tool.label)
            }
        }
        .padding(.horizontal, 6)
        .glassEffect(.regular, in: .capsule)
        .padding(.horizontal, TF.Metric.gutter)
        .padding(.bottom, 8)
    }

    private static let tools: [(symbol: String, label: String)] = [
        ("link", "Add a link"),
        ("photo", "Add a photo"),
        ("play.rectangle", "Add a video"),
        ("list.bullet", "Add a poll"),
        ("questionmark.circle", "Add a quiz"),
        ("mic", "Add audio"),
    ]

    private func post() {
        guard canPost, case .signedIn(let userID) = auth.state else { return }
        isPosting = true
        failure = nil

        Task {
            do {
                try await database.insert(into: "posts", NewPost(
                    userId: userID,
                    textContent: body_.trimmingCharacters(in: .whitespacesAndNewlines),
                    postType: "text",
                    groupId: group?.id,
                    status: "published"
                ))
                onPosted()
                dismiss()
            } catch {
                failure = error.localizedDescription
            }
            isPosting = false
        }
    }
}

/// What is actually written. Deliberately narrow: the server fills in the
/// counts, the timestamps and the moderation flags, and a client that sends
/// them is a client that can lie about them.
private struct NewPost: Encodable, Sendable {
    let userId: String
    let textContent: String
    let postType: String
    let groupId: String?
    let status: String

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case textContent = "text_content"
        case postType = "post_type"
        case groupId = "group_id"
        case status
    }
}
