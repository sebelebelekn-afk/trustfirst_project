import SwiftUI

/// "Post to" — choosing which group a post goes into. Also allows posting to
/// no group at all, because `posts.group_id` is nullable and the open feed is
/// a real destination rather than a missing value.
struct GroupPickerView: View {
    let store: GroupsStore
    @Binding var selection: TFGroup?
    var allowsOpenFeed: Bool = true

    @Environment(\.dismiss) private var dismiss
    @State private var term = ""

    private var visible: [TFGroup] {
        guard !term.isEmpty else { return store.groups }
        return store.groups.filter {
            $0.displayName.localizedCaseInsensitiveContains(term)
                || ($0.description ?? "").localizedCaseInsensitiveContains(term)
        }
    }

    var body: some View {
        ZStack(alignment: .bottom) {
            VStack(spacing: 0) {
                header

                if store.groups.isEmpty {
                    EmptyState(
                        systemImage: "person.3",
                        title: "No groups yet",
                        message: "Join a group and it shows up here as somewhere to post."
                    )
                } else {
                    ScrollView {
                        LazyVStack(spacing: 0) {
                            if allowsOpenFeed && term.isEmpty {
                                openFeedRow
                                Rectangle().fill(TF.Colour.hairline).frame(height: 0.5)
                            }
                            ForEach(visible) { group in
                                row(group)
                                Rectangle().fill(TF.Colour.hairline).frame(height: 0.5)
                            }
                        }
                        // Clears the floating search capsule at the bottom.
                        .padding(.bottom, 90)
                    }
                }
            }

            // The search field floats over the list on its own glass, so the
            // list keeps its full height and the field is always reachable.
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 17, weight: .medium))
                    .foregroundStyle(TF.Colour.secondaryLabel)
                TextField("Search for a group", text: $term)
                    .font(TF.Type.rowBody)
                    .tint(TF.Colour.accent)
                    .autocorrectionDisabled()
            }
            .padding(.horizontal, 20)
            .frame(height: TF.Metric.fieldHeight)
            .glassEffect(.regular, in: .capsule)
            .padding(.horizontal, TF.Metric.gutter)
            .padding(.bottom, TF.Metric.gutter)
        }
        .background(TF.Colour.canvas)
    }

    private var header: some View {
        ZStack {
            Text("Post to")
                .font(TF.Type.screenTitle)
                .foregroundStyle(TF.Colour.label)
            HStack {
                TFGlassIconButton(systemImage: "xmark", accessibilityLabel: "Close") { dismiss() }
                Spacer()
            }
        }
        .padding(.horizontal, TF.Metric.gutter)
        .padding(.vertical, 10)
    }

    private var openFeedRow: some View {
        Button {
            selection = nil
            dismiss()
        } label: {
            HStack(spacing: 12) {
                ZStack {
                    Circle().fill(TF.Colour.recessed)
                    Image(systemName: "globe")
                        .font(.system(size: 18))
                        .foregroundStyle(TF.Colour.secondaryLabel)
                }
                .frame(width: 44, height: 44)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Your feed")
                        .font(TF.Type.rowTitle)
                        .foregroundStyle(TF.Colour.label)
                    Text("Anyone who follows you")
                        .font(TF.Type.caption)
                        .foregroundStyle(TF.Colour.secondaryLabel)
                }
                Spacer(minLength: 0)
                if selection == nil {
                    Image(systemName: "checkmark")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(TF.Colour.accent)
                }
            }
            .padding(.horizontal, TF.Metric.gutter)
            .padding(.vertical, 12)
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
    }

    private func row(_ group: TFGroup) -> some View {
        Button {
            selection = group
            dismiss()
        } label: {
            HStack(alignment: .top, spacing: 12) {
                TFGroupIcon(group: group, size: 44)
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 5) {
                        Text(group.displayName)
                            .font(TF.Type.rowTitle)
                            .foregroundStyle(TF.Colour.label)
                        if group.isPrivate {
                            Image(systemName: "lock.fill")
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundStyle(TF.Colour.tertiaryLabel)
                        }
                    }
                    if !group.memberCountLabel.isEmpty {
                        Text(group.memberCountLabel)
                            .font(TF.Type.caption)
                            .foregroundStyle(TF.Colour.secondaryLabel)
                    }
                    if let description = group.description, !description.isEmpty {
                        Text(description)
                            .font(TF.Type.caption)
                            .foregroundStyle(TF.Colour.secondaryLabel)
                            .lineLimit(2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer(minLength: 0)
                if selection?.id == group.id {
                    Image(systemName: "checkmark")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(TF.Colour.accent)
                }
            }
            .padding(.horizontal, TF.Metric.gutter)
            .padding(.vertical, 12)
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
    }
}
