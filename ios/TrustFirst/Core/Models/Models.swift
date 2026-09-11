import Foundation

// Rows as the database actually stores them. Two rules throughout:
//
//   1. Only `id` is non-optional. Every other column is optional, because a
//      column added or renamed on the server must never make the app fail to
//      decode a whole page of rows. A missing field degrades one label; a
//      failed decode degrades the entire screen.
//   2. CodingKeys spell the snake_case column names explicitly rather than
//      relying on a global key strategy, so renaming a Swift property can
//      never silently stop reading a column.

// MARK: - User

struct TFUser: Codable, Identifiable, Hashable, Sendable {
    let id: String
    var username: String?
    var fullName: String?
    var avatarURL: String?
    var bio: String?
    var badgeTier: String?
    var verified: Bool?
    var aiLabel: Bool?
    var accountType: String?
    var followerCount: Int?
    var followingCount: Int?

    enum CodingKeys: String, CodingKey {
        case id, username, bio, verified
        case fullName = "full_name"
        case avatarURL = "avatar_url"
        case badgeTier = "badge_tier"
        case aiLabel = "ai_label"
        case accountType = "account_type"
        case followerCount = "follower_count"
        case followingCount = "following_count"
    }

    /// What to show when there is no display name yet.
    var displayName: String { fullName ?? username.map { "@\($0)" } ?? "Someone" }
    var handle: String { username.map { "@\($0)" } ?? "" }

    /// The three tiers the web app already awards. Nothing here grants a badge
    /// — it only reads one the server set.
    enum Badge: String {
        case verified = "blue"
        case creator = "white"
        case golden = "golden"
    }

    var badge: Badge? {
        if let tier = badgeTier, let badge = Badge(rawValue: tier) { return badge }
        return verified == true ? .verified : nil
    }
}

// MARK: - Post

struct TFPost: Codable, Identifiable, Hashable, Sendable {
    let id: String
    var userId: String?
    var textContent: String?
    var mediaURL: String?
    var mediaType: String?
    var thumbnailURL: String?
    var postType: String?
    var likeCount: Int?
    var commentCount: Int?
    var repostCount: Int?
    var shareCount: Int?
    var viewCount: Int?
    var isPinned: Bool?
    var quotedPostId: String?
    var createdAt: Date?
    var users: TFUser?
    /// Null when the post is on the open feed rather than inside a group.
    var groupId: String?
    /// Present when the post is fetched with its group joined in.
    var groups: TFGroup?

    enum CodingKeys: String, CodingKey {
        case id, users, groups
        case userId = "user_id"
        case textContent = "text_content"
        case mediaURL = "media_url"
        case mediaType = "media_type"
        case thumbnailURL = "thumbnail_url"
        case postType = "post_type"
        case likeCount = "like_count"
        case commentCount = "comment_count"
        case repostCount = "repost_count"
        case shareCount = "share_count"
        case viewCount = "view_count"
        case isPinned = "is_pinned"
        case quotedPostId = "quoted_post_id"
        case createdAt = "created_at"
        case groupId = "group_id"
    }

    /// The nine kinds of thing a post can be, carried over from the web app.
    enum Kind: String {
        case video, text, quote, poll, quiz, thought, question, audio, trustclip
    }

    var kind: Kind { postType.flatMap(Kind.init) ?? .text }
}

// MARK: - Notification

struct TFNotification: Codable, Identifiable, Hashable, Sendable {
    let id: String
    var userId: String?
    var actorId: String?
    /// Some writers on the server spell the actor `from_user_id` instead.
    /// Read both; `actor` resolves to whichever is set.
    var fromUserId: String?
    var type: String?
    /// The server renders the headline itself. Preferred over anything this
    /// app could reconstruct, because it knows the context — which post, which
    /// group — that the notification row does not carry.
    var message: String?
    var previewText: String?
    var read: Bool?
    var createdAt: Date?
    var actor: TFUser?

    enum CodingKeys: String, CodingKey {
        case id, type, read, actor, message
        case userId = "user_id"
        case actorId = "actor_id"
        case fromUserId = "from_user_id"
        case previewText = "preview_text"
        case createdAt = "created_at"
    }

    var isUnread: Bool { read != true }
    var actorID: String? { actorId ?? fromUserId }
}

// MARK: - Conversation

struct TFConversation: Codable, Identifiable, Hashable, Sendable {
    let id: String
    var type: String?
    var name: String?
    var avatarURL: String?
    var createdBy: String?
    var isLocked: Bool?
    var disappearingSeconds: Int?
    var updatedAt: Date?

