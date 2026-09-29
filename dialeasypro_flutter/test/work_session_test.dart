// APP-H2: after signing out and back in without closing the app, the agent
// must go live again. start() returns early while `live` is true, and nothing
// reset it on logout or session expiry.

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:dialeasypro/core/services/presence_service.dart';
import 'package:dialeasypro/features/work/work_session.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('signing out and back in starts a fresh live session', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final work = container.read(workSessionProvider.notifier);

    await work.start();
    expect(container.read(workSessionProvider).live, isTrue);

    work.signedOut();
    expect(container.read(workSessionProvider).live, isFalse);
    expect(PresenceService.instance.current, AgentStatus.offline);

    await work.start(); // the next sign-in
    expect(container.read(workSessionProvider).live, isTrue);
    expect(PresenceService.instance.current, AgentStatus.available,
        reason: 'the new session must report the agent available');

    PresenceService.instance.stopQuietly();
  });
}
