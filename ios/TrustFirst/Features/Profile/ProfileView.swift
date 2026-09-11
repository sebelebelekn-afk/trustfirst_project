import SwiftUI

@MainActor
@Observable
final class ProfileModel {
    enum Tab: Hashable { case posts, replies, saved, about }

    var tab: Tab = .posts
    var user: TFUser?
    var posts: [TFPost] = []
    var saved: [TFPost] = []
    var isLoading = true
    var failure: String?

    private let database: Database
    private let userID: String
    private var loadedTabs: Set<Tab> = []

    init(database: Database, userID: String) {
        self.database = database
        self.userID = userID
    }

    func loadProfile() async {
        isLoading = true
        defer { isLoading = false }
        do {
            user = try await database.first(
                Query("users")
                    .select("id,username,full_name,avatar_url,bio,badge_tier,verified,account_type,follower_count,following_count")
                    .eq("id", userID),
                as: TFUser.self
            )
            failure = nil
        } catch {
            failure = error.localizedDescription
        }
        await load(.posts)
    }

    /// Each tab fetches once and is then kept. Switching back and forth should
    /// not re-hit the database for rows that have not changed.
    func load(_ tab: Tab) async {
        guard !loadedTabs.contains(tab) else { return }
        do {
            switch tab {
            case .posts:
                posts = try await database.fetch(
                    Query("posts")
                        .select("""
                            *,\
                            users:user_id(id,username,full_name,avatar_url,badge_tier,verified,ai_label),\
                            groups:group_id(id,name,emoji,color,privacy,member_count)
                            """)
                        .eq("user_id", userID)
                        .order("created_at")
                        .limit(30),
                    as: TFPost.self
                )
            case .saved:
                let rows = try await database.fetch(
                    Query("bookmarks")
                        .select("""
                            post_id,\
                            posts:post_id(*,\
                            users:user_id(id,username,full_name,avatar_url,badge_tier,verified,ai_label),\
                            groups:group_id(id,name,emoji,color,privacy,member_count))
                            """)
                        .eq("user_id", userID)
                        .order("created_at")
                        .limit(30),
                    as: BookmarkRow.self
                )
                saved = rows.compactMap(\.posts)
            case .replies, .about:
                break
            }
            loadedTabs.insert(tab)
            failure = nil
        } catch {
            failure = error.localizedDescription
        }
    }

    private struct BookmarkRow: Decodable, Sendable {
        let posts: TFPost?
    }
}

struct ProfileView: View {
    @Environment(Database.self) private var database
    @Environment(AuthStore.self) private var auth

    @State private var model: ProfileModel?
    @State private var showingAccount = false

    var body: some View {
        NavigationStack {
            Group {
                if let model {
                    content(model)
                } else {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .background(TF.Colour.canvas)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button {
                    } label: {
                        Image(systemName: "square.and.arrow.up")
                    }
                    .accessibilityLabel("Share profile")

                    Button {
                        showingAccount = true
                    } label: {
                        Image(systemName: "line.3.horizontal")
                    }
                    .accessibilityLabel("Account")
                }
            }
            .sheet(isPresented: $showingAccount) {
                AccountSheet { showingAccount = false }
            }
        }
        .task {
            guard model == nil, case .signedIn(let userID) = auth.state else { return }
            let model = ProfileModel(database: database, userID: userID)
            self.model = model
            await model.loadProfile()
        }
    }

    @ViewBuilder
    private func content(_ model: ProfileModel) -> some View {
        @Bindable var model = model
        ScrollView {
            LazyVStack(spacing: 0, pinnedViews: [.sectionHeaders]) {
                Section {
                    tabContent(model)
                } header: {
                    VStack(spacing: 0) {
                        hero(model)
                        TFSegmentedTabs(
                            tabs: [
                                (value: .posts, title: "Posts"),
                                (value: .replies, title: "Replies"),
                                (value: .saved, title: "Saved"),
                                (value: .about, title: "About"),
                            ],
                            selection: $model.tab
                        )
                        .background(TF.Colour.canvas)
                    }
                }
            }
        }
        .refreshable { await model.loadProfile() }
        .onChange(of: model.tab) { _, tab in
            Task { await model.load(tab) }
        }
    }

