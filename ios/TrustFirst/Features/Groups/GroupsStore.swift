import Foundation

/// The groups this person belongs to. Loaded once and shared: the drawer lists
/// them, the home feed is built from them, and the composer needs them to ask
/// where a post is going. Three screens fetching the same rows separately is
/// three chances for them to disagree.
@MainActor
@Observable
final class GroupsStore {
    private(set) var groups: [TFGroup] = []
    private(set) var adminGroupIDs: Set<String> = []
    private(set) var isLoading = false
    private(set) var failure: String?

    private let database: Database
    private let userID: String
    private var hasLoaded = false

    init(database: Database, userID: String) {
        self.database = database
        self.userID = userID
    }

    /// Ids of the groups whose posts make up the home feed.
    var groupIDs: [String] { groups.map(\.id) }

    func loadIfNeeded() async {
        guard !hasLoaded else { return }
        await load()
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            // The group is joined into the membership row, so this is one
            // request rather than a list of ids followed by a second fetch.
            let memberships = try await database.fetch(
                Query("group_members")
                    .select("id,group_id,user_id,role,joined_at,groups(*)")
                    .eq("user_id", userID)
                    .order("joined_at"),
                as: TFGroupMember.self
            )
            groups = memberships
                .compactMap(\.groups)
                // A group can be archived without the membership row being
                // removed; those should not appear anywhere.
                .filter { $0.isActive != false }
                .sorted { $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending }
            adminGroupIDs = Set(memberships.filter(\.isAdmin).compactMap(\.groupId))
            failure = nil
            hasLoaded = true
        } catch {
            failure = error.localizedDescription
        }
    }

    func isAdmin(of group: TFGroup) -> Bool { adminGroupIDs.contains(group.id) }
}
