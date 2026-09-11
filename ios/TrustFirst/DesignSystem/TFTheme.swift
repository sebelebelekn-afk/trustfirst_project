import SwiftUI
import UIKit

// The whole look lives here. Every colour, radius and duration the app draws
// with is one of these values, so rebranding is editing this file rather than
// hunting through screens.
//
// The palette is read off the light, near-white direction: white surfaces,
// a grey-blue for anything recessed (search fields, unread rows), and a single
// saturated blue for "this one is selected". Liquid Glass supplies the depth,
// so the colours underneath it stay flat and quiet on purpose — a glass layer
// over an already-busy background reads as mud.
enum TF {

    // MARK: - Colour

    enum Colour {
        /// The page itself. Glass is only legible over something, and this is it.
        static let canvas = Color(light: 0xFFFFFF, dark: 0x000000)
        /// Cards and rows that sit on the canvas.
        static let surface = Color(light: 0xFFFFFF, dark: 0x101214)
        /// Recessed containers: search fields, the Ask pill, inert capsules.
        static let recessed = Color(light: 0xE8ECEF, dark: 0x1E2225)
        /// The wash behind a row that has not been read yet.
        static let unread = Color(light: 0xEDF1F3, dark: 0x14191D)

        static let label = Color(light: 0x0F1419, dark: 0xF2F4F5)
        static let secondaryLabel = Color(light: 0x5B6B74, dark: 0x9AA6AD)
        static let tertiaryLabel = Color(light: 0x8A979E, dark: 0x6B767C)

        /// Selection: the tab underline, the caret, the active pill.
        static let accent = Color(light: 0x1F5EFF, dark: 0x4C83FF)
        /// The fill behind the selected item in the floating tab bar.
        static let selectedPill = Color(light: 0xDCE2E6, dark: 0x2A3035)

        static let hairline = Color(light: 0xE3E7EA, dark: 0x24292D)
        static let destructive = Color(light: 0xD93025, dark: 0xFF6B5E)

        // Verification badges, carried over from the web app's three tiers.
        static let badgeVerified = Color(light: 0x1D9BF0, dark: 0x4DB8F5)
        static let badgeCreator  = Color(light: 0x6E7A82, dark: 0xC9D1D6)
        static let badgeGolden   = Color(light: 0xE0A43B, dark: 0xF0BC5E)
    }

    // MARK: - Type

    enum Typography {
        static let screenTitle  = Font.system(size: 20, weight: .semibold)
        static let sectionTitle = Font.system(size: 15, weight: .semibold)
        static let rowTitle     = Font.system(size: 17, weight: .semibold)
        static let rowBody      = Font.system(size: 16, weight: .regular)
        static let caption      = Font.system(size: 13, weight: .regular)
        static let tabLabel     = Font.system(size: 11, weight: .medium)
        /// Segmented tabs read heavier when selected, which is most of the
        /// signal — the underline only confirms it.
        static func segment(selected: Bool) -> Font {
            .system(size: 17, weight: selected ? .semibold : .regular)
        }
    }

    // MARK: - Metrics

    enum Metric {
        static let gutter: CGFloat = 16
        static let rowSpacing: CGFloat = 14
        /// Floating furniture (tab bar, FAB) is inset from the screen edge —
        /// that inset is what makes it read as floating rather than docked.
        static let floatingInset: CGFloat = 12
        static let toolbarButton: CGFloat = 44
        static let fab: CGFloat = 56
        static let avatar: CGFloat = 44
        static let fieldHeight: CGFloat = 52
        static let fieldRadius: CGFloat = 26
        static let sheetRadius: CGFloat = 22
    }

    // MARK: - Motion

    enum Motion {
        /// Glass morphs want spring, not ease — the shape is physical.
        static let morph = Animation.spring(response: 0.38, dampingFraction: 0.78)
        static let tap = Animation.spring(response: 0.26, dampingFraction: 0.72)
        static let settle = Animation.smooth(duration: 0.22)
    }
}

// Hex is how the palette above is written, because that is how it is read off a
// design. Two values per colour so the app is never light-mode-only by accident.
extension Color {
    init(light: UInt32, dark: UInt32) {
        self.init(uiColor: UIColor { traits in
            UIColor(hex: traits.userInterfaceStyle == .dark ? dark : light)
        })
    }
}

extension UIColor {
    fileprivate convenience init(hex: UInt32) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: 1
        )
    }
}

// MARK: - Field style

/// The recessed capsule used by every text field. Applied to a plain TextField
/// rather than wrapping one, so `.focused()` and `.textContentType()` at the
/// call site still land on the real field.
struct TFFieldStyle: ViewModifier {
    func body(content: Content) -> some View {
        content
            .font(TF.Typography.rowBody)
            .foregroundStyle(TF.Colour.label)
            .tint(TF.Colour.accent)
            .padding(.horizontal, 16)
            .frame(height: TF.Metric.fieldHeight)
            .background(TF.Colour.recessed, in: .rect(cornerRadius: TF.Metric.fieldRadius))
    }
}

extension View {
    func tfFieldStyle() -> some View { modifier(TFFieldStyle()) }
}
