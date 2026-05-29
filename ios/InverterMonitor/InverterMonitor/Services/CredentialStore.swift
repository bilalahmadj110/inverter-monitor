import Foundation
import Security

/// Keychain-backed store for the user's sign-in credentials. We persist them so the
/// app can silently re-authenticate when the Flask session cookie expires, instead
/// of dropping the user back to the login screen every ~60 minutes.
///
/// The keychain entry is scoped to `kSecClassGenericPassword` with a fixed service
/// name so it survives app reinstalls on the same device (device-local, not synced
/// to iCloud). Cleared explicitly on sign-out.
enum CredentialStore {
    private static let service = "com.inverter.monitor.credentials"
    private static let account = "inverter_user"

    struct Credentials: Equatable {
        var username: String
        var password: String
    }

    static func save(_ credentials: Credentials) {
        guard let data = try? JSONEncoder().encode([
            "u": credentials.username,
            "p": credentials.password
        ]) else { return }
        // Delete-then-add avoids the "duplicate item" error from SecItemAdd when
        // credentials already exist (common on re-login after a rotated password).
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)

        var add = query
        add[kSecValueData as String] = data
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(add as CFDictionary, nil)
    }

    static func load() -> Credentials? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var out: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &out)
        guard status == errSecSuccess, let data = out as? Data else { return nil }
        guard let dict = try? JSONDecoder().decode([String: String].self, from: data),
              let u = dict["u"], let p = dict["p"], !u.isEmpty else { return nil }
        return Credentials(username: u, password: p)
    }

    static func clear() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }
}
