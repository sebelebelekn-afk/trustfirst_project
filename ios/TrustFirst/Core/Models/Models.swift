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

    enum CodingKeys: String, CodingKey {
        case id, users
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
    var type: String?
    var previewText: String?
    var read: Bool?
    var createdAt: Date?
    var actor: TFUser?

    enum CodingKeys: String, CodingKey {
        case id, type, read, actor
        case userId = "user_id"
        case actorId = "actor_id"
        case previewText = "preview_text"
        case createdAt = "created_at"
    }

    var isUnread: Bool { read != true }
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
