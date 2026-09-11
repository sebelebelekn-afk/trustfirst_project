import SwiftUI

enum AppTab: Hashable {
    case home, inbox, you
}

/// The three-tab shell. The bar itself is the system's, which is the whole
/// point: on iOS 26 that is a real floating Liquid Glass bar that content
/// scrolls underneath, and .tabBarMinimizeBehavior(.onScrollDown) is what makes
/// it shrink out of the way when someone starts reading.
struct MainTabView: View {
    @State private var selection: AppTab = .home

    var body: some View {
        TabView(selection: $selection) {
            Tab("Home", systemImage: "house", value: AppTab.home) {
                HomeView()
            }
            Tab("Inbox", systemImage: "bell", value: AppTab.inbox) {
                InboxView()
            }
            Tab("You", systemImage: "person.crop.circle", value: AppTab.you) {
                YouView()
            }
        }
        .tabBarMinimizeBehavior(.onScrollDown)
    }
}

// Placeholders so the shell builds and runs end to end. These are the next
// screens to write, not a decision that they are empty.
struct HomeView: View {
    var body: some View {
        NavigationStack {
            ScrollView {
                Text("Feed goes here")
                    .font(TF.Type.rowBody)
                    .foregroundStyle(TF.Colour.secondaryLabel)
                    .frame(maxWidth: .infinity, minHeight: 400)
            }
            .background(TF.Colour.canvas)
            .navigationTitle("Home")
        }
    }
}

struct YouView: View {
    @Environment(AuthStore.self) private var auth

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Text("Your profile goes here")
                    .font(TF.Type.rowBody)
                    .foregroundStyle(TF.Colour.secondaryLabel)
                Button("Sign out") { Task { await auth.signOut() } }
                    .buttonStyle(.glass)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(TF.Colour.canvas)
            .navigationTitle("You")
        }
    }
}
