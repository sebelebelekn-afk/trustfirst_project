import SwiftUI

/// One row of the sheet: an icon, a label, and what tapping it does.
struct TFAction: Identifiable {
    let id = UUID()
    let title: String
    let systemImage: String
    var isDestructive: Bool = false
    let handler: () -> Void
}

/// The bottom sheet from the ••• menu — icon-and-label rows on an opaque card,
/// with the Close button detached below it as its own capsule.
///
/// This is a real sheet rather than .confirmationDialog because the reference
/// carries leading icons and a separated Close, and the system dialog offers
/// neither. It sizes itself to its rows, so it never opens taller than it needs.
struct TFActionSheet: View {
    let actions: [TFAction]
    var onClose: () -> Void

    var body: some View {
        VStack(spacing: 10) {
            VStack(spacing: 0) {
                ForEach(Array(actions.enumerated()), id: \.element.id) { index, action in
                    Button {
                        action.handler()
                    } label: {
                        HStack(spacing: 18) {
                            Image(systemName: action.systemImage)
                                .font(.system(size: 19, weight: .regular))
                                .frame(width: 26)
                            Text(action.title)
                                .font(TF.Type.rowBody)
                            Spacer(minLength: 0)
                        }
                        .foregroundStyle(action.isDestructive ? TF.Colour.destructive : TF.Colour.label)
                        .padding(.horizontal, 22)
                        .frame(height: 60)
                        .contentShape(.rect)
                    }
                    .buttonStyle(.plain)

                    if index < actions.count - 1 {
                        Rectangle()
                            .fill(TF.Colour.hairline)
                            .frame(height: 0.5)
                            .padding(.leading, 66)
                    }
                }
            }
            .background(TF.Colour.surface, in: .rect(cornerRadius: TF.Metric.sheetRadius))

            Button(action: onClose) {
                Text("Close")
                    .font(.system(size: 17, weight: .medium))
                    .foregroundStyle(TF.Colour.secondaryLabel)
                    .frame(maxWidth: .infinity)
                    .frame(height: 54)
            }
            .background(TF.Colour.recessed, in: .capsule)
            .buttonStyle(.plain)
        }
        .padding(.horizontal, TF.Metric.gutter)
        .padding(.bottom, TF.Metric.gutter)
        .presentationBackground(.clear)
        .presentationDragIndicator(.hidden)
    }
}

extension View {
    /// Presents a TFActionSheet sized to its own content.
    func tfActionSheet(
        isPresented: Binding<Bool>,
        actions: [TFAction]
    ) -> some View {
        // 60pt a row, plus the Close capsule and the gaps around it.
        let height = CGFloat(actions.count) * 60 + 54 + 10 + TF.Metric.gutter
        return sheet(isPresented: isPresented) {
            TFActionSheet(actions: actions) { isPresented.wrappedValue = false }
                .presentationDetents([.height(height)])
        }
    }
}
