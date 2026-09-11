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
                ProfileView()
            }
        }
        .tabBarMinimizeBehavior(.onScrollDown)
    }
}
