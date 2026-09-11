import SwiftUI

// The glass furniture. These are thin wrappers over Apple's real Liquid Glass
// APIs — .glassEffect, GlassEffectContainer, glassEffectID — and deliberately
// not reimplementations of them. Nothing here paints its own blur or draws a
// fake highlight border: the system renders the material, refracts what is
// behind it, and reacts to motion, and none of that can be faked convincingly.

// MARK: - Circular icon button

/// The lone button in the top-left of every screen (☰, ✕, ←). Circular, glass,
/// and sized to the 44pt minimum touch target rather than to the glyph.
struct TFGlassIconButton: View {
    let systemImage: String
    var accessibilityLabel: String
    var tint: Color? = nil
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(tint ?? TF.Colour.label)
                .frame(width: TF.Metric.toolbarButton, height: TF.Metric.toolbarButton)
        }
        .glassEffect(.regular.interactive(), in: .circle)
        .accessibilityLabel(accessibilityLabel)
    }
}

// MARK: - Grouped icon capsule

/// Several icons sharing one capsule of glass, the way the ＋ / mark-read / •••
/// cluster does in the top-right. They share a single GlassEffectContainer so
/// the material is continuous across them instead of three separate pills
/// sitting next to each other.
struct TFGlassIconGroup<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        HStack(spacing: 0) { content }
            .glassEffect(.regular, in: .capsule)
    }
}

/// One icon inside a TFGlassIconGroup. It carries no glass of its own — the
/// group owns the material — so it is just a correctly sized hit target.
struct TFGlassGroupItem: View {
    let systemImage: String
    var accessibilityLabel: String
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(TF.Colour.label)
                .frame(width: TF.Metric.toolbarButton, height: TF.Metric.toolbarButton)
        }
        .accessibilityLabel(accessibilityLabel)
    }
}

// MARK: - Floating action button

/// The circular compose button that hovers above the tab bar. Tinted glass
/// rather than a flat filled circle, so it still refracts the feed moving
/// underneath it.
struct TFFloatingActionButton: View {
    let systemImage: String
    var accessibilityLabel: String
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(TF.Colour.label)
                .frame(width: TF.Metric.fab, height: TF.Metric.fab)
        }
        .glassEffect(.regular.interactive(), in: .circle)
        .accessibilityLabel(accessibilityLabel)
        .padding(.trailing, TF.Metric.gutter)
    }
}

// MARK: - Search field

/// The recessed capsule field. This one is intentionally *not* glass: in the
/// reference it is an opaque grey-blue well, and that contrast is what makes
/// the floating glass above it read as floating. Glass on glass reads as fog.
struct TFSearchField: View {
    let placeholder: String
    @Binding var text: String
    var showsLeadingIcon: Bool = true
    var onSubmit: () -> Void = {}

    @FocusState private var focused: Bool

    var body: some View {
        HStack(spacing: 10) {
            if showsLeadingIcon {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 17, weight: .medium))
                    .foregroundStyle(TF.Colour.secondaryLabel)
            }
            TextField(placeholder, text: $text)
                .font(TF.Typography.rowBody)
                .foregroundStyle(TF.Colour.label)
                .tint(TF.Colour.accent)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .focused($focused)
                .submitLabel(.search)
                .onSubmit(onSubmit)

            if !text.isEmpty {
                Button {
                    text = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 17))
                        .foregroundStyle(TF.Colour.tertiaryLabel)
                }
                .accessibilityLabel("Clear search")
            }
        }
        .padding(.horizontal, 16)
        .frame(height: TF.Metric.fieldHeight)
        .background(TF.Colour.recessed, in: .rect(cornerRadius: TF.Metric.fieldRadius))
        .contentShape(.rect)
        .onTapGesture { focused = true }
    }
}

// MARK: - Segmented tabs

/// Two or more labels with a sliding underline, as on Notifications / Chat.
/// The underline slides between positions with matchedGeometryEffect rather
/// than fading, because a bar that jumps reads as a redraw and a bar that
/// slides reads as the same bar moving.
struct TFSegmentedTabs<Value: Hashable>: View {
    let tabs: [(value: Value, title: String)]
    @Binding var selection: Value
    @Namespace private var underline

    var body: some View {
        HStack(spacing: 0) {
            ForEach(tabs, id: \.value) { item in
                let isSelected = item.value == selection
                Button {
                    withAnimation(TF.Motion.settle) { selection = item.value }
                } label: {
                    VStack(spacing: 10) {
                        Text(item.title)
                            .font(TF.Typography.segment(selected: isSelected))
                            .foregroundStyle(isSelected ? TF.Colour.label : TF.Colour.secondaryLabel)
                        ZStack {
                            // An always-present clear bar keeps every tab the
                            // same height, so selecting one never nudges the
                            // content below by three points.
                            Capsule().fill(.clear).frame(height: 3)
                            if isSelected {
                                Capsule()
                                    .fill(TF.Colour.accent)
                                    .frame(height: 3)
                                    .matchedGeometryEffect(id: "tf.tabs.underline", in: underline)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .contentShape(.rect)
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(isSelected ? [.isSelected] : [])
            }
        }
        .padding(.top, 8)
        .overlay(alignment: .bottom) {
            Rectangle().fill(TF.Colour.hairline).frame(height: 0.5)
        }
    }
}
