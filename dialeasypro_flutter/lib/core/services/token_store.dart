import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

// ============================================================
// DialEasypro — Where the sign-in tokens live
//
// Encrypted at rest: the Android Keystore holds the key, so a copy of the
// app's files is no use without the phone itself.
//
// The tokens used to sit in plain SharedPreferences because the encrypted
// store "returned null on some devices after rebuilds" — the Authorization
// header silently vanished and every request 401'd. That is what happens
// when Android restores encrypted data from a backup onto a phone whose
// Keystore key was not in it; backups are now off (data_extraction_rules).
// Should a phone still misbehave, it is caught here instead of in every
// request:
//   - every write is read back, and a store that cannot keep a token is not
//     trusted: the token goes to plain storage, as before;
//   - tokens found in plain storage (older app versions, or that fallback)
//     move into the encrypted store as soon as it proves it works;
//   - the running app reads from memory, so a store that loses a token
//     mid-session cannot sign the agent out.
// ============================================================

/// The encrypted backend, swappable in tests.
abstract class SecretStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

class _KeystoreSecretStore implements SecretStore {
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String value) => _storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

class TokenStore {
  TokenStore({SecretStore? secure}) : _secure = secure ?? _KeystoreSecretStore();

  static TokenStore instance = TokenStore();

  static const kAccess = 'access_token';
  static const kRefresh = 'refresh_token';

  final SecretStore _secure;

  String? _access;
  String? _refresh;
  bool _loaded = false;

  Future<String?> get access async {
    await _load();
    return _access;
  }

  Future<String?> get refresh async {
    await _load();
    return _refresh;
  }

  Future<void> save({required String access, required String refresh}) async {
    _access = access;
    _refresh = refresh;
    _loaded = true;
    await _persist(access, refresh);
  }

  Future<void> clear() async {
    _access = null;
    _refresh = null;
    _loaded = true;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(kAccess);
    await prefs.remove(kRefresh);
    for (final key in const [kAccess, kRefresh]) {
      try {
        await _secure.delete(key);
      } catch (e) {
        debugPrint('[TokenStore] could not delete $key: $e');
      }
    }
  }

  Future<void> _load() async {
    if (_loaded) return;
    String? access;
    String? refresh;
    try {
      access = await _secure.read(kAccess);
      refresh = await _secure.read(kRefresh);
    } catch (e) {
      debugPrint('[TokenStore] encrypted store unreadable: $e');
    }
    if (_blank(access) || _blank(refresh)) {
      // Not in the encrypted store: an older app version, or a phone where it
      // did not work. Move them over if it works now.
      final prefs = await SharedPreferences.getInstance();
      final plainAccess = prefs.getString(kAccess);
      final plainRefresh = prefs.getString(kRefresh);
      if (!_blank(plainAccess) && !_blank(plainRefresh)) {
        access = plainAccess;
        refresh = plainRefresh;
        await _persist(access!, refresh!);
      }
    }
    _access = _blank(access) ? null : access;
    _refresh = _blank(refresh) ? null : refresh;
    _loaded = true;
  }

  /// Encrypted when the store demonstrably keeps what it is given; plain
  /// storage otherwise. Never both.
  Future<void> _persist(String access, String refresh) async {
    final prefs = await SharedPreferences.getInstance();
    var secured = false;
    try {
      await _secure.write(kAccess, access);
      await _secure.write(kRefresh, refresh);
      secured = await _secure.read(kAccess) == access && await _secure.read(kRefresh) == refresh;
    } catch (e) {
      debugPrint('[TokenStore] encrypted store unusable: $e');
    }
    if (secured) {
      await prefs.remove(kAccess);
      await prefs.remove(kRefresh);
    } else {
      debugPrint('[TokenStore] falling back to plain storage on this phone');
      // Nothing half-written may be read back ahead of the real tokens.
      for (final key in const [kAccess, kRefresh]) {
        try {
          await _secure.delete(key);
        } catch (_) {}
      }
      await prefs.setString(kAccess, access);
      await prefs.setString(kRefresh, refresh);
    }
  }

  static bool _blank(String? s) => s == null || s.isEmpty;
}
