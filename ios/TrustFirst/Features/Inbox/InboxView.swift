import SwiftUI

@MainActor
@Observable
final class InboxModel {
    enum Tab: Hashable { case notifications, chat }

    var tab: Tab = .notifications
    var notifications: [TFNotification] = []
    var conversations: [TFConversation] = []
    var isLoading = false
    var failure: String?

    private let database: Database
    private let userID: String

    init(database: Database, userID: String) {
        self.database = database
        self.userID = userID
    }

    func loadNotifications() async {
        isLoading = true
        defer { isLoading = false }
        do {
            // The actor is joined in the same request rather than fetched per
            // row — one round trip for the page instead of one per sender.
            notifications = try await database.fetch(
                Query("notifications")
                    .select("*, actor:actor_id(id,username,full_name,avatar_url,badge_tier,verified)")
                    .eq("user_id", userID)
                    .order("created_at")
                    .limit(50),
                as: TFNotification.self
            )
            failure = nil
        } catch {
            failure = error.localizedDescription
        }
    }

    /// Marks everything read locally first so the tap feels instant, then tells
    /// the server. If the server refuses, the rows go back to unread rather
    /// than leaving the screen quietly lying about the state.
    func markAllRead() async {
        let previous = notifications
        for index in notifications.indices { notifications[index].read = true }
        do {
            try await database.update(
                Query("notifications").eq("user_id", userID).eq("read", "false"),
                ["read": true]
            )
        } catch {
            notifications = previous
            failure = error.localizedDescription
        }
    }
}

struct InboxView: View {
    @Environment(Database.self) private var database
    @Environment(AuthStore.self) private var auth

    @State private var model: InboxModel?
    @State private var showingMenu = false
    @State private var showingCompose = false

    var body: some View {
        NavigationStack {
            Group {
                if let model {
                    content(model)
                } else {
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .background(TF.Colour.canvas)
            .navigationTitle("Inbox")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                // One button alone on the left, three sharing a capsule on the
                // right. On iOS 26 the toolbar supplies the glass for both
                // groups, and ToolbarSpacer is what keeps them separate rather
                // than letting all four merge into one long pill.
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                    } label: {
                        Image(systemName: "line.3.horizontal")
                    }
                    .accessibilityLabel("Menu")
                }
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button {
                        showingCompose = true
                    } label: {
                        Image(systemName: "plus")
                    }
                    .accessibilityLabel("New message")

                    Button {
                        Task { await model?.markAllRead() }
                    } label: {
                        Image(systemName: "envelope.badge.checkmark")
                    }
                    .accessibilityLabel("Mark all read")

                    Button {
                        showingMenu = true
                    } label: {
                        Image(systemName: "ellipsis")
                    }
                    .accessibilityLabel("More")
                }
            }
            .tfActionSheet(isPresented: $showingMenu, actions: [
                TFAction(title: "New message", systemImage: "square.and.pencil") {
                    showingMenu = false
                    showingCompose = true
                },
                TFAction(title: "Private message archive", systemImage: "archivebox") {
                    showingMenu = false
                },
                TFAction(title: "Edit notification settings", systemImage: "gearshape") {
                    showingMenu = false
                },
            ])
            .sheet(isPresented: $showingCompose) {
                NewChatView()
            }
        }
        .task {
            guard model == nil, case .signedIn(let userID) = auth.state else { return }
            let model = InboxModel(database: database, userID: userID)
            self.model = model
            await model.loadNotifications()
        }
    }

    @ViewBuilder
    private func content(_ model: InboxModel) -> some View {
        @Bindable var model = model
        VStack(spacing: 0) {
            TFSegmentedTabs(
                tabs: [(value: .notifications, title: "Notifications"), (value: .chat, title: "Chat")],
                selection: $model.tab
            )

            switch model.tab {
            case .notifications:
                NotificationList(model: model)
            case .chat:
                ChatEmptyState()
            }
        }
        .overlay(alignment: .bottomTrailing) {
            // Only the chat side has a compose action, so the button is only
            // there — a button that does nothing on one tab is worse than none.
            if model.tab == .chat {
                TFFloatingActionButton(
                    systemImage: "square.and.pencil",
                    accessibilityLabel: "New chat"
                ) { showingCompose = true }
                .padding(.bottom, TF.Metric.floatingInset)
            }
        }
    }
}

private struct NotificationList: View {
    let model: InboxModel

    var body: some View {
        if model.isLoading && model.notifications.isEmpty {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let failure = model.failure, model.notifications.isEmpty {
            EmptyState(
                systemImage: "exclamationmark.triangle",
                title: "Could not load your notifications",
                message: failure
            )
        } else if model.notifications.isEmpty {
            EmptyState(
                systemImage: "bell",
                title: "Nothing yet",
                message: "When someone replies to you or follows you, it shows up here."
            )
        } else {
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(model.notifications) { notification in
                        NotificationRow(notification: notification)
                    }
                }
            }
            .refreshable { await model.loadNotifications() }
        }
    }
}

private struct NotificationRow: View {
    let notification: TFNotification

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            TFAvatar(url: notification.actor?.avatarURL, fallback: notification.actor?.displayName)

            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(TF.Type.rowTitle)
                    .foregroundStyle(TF.Colour.label)
                    .fixedSize(horizontal: false, vertical: true)

                if let preview = notification.previewText, !preview.isEmpty {
                    Text(preview)
                        .font(TF.Type.rowBody)
                        .foregroundStyle(TF.Colour.secondaryLabel)
                        .lineLimit(2)
                }

                if let created = notification.createdAt {
                    Text(created.tfShortRelative)
                        .font(TF.Type.caption)
                        .foregroundStyle(TF.Colour.tertiaryLabel)
                        .padding(.top, 2)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, TF.Metric.gutter)
        .padding(.vertical, TF.Metric.rowSpacing)
        // Unread is a wash across the whole row rather than a dot, which scans
        // faster down a long list.
        .background(notification.isUnread ? TF.Colour.unread : TF.Colour.surface)
        .contentShape(.rect)
    }

    private var title: String {
        let who = notification.actor?.handle.isEmpty == false
            ? notification.actor!.handle
            : (notification.actor?.displayName ?? "Someone")
        return switch notification.type {
        case "follow":   "\(who) started following you"
        case "like":     "\(who) liked your post"
        case "comment":  "\(who) replied to your post"
        case "mention":  "\(who) mentioned you"
        case "repost":   "\(who) reposted you"
        case "system":   "TrustFirst"
        default:         "\(who) sent you something"
        }
    }
}

private struct ChatEmptyState: View {
    var body: some View {
        EmptyState(
            systemImage: "bubble.left.and.bubble.right",
            title: "Welcome to chat",
            message: "Messages you send and receive appear here. They are end-to-end encrypted."
        )
    }
}

struct EmptyState: View {
    let systemImage: String
    let title: String
    let message: String

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: systemImage)
                .font(.system(size: 40, weight: .light))
                .foregroundStyle(TF.Colour.tertiaryLabel)
            Text(title)
                .font(TF.Type.screenTitle)
                .foregroundStyle(TF.Colour.label)
            Text(message)
                .font(TF.Type.rowBody)
                .foregroundStyle(TF.Colour.secondaryLabel)
                .multilineTextAlignment(.center)
        }
        .padding(.horizontal, 40)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
