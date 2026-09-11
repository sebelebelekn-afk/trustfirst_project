import Foundation
import Security

/// Where the refresh token lives. Not UserDefaults: a refresh token is a
/// long-lived credential, and UserDefaults is a plist that comes out of an
/// unencrypted backup in plain text.
///
/// kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly keeps it readable for
/// background refresh after the first unlock, and stops it travelling to
/// another device in a backup.
enum Keychain {
    private static let service = "app.trustfirst.mobile"

    static func set(_ value: String, for key: String) {
        let data = Data(value.utf8)
        var query = baseQuery(key)
        SecItemDelete(query as CFDictionary)
        query[kSecValueData as String] = data
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(query as CFDictionary, nil)
    }

    static func get(_ key: String) -> String? {
        var query = baseQuery(key)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func remove(_ key: String) {
        SecItemDelete(baseQuery(key) as CFDictionary)
    }

    private static func baseQuery(_ key: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
    }
}
