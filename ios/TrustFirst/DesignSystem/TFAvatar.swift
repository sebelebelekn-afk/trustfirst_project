import SwiftUI

/// A round avatar that always draws something. An empty circle where a face
/// should be reads as a broken image; an initial reads as a person with no
/// picture, which is what it actually is.
struct TFAvatar: View {
    let url: String?
    var fallback: String?
    var size: CGFloat = TF.Metric.avatar

    var body: some View {
        Group {
            if let url, let parsed = URL(string: url) {
                AsyncImage(url: parsed) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable().scaledToFill()
                    default:
                        placeholder
                    }
                }
            } else {
                placeholder
            }
        }
        .frame(width: size, height: size)
        .clipShape(.circle)
    }

    private var placeholder: some View {
        ZStack {
            TF.Colour.recessed
            Text(initial)
                .font(.system(size: size * 0.42, weight: .semibold))
                .foregroundStyle(TF.Colour.secondaryLabel)
        }
    }

    private var initial: String {
        let trimmed = (fallback ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        // Skip a leading @ so "@sebe" shows S, not @.
        let letters = trimmed.drop { $0 == "@" }
        return letters.first.map { String($0).uppercased() } ?? "?"
    }
}

/// The tier badge beside a name. Reads a badge the server granted; it can never
/// award one — that hole was closed on the server and is not reopened here.
struct TFBadge: View {
    let badge: TFUser.Badge
    var size: CGFloat = 15

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size, weight: .semibold))
            .foregroundStyle(colour)
            .accessibilityLabel(label)
    }

    private var symbol: String {
        switch badge {
        case .verified, .creator: "checkmark.seal.fill"
        case .golden: "rosette"
        }
    }

    private var colour: Color {
        switch badge {
        case .verified: TF.Colour.badgeVerified
        case .creator: TF.Colour.badgeCreator
        case .golden: TF.Colour.badgeGolden
        }
    }

    private var label: String {
        switch badge {
        case .verified: "Verified"
        case .creator: "Creator"
        case .golden: "Influencer"
        }
    }
}
