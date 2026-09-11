import SwiftUI

/// One post in a feed. The group is attributed first, above the author,
/// because in a feed assembled from several groups the group is what tells you
/// why this post is in front of you.
struct PostRow: View {
    let post: TFPost
    var onOpenGroup: (TFGroup) -> Void = { _ in }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let group = post.groups {
                Button { onOpenGroup(group) } label: {
                    HStack(spacing: 6) {
                        TFGroupChip(group: group)
                        if let created = post.createdAt {
                            Text("· \(created.tfShortRelative)")
                                .font(TF.Typography.caption)
                                .foregroundStyle(TF.Colour.tertiaryLabel)
                        }
                        Spacer(minLength: 0)
                    }
                    .contentShape(.rect)
                }
                .buttonStyle(.plain)
            }

            author

            if let text = post.textContent, !text.isEmpty {
                Text(text)
                    .font(TF.Typography.rowBody)
                    .foregroundStyle(TF.Colour.label)
                    .lineLimit(8)
                    .fixedSize(horizontal: false, vertical: true)
            }

            media
            counts
        }
        .padding(.horizontal, TF.Metric.gutter)
        .padding(.vertical, TF.Metric.rowSpacing)
        .background(TF.Colour.surface)
        .contentShape(.rect)
    }

    private var author: some View {
        HStack(spacing: 8) {
            TFAvatar(url: post.users?.avatarURL, fallback: post.users?.displayName, size: 28)
            HStack(spacing: 4) {
                Text(post.users?.displayName ?? "Someone")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(TF.Colour.label)
                if let badge = post.users?.badge { TFBadge(badge: badge, size: 13) }
                // Posts made by Eddie are labelled as such. A reader should
                // never have to guess whether a person wrote something.
                if post.users?.aiLabel == true {
                    Text("AI")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(TF.Colour.secondaryLabel)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(TF.Colour.recessed, in: .capsule)
                }
            }
            Spacer(minLength: 0)
        }
    }

    @ViewBuilder
    private var media: some View {
        if let urlString = post.thumbnailURL ?? post.mediaURL, let url = URL(string: urlString) {
            ZStack {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image): image.resizable().scaledToFill()
                    default: TF.Colour.recessed
                    }
                }
                // Video posts get a play glyph over the still, so a thumbnail
                // is never mistaken for a photo that will not move.
                if post.kind == .video || post.kind == .trustclip {
                    Image(systemName: "play.circle.fill")
                        .font(.system(size: 44))
                        .foregroundStyle(.white.opacity(0.92))
                        .shadow(radius: 8)
                }
            }
            .frame(maxWidth: .infinity)
            .frame(height: 220)
            .clipShape(.rect(cornerRadius: 14))
        }
    }

    private var counts: some View {
        HStack(spacing: 18) {
            Label(post.likeCount?.tfCompact ?? "0", systemImage: "heart")
            Label(post.commentCount?.tfCompact ?? "0", systemImage: "bubble.right")
            Label(post.repostCount?.tfCompact ?? "0", systemImage: "arrow.2.squarepath")
            Spacer(minLength: 0)
        }
        .font(.system(size: 13, weight: .medium))
        .foregroundStyle(TF.Colour.secondaryLabel)
        .labelStyle(.titleAndIcon)
    }
}
