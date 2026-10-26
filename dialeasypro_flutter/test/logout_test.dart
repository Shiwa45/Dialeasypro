// Sign Out must sign out even when the server does not answer.
//
// logout() waited for the "stop sending pushes to this phone" request before
// clearing the session. On a weak connection that took Dio's full timeouts
// (and a token refresh) — up to a minute and a half with nothing on screen —
// so tapping Sign Out looked as if it did nothing.

import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:dialeasypro/core/services/token_store.dart';
import 'package:dialeasypro/data/services/api_client.dart';
import 'package:dialeasypro/features/auth/auth_provider.dart';

/// A server that accepts the connection and never replies.
class _Silent implements HttpClientAdapter {
  final List<String> paths = [];

  @override
  Future<ResponseBody> fetch(RequestOptions o, Stream<Uint8List>? body, Future<void>? cancel) {
    paths.add(o.path);
    return Completer<ResponseBody>().future;
  }

  @override
  void close({bool force = false}) {}
}

class _Keystore implements SecretStore {
  final Map<String, String> data = {};
  @override
  Future<String?> read(String key) async => data[key];
  @override
  Future<void> write(String key, String value) async => data[key] = value;
  @override
  Future<void> delete(String key) async => data.remove(key);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // The phone's notification plugin answers, as on a device: logout() then
  // goes on to the server call. (Unstubbed it throws, which skipped that call.)
  setUpAll(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('dexterous.com/flutter/local_notifications'),
      (_) async => null,
    );
  });

  test('Sign Out finishes quickly when the server never answers', () async {
    SharedPreferences.setMockInitialValues({});
    TokenStore.instance = TokenStore(secure: _Keystore());
    await ApiClient.instance.saveTokens(access: 'a', refresh: 'r');
    final server = _Silent();
    ApiClient.instance.dio.httpClientAdapter = server;

    final auth = AuthNotifier();
    final watch = Stopwatch()..start();
    await auth.logout().timeout(const Duration(seconds: 10));

    expect(server.paths, contains('/auth/notifications/device/'),
        reason: 'the phone is still unregistered from pushes');
    expect(watch.elapsed, lessThan(const Duration(seconds: 8)));
    expect(auth.state.status, AuthStatus.unauthenticated);
    expect(await ApiClient.instance.accessToken, isNull, reason: 'the session is gone');
  });
}
