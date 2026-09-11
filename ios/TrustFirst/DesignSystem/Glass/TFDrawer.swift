import SwiftUI

/// A panel that slides in from the leading edge, the way the ☰ button opens
/// one. Written rather than borrowed from a sheet because a sheet comes up
/// from the bottom and covers the tab bar, and the point of this panel is to
/// move sideways between groups while the rest of the app stays put.
struct TFDrawer<Panel: View, Content: View>: View {
    @Binding var isOpen: Bool
    @ViewBuilder var panel: Panel
    @ViewBuilder var content: Content

    @State private var dragOffset: CGFloat = 0

    /// Leaves a strip of the app visible so it is obvious what is underneath.
    private let widthFraction: CGFloat = 0.86

    var body: some View {
        GeometryReader { proxy in
            let width = proxy.size.width * widthFraction

            ZStack(alignment: .leading) {
                content

                if isOpen || dragOffset != 0 {
                    // Dimming scales with how far the panel has actually
                    // travelled, so a half-finished drag looks half-finished.
                    Color.black
                        .opacity(0.28 * progress(width: width))
                        .ignoresSafeArea()
                        .onTapGesture { close() }
                        .accessibilityLabel("Close menu")
                        .accessibilityAddTraits(.isButton)
                }

                panel
                    .frame(width: width)
                    .frame(maxHeight: .infinity)
                    .background(TF.Colour.surface)
                    .ignoresSafeArea(edges: .vertical)
                    .offset(x: isOpen ? dragOffset : -width + dragOffset)
                    .gesture(
                        DragGesture()
                            .onChanged { value in
                                guard isOpen else { return }
                                // Only dragging it closed; pulling further open
                                // would detach it from the edge.
                                dragOffset = min(0, value.translation.width)
                            }
                            .onEnded { value in
                                guard isOpen else { return }
                                let travelled = -value.translation.width
                                let flicked = value.predictedEndTranslation.width < -width / 2
                                withAnimation(TF.Motion.morph) {
                                    if travelled > width / 3 || flicked { isOpen = false }
                                    dragOffset = 0
                                }
                            }
                    )
            }
            .animation(TF.Motion.morph, value: isOpen)
        }
    }

    private func progress(width: CGFloat) -> CGFloat {
        guard width > 0 else { return 0 }
        let travelled = isOpen ? width + dragOffset : max(0, dragOffset)
        return max(0, min(1, travelled / width))
    }

    private func close() {
        withAnimation(TF.Motion.morph) {
            isOpen = false
            dragOffset = 0
        }
    }
}
