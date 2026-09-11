import SwiftUI

/// What the ☰ button opens: the groups you are in, and the way into each one.
struct GroupsPanel: View {
    let store: GroupsStore
    var onSelect: (TFGroup) -> Void
    var onClose: () -> Void

    @State private var filter = ""

    private var visible: [TFGroup] {
        guard !filter.isEmpty else { return store.groups }
        return store.groups.filter {
            $0.displayName.localizedCaseInsensitiveContains(filter)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Your groups")
                    .font(TF.Type.screenTitle)
                    .foregroundStyle(TF.Colour.label)
                Spacer()
                TFGlassIconButton(systemImage: "xmark", accessibilityLabel: "Close menu", action: onClose)
            }
            .padding(.top, 8)

            // Only worth showing once the list is long enough to need it.
            if store.groups.count > 6 {
                TFSearchField(placeholder: "Filter groups", text: $filter)
            }

            if store.isLoading && store.groups.isEmpty {
                ProgressView().frame(maxWidth: .infinity)
            } else if let failure = store.failure, store.groups.isEmpty {
                Text(failure)
                    .font(TF.Type.caption)
                    .foregroundStyle(TF.Colour.destructive)
            } else if store.groups.isEmpty {
                Text("You are not in any groups yet. Join one and its posts show up on your home feed.")
                    .font(TF.Type.rowBody)
                    .foregroundStyle(TF.Colour.secondaryLabel)
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(visible) { group in
                            Button {
                                onSelect(group)
                            } label: {
                                HStack(spacing: 12) {
                                    TFGroupIcon(group: group)
                                    VStack(alignment: .leading, spacing: 2) {
                                        HStack(spacing: 5) {
                                            Text(group.displayName)
                                                .font(.system(size: 16, weight: .medium))
                                                .foregroundStyle(TF.Colour.label)
                                                .lineLimit(1)
                                            if group.isPrivate {
                                                Image(systemName: "lock.fill")
                                                    .font(.system(size: 10, weight: .semibold))
                                                    .foregroundStyle(TF.Colour.tertiaryLabel)
                                            }
                                        }
                                        HStack(spacing: 6) {
                                            if !group.memberCountLabel.isEmpty {
                                                Text(group.memberCountLabel)
                                            }
                                            if store.isAdmin(of: group) {
                                                Text("Admin").foregroundStyle(TF.Colour.accent)
                                            }
                                        }
                                        .font(TF.Type.caption)
                                        .foregroundStyle(TF.Colour.tertiaryLabel)
                                    }
                                    Spacer(minLength: 0)
                                }
                                .padding(.vertical, 10)
                                .contentShape(.rect)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .scrollIndicators(.hidden)
            }

            Spacer(minLength: 0)
        }
        .padding(.horizontal, TF.Metric.gutter)
        .padding(.top, 60)
    }
}
