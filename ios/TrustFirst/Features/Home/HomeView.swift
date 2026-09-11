import SwiftUI

@MainActor
@Observable
final class FeedModel {
    var posts: [TFPost] = []
    var isLoading = false
    var isLoadingMore = false
    var reachedEnd = false
    var failure: String?

    private let database: Database
    private let pageSize = 20

    init(database: Database) {
        self.database = database
    }

    /// The home feed is the posts in the groups you belong to. With no groups
    /// there is no feed — which is a state to say out loud, not an empty list.
    func load(groupIDs: [String]) async {
        guard !groupIDs.isEmpty else {
            posts = []
            reachedEnd = true
            return
        }
        isLoading = true
        defer { isLoading = false }
        do {
            posts = try await page(groupIDs: groupIDs, from: 0)
            reachedEnd = posts.count < pageSize
            failure = nil
        } catch {
            failure = error.localizedDescription
        }
    }

    func loadMore(groupIDs: [String]) async {
        guard !isLoadingMore, !reachedEnd, !groupIDs.isEmpty else { return }
        isLoadingMore = true
        defer { isLoadingMore = false }
        do {
            let next = try await page(groupIDs: groupIDs, from: posts.count)
            // Ids already held are dropped: a post inserted while paging would
            // otherwise shift every row down and arrive twice.
            let known = Set(posts.map(\.id))
            posts.append(contentsOf: next.filter { !known.contains($0.id) })
            reachedEnd = next.count < pageSize
        } catch {
            failure = error.localizedDescription
        }
    }

    private func page(groupIDs: [String], from offset: Int) async throws -> [TFPost] {
        try await database.fetch(
            Query("posts")
                .select("""
                    *,\
                    users:user_id(id,username,full_name,avatar_url,badge_tier,verified,ai_label),\
                    groups:group_id(id,name,emoji,color,privacy,member_count)
                    """)
                .in("group_id", groupIDs)
                .order("created_at")
                .range(from: offset, to: offset + pageSize - 1),
            as: TFPost.self
        )
    }
}

struct HomeView: View {
    @Environment(Database.self) private var database
    @Environment(AuthStore.self) private var auth

    @State private var feed: FeedModel?
    @State private var groups: GroupsStore?
    @State private var drawerOpen = false
    @State private var openedGroup: TFGroup?
    @State private var composing = false

    var body: some View {
        TFDrawer(isOpen: $drawerOpen) {
            if let groups {
                GroupsPanel(
                    store: groups,
                    onSelect: { group in
                        drawerOpen = false
                        openedGroup = group
                    },
                    onClose: { drawerOpen = false }
                )
            }
        } content: {
            NavigationStack {
                feedBody
                    .background(TF.Colour.canvas)
                    .navigationTitle("Home")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .topBarLeading) {
                            Button {
                                withAnimation(TF.Motion.morph) { drawerOpen = true }
                            } label: {
                                Image(systemName: "line.3.horizontal")
                            }
                            .accessibilityLabel("Your groups")
                        }
                        ToolbarItemGroup(placement: .topBarTrailing) {
                            Button {
                            } label: {
                                Image(systemName: "magnifyingglass")
                            }
                            .accessibilityLabel("Search")

                            Button {
                                composing = true
                            } label: {
                                Image(systemName: "square.and.pencil")
                            }
                            .accessibilityLabel("New post")
                        }
                    }
                    .navigationDestination(item: $openedGroup) { group in
                        GroupView(group: group)
                    }
                    .sheet(isPresented: $composing) {
                        if let groups {
                            NewPostView(groupsStore: groups) {
                                // A new post should be visible the moment the
                                // composer closes, not on the next pull.
                                Task { await feed?.load(groupIDs: groups.groupIDs) }
                            }
                        }
                    }
            }
        }
        .task {
            guard feed == nil, case .signedIn(let userID) = auth.state else { return }
            let groupsStore = GroupsStore(database: database, userID: userID)
            let feedModel = FeedModel(database: database)
            groups = groupsStore
            feed = feedModel
            await groupsStore.loadIfNeeded()
            await feedModel.load(groupIDs: groupsStore.groupIDs)
        }
    }

    @ViewBuilder
    private var feedBody: some View {
        if let feed, let groups {
            if feed.isLoading && feed.posts.isEmpty {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let failure = feed.failure, feed.posts.isEmpty {
                EmptyState(
                    systemImage: "exclamationmark.triangle",
                    title: "Could not load your feed",
                    message: failure
                )
            } else if groups.groups.isEmpty {
                EmptyState(
                    systemImage: "person.3",
                    title: "No groups yet",
                    message: "Your home feed is the posts from groups you are in. Join one to fill it."
                )
            } else if feed.posts.isEmpty {
                EmptyState(
                    systemImage: "text.bubble",
                    title: "Nothing posted yet",
                    message: "Nobody in your groups has posted. Be the first."
                )
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(feed.posts) { post in
                            PostRow(post: post) { group in
                                openedGroup = group
                            }
                            .onAppear {
                                // Paging starts three rows from the bottom, so
                                // the next page is usually already there.
                                if post.id == feed.posts.suffix(3).first?.id {
                                    Task { await feed.loadMore(groupIDs: groups.groupIDs) }
                                }
                            }
                            Rectangle()
                                .fill(TF.Colour.hairline)
                                .frame(height: 0.5)
                        }
                        if feed.isLoadingMore {
                            ProgressView().padding(.vertical, 20)
                        }
                    }
                }
                .refreshable {
                    await groups.load()
                    await feed.load(groupIDs: groups.groupIDs)
                }
            }
        } else {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}
