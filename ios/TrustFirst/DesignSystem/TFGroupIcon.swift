import SwiftUI

/// A group's circle: its emoji on its own colour. Groups rarely have an
/// uploaded icon, and an empty grey circle beside every one makes a list of
/// them unscannable — the colour is what your eye actually navigates by.
struct TFGroupIcon: View {
    let group: TFGroup
    var size: CGFloat = 36

    var body: some View {
        ZStack {
            Circle().fill(background)
            if let emoji = group.emoji, !emoji.isEmpty {
                Text(emoji).font(.system(size: size * 0.52))
            } else {
                Text(initial)
                    .font(.system(size: size * 0.44, weight: .semibold))
                    .foregroundStyle(.white)
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }

    private var background: Color {
        // The server's colour when it set one, otherwise a stable colour
        // derived from the id — so the same group is the same colour on every
        // device and every launch, without storing anything.
        if let hex = group.color, let parsed = Color(tfHex: hex) { return parsed }
        return Self.palette[abs(group.id.hashValue) % Self.palette.count]
    }

    private var initial: String {
        group.displayName.first.map { String($0).uppercased() } ?? "#"
    }

    private static let palette: [Color] = [
        Color(red: 0.20, green: 0.45, blue: 0.95),
        Color(red: 0.85, green: 0.33, blue: 0.28),
        Color(red: 0.16, green: 0.62, blue: 0.48),
        Color(red: 0.74, green: 0.45, blue: 0.13),
        Color(red: 0.51, green: 0.35, blue: 0.82),
        Color(red: 0.14, green: 0.55, blue: 0.70),
    ]
}

extension Color {
    /// Parses "#RRGGBB" or "RRGGBB". Returns nil rather than a default, so a
    /// bad value falls through to the derived colour instead of painting every
    /// broken group black.
    init?(tfHex hex: String) {
        var text = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.hasPrefix("#") { text.removeFirst() }
        guard text.count == 6, let value = UInt32(text, radix: 16) else { return nil }
        self.init(
            red: Double((value >> 16) & 0xFF) / 255,
            green: Double((value >> 8) & 0xFF) / 255,
            blue: Double(value & 0xFF) / 255
        )
    }
}

/// The "in <group>" line that attributes a post or a notification. Tappable
/// wherever a group can be opened.
struct TFGroupChip: View {
    let group: TFGroup
    var showsPrivacy: Bool = true

    var body: some View {
        HStack(spacing: 6) {
            TFGroupIcon(group: group, size: 20)
            Text(group.displayName)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(TF.Colour.label)
                .lineLimit(1)
            if showsPrivacy && group.isPrivate {
                Image(systemName: "lock.fill")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(TF.Colour.tertiaryLabel)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(group.isPrivate
            ? "\(group.displayName), private group"
            : group.displayName)
    }
}
