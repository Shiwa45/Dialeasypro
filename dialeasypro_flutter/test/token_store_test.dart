import 'package:dialeasypro/core/services/token_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _Keystore implements SecretStore {
  _Keystore({this.broken = false, this.forgets = false});

  /// Throws on every call, like a Keystore that cannot be opened.
  final bool broken;

  /// Accepts writes but reads back null — the failure the old comment described.
  final bool forgets;

  final Map<String, String> data = {};

  @override
  Future<String?> read(String key) async {
    if (broken) throw Exception('keystore');
    return forgets ? null : data[key];
  }

  @override
  Future<void> write(String key, String value) async {
    if (broken) throw Exception('keystore');
    data[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    if (broken) throw Exception('keystore');
    data.remove(key);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('tokens are kept encrypted, not in plain storage', () async {
    SharedPreferences.setMockInitialValues({});
    final keystore = _Keystore();
    await TokenStore(secure: keystore).save(access: 'a1', refresh: 'r1');

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('access_token'), isNull);
    expect(prefs.getString('refresh_token'), isNull);

    // A fresh start of the app finds them.
    final restarted = TokenStore(secure: keystore);
    expect(await restarted.access, 'a1');
    expect(await restarted.refresh, 'r1');
  });

  test('tokens from an older app version move into the encrypted store', () async {
    SharedPreferences.setMockInitialValues({'access_token': 'old-a', 'refresh_token': 'old-r'});
    final keystore = _Keystore();
    final store = TokenStore(secure: keystore);

    expect(await store.access, 'old-a');
    expect(keystore.data, {'access_token': 'old-a', 'refresh_token': 'old-r'});
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('access_token'), isNull);
  });

  for (final kind in ['broken', 'forgetful']) {
    test('a $kind encrypted store falls back to plain storage and keeps the session', () async {
      SharedPreferences.setMockInitialValues({});
      final keystore = _Keystore(broken: kind == 'broken', forgets: kind == 'forgetful');
      await TokenStore(secure: keystore).save(access: 'a1', refresh: 'r1');

      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('access_token'), 'a1');
      expect(keystore.data, isEmpty);

      final restarted = TokenStore(secure: keystore);
      expect(await restarted.access, 'a1');
      expect(await restarted.refresh, 'r1');
    });
  }

  test('sign-out clears both stores', () async {
    SharedPreferences.setMockInitialValues({'access_token': 'stale', 'refresh_token': 'stale'});
    final keystore = _Keystore()..data.addAll({'access_token': 'a', 'refresh_token': 'r'});
    final store = TokenStore(secure: keystore);
    await store.clear();

    expect(await store.access, isNull);
    expect(keystore.data, isEmpty);
    expect(await TokenStore(secure: keystore).access, isNull);
  });
}