    enum CodingKeys: String, CodingKey {
        case id, type, name
        case avatarURL = "avatar_url"
        case createdBy = "created_by"
        case isLocked = "is_locked"
        case disappearingSeconds = "disappearing_seconds"
        case updatedAt = "updated_at"
    }

    var isGroup: Bool { type == "group" }
}

// MARK: - Message

struct TFMessage: Codable, Identifiable, Hashable, Sendable {
    let id: String
    var conversationId: String?
    var senderId: String?
    var content: String?
    /// Set instead of `content` when the conversation is end-to-end encrypted.
    /// The app decrypts locally; the server never sees the plaintext.
    var ciphertext: String?
    var nonce: String?
    var mediaURL: String?
    var messageType: String?
    var replyToId: String?
    var voiceDurationSeconds: Double?
    var createdAt: Date?

    enum CodingKeys: String, CodingKey {
        case id, content, ciphertext, nonce
        case conversationId = "conversation_id"
        case senderId = "sender_id"
        case mediaURL = "media_url"
        case messageType = "message_type"
        case replyToId = "reply_to_id"
        case voiceDurationSeconds = "voice_duration_seconds"
        case createdAt = "created_at"
    }

    var isEncrypted: Bool { ciphertext != nil }
}

// MARK: - Relative time

extension Date {
    /// "5h", "10h", "3d" — the compact form the notification rows use.
    var tfShortRelative: String {
        let seconds = max(0, Date().timeIntervalSince(self))
        switch seconds {
        case ..<60:     return "now"
        case ..<3600:   return "\(Int(seconds / 60))m"
        case ..<86_400: return "\(Int(seconds / 3600))h"
        case ..<604_800: return "\(Int(seconds / 86_400))d"
        default:
            let weeks = Int(seconds / 604_800)
            return weeks < 52 ? "\(weeks)w" : "\(weeks / 52)y"
        }
    }
}

// MARK: - Group

/// A group is where a post lives. `posts.group_id` is nullable, so a post is
/// either in a group or on the open feed — the same shape a subreddit has, and
/// the reason a group needs an identity of its own rather than just a name:
/// it is attributed on every post, in every notification, and in the drawer.
struct TFGroup: Codable, Identifiable, Hashable, Sendable {
    let id: String
    var name: String?
    var description: String?
    var emoji: String?
    /// Stored as a hex string on the server. Drives the group's circle so the
    /// list is scannable without anyone having to upload an icon.
    var color: String?
    var privacy: String?
    var visibility: String?
    var memberCount: Int?
    var adminId: String?
    var isActive: Bool?
    var createdAt: Date?

    enum CodingKeys: String, CodingKey {
        case id, name, description, emoji, color, privacy, visibility
        case memberCount = "member_count"
        case adminId = "admin_id"
        case isActive = "is_active"
        case createdAt = "created_at"
    }

    var displayName: String { name ?? "Group" }

    /// Private groups are marked everywhere they appear. Someone should never
    /// have to open a group to find out that what they post in it is walled.
    var isPrivate: Bool { (privacy ?? visibility)?.lowercased() == "private" }

    var memberCountLabel: String {
        guard let count = memberCount else { return "" }
        return count == 1 ? "1 member" : "\(count.tfCompact) members"
    }
}

struct TFGroupMember: Codable, Identifiable, Hashable, Sendable {
    let id: String
    var groupId: String?
    var userId: String?
    var role: String?
    var joinedAt: Date?
    /// Present when the membership row is fetched with the group joined in.
    var groups: TFGroup?

    enum CodingKeys: String, CodingKey {
        case id, role, groups
        case groupId = "group_id"
        case userId = "user_id"
        case joinedAt = "joined_at"
    }

    var isAdmin: Bool {
        let role = role?.lowercased()
        return role == "admin" || role == "owner"
    }
}

extension Int {
    /// 1200 -> "1.2k". Member and like counts are glanced at, not read.
    var tfCompact: String {
        switch self {
        case ..<1_000: String(self)
        case ..<1_000_000:
            let thousands = Double(self) / 1_000
            return thousands < 10
                ? String(format: "%.1fk", thousands).replacingOccurrences(of: ".0k", with: "k")
                : "\(Int(thousands))k"
        default:
            let millions = Double(self) / 1_000_000
            return String(format: "%.1fm", millions).replacingOccurrences(of: ".0m", with: "m")
        }
    }
}
