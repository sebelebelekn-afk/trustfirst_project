import SwiftUI

/// A single group: its header, and the posts in it.
struct GroupView: View {
    let group: TFGroup

    @Environment(Database.self) private var database
    @State private var posts: [TFPost] = []
    @State private var isLoading = true
    @State private var failure: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                header

                if isLoading {
                    ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
                } else if let failure {
                    Text(failure)
                        .font(TF.Type.caption)
                        .foregroundStyle(TF.Colour.destructive)
                        .padding(TF.Metric.gutter)
                } else if posts.isEmpty {
                    Text("Nothing posted in \(group.displayName) yet.")
                        .font(TF.Type.rowBody)
                        .foregroundStyle(TF.Colour.secondaryLabel)
                        .padding(TF.Metric.gutter)
                } else {
                    ForEach(posts) { post in
                        // The group is already the whole screen, so repeating
                        // it on every row would be noise.
                        PostRow(post: post.withoutGroup())
                        Rectangle().fill(TF.Colour.hairline).frame(height: 0.5)
                    }
                }
            }
        }
        .background(TF.Colour.canvas)
        .navigationTitle(group.displayName)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                TFGroupIcon(group: group, size: 56)
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 5) {
                        Text(group.displayName)
                            .font(.system(size: 22, weight: .bold))
                            .foregroundStyle(TF.Colour.label)
                        if group.isPrivate {
                            Image(systemName: "lock.fill")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(TF.Colour.tertiaryLabel)
                        }
                    }
                    if !group.memberCountLabel.isEmpty {
                        Text(group.memberCountLabel)
                            .font(TF.Type.caption)
                            .foregroundStyle(TF.Colour.secondaryLabel)
                    }
                }
                Spacer(minLength: 0)
            }

            if let description = group.description, !description.isEmpty {
                Text(description)
                    .font(TF.Type.rowBody)
                    .foregroundStyle(TF.Colour.secondaryLabel)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(TF.Metric.gutter)
    }

    private func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            posts = try await database.fetch(
                Query("posts")
                    .select("*, users:user_id(id,username,full_name,avatar_url,badge_tier,verified,ai_label)")
                    .eq("group_id", group.id)
                    .order("created_at")
                    .limit(30),
                as: TFPost.self
            )
            failure = nil
        } catch {
            failure = error.localizedDescription
        }
    }
}

extension TFPost {
    /// A copy with the group attribution stripped, for use inside that group.
    func withoutGroup() -> TFPost {
        var copy = self
        copy.groups = nil
        return copy
    }
}