    private func hero(_ model: ProfileModel) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            TFAvatar(url: model.user?.avatarURL, fallback: model.user?.displayName, size: 88)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(model.user?.displayName ?? "You")
                        .font(.system(size: 26, weight: .bold))
                        .foregroundStyle(TF.Colour.label)
                    if let badge = model.user?.badge { TFBadge(badge: badge, size: 17) }
                }
                if let handle = model.user?.handle, !handle.isEmpty {
                    Text(handle)
                        .font(TF.Typography.rowBody)
                        .foregroundStyle(TF.Colour.secondaryLabel)
                }
            }

            if let bio = model.user?.bio, !bio.isEmpty {
                Text(bio)
                    .font(TF.Typography.rowBody)
                    .foregroundStyle(TF.Colour.label)
                    .fixedSize(horizontal: false, vertical: true)
            }

            // Reddit's karma and achievements have no column in this database,
            // so the stats are the ones that actually exist.
            HStack(spacing: 0) {
                stat(model.posts.count.tfCompact, "Posts")
                divider
                stat((model.user?.followerCount ?? 0).tfCompact, "Followers")
                divider
                stat((model.user?.followingCount ?? 0).tfCompact, "Following")
            }
            .padding(.top, 4)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(TF.Metric.gutter)
        .background(TF.Colour.canvas)
    }

    private var divider: some View {
        Rectangle()
            .fill(TF.Colour.hairline)
            .frame(width: 0.5, height: 30)
    }

    private func stat(_ value: String, _ label: String) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(TF.Colour.label)
            Text(label)
                .font(TF.Typography.caption)
                .foregroundStyle(TF.Colour.secondaryLabel)
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private func tabContent(_ model: ProfileModel) -> some View {
        switch model.tab {
        case .posts:
            postList(model.posts, empty: "You have not posted yet.")
        case .saved:
            postList(model.saved, empty: "Nothing saved yet.")
        case .replies:
            placeholder("Your replies will appear here.")
        case .about:
            placeholder("About you.")
        }
    }

    @ViewBuilder
    private func postList(_ posts: [TFPost], empty: String) -> some View {
        if posts.isEmpty {
            placeholder(empty)
        } else {
            ForEach(posts) { post in
                PostRow(post: post)
                Rectangle().fill(TF.Colour.hairline).frame(height: 0.5)
            }
        }
    }

    private func placeholder(_ text: String) -> some View {
        Text(text)
            .font(TF.Typography.rowBody)
            .foregroundStyle(TF.Colour.secondaryLabel)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 60)
    }
}

/// The ☰ sheet on the profile.
struct AccountSheet: View {
    var onClose: () -> Void

    @Environment(AuthStore.self) private var auth

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Your account")
                    .font(.system(size: 22, weight: .bold))
                    .foregroundStyle(TF.Colour.label)
                Spacer()
                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(TF.Colour.label)
                        .frame(width: 34, height: 34)
                        .background(TF.Colour.recessed, in: .circle)
                }
                .accessibilityLabel("Close")
            }
            .padding(.horizontal, 22)
            .padding(.top, 22)
            .padding(.bottom, 10)

            ForEach(Self.items, id: \.title) { item in
                Button {
                } label: {
                    HStack(spacing: 18) {
                        Image(systemName: item.symbol)
                            .font(.system(size: 19))
                            .frame(width: 26)
                        Text(item.title).font(TF.Typography.rowBody)
                        Spacer(minLength: 0)
                    }
                    .foregroundStyle(TF.Colour.label)
                    .padding(.horizontal, 22)
                    .frame(height: 56)
                    .contentShape(.rect)
                }
                .buttonStyle(.plain)
            }

            Button {
                onClose()
                Task { await auth.signOut() }
            } label: {
                HStack(spacing: 18) {
                    Image(systemName: "rectangle.portrait.and.arrow.right")
                        .font(.system(size: 19))
                        .frame(width: 26)
                    Text("Sign out").font(TF.Typography.rowBody)
                    Spacer(minLength: 0)
                }
                .foregroundStyle(TF.Colour.destructive)
                .padding(.horizontal, 22)
                .frame(height: 56)
                .contentShape(.rect)
            }
            .buttonStyle(.plain)

            Spacer(minLength: 0)
        }
        .presentationDetents([.height(430)])
    }

    private static let items: [(title: String, symbol: String)] = [
        ("Settings", "gearshape"),
        ("Edit profile", "pencil"),
        ("Saved", "bookmark"),
        ("Your groups", "person.3"),
        ("Wallet", "creditcard"),
    ]
}
