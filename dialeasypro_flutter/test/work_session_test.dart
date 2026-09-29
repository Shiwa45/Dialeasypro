// APP-H2: after signing out and back in without closing the app, the agent
// must go live again. start() returns early while `live` is true, and nothing
// reset it on logout or session expiry.

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:dialeasypro/core/services/presence_service.dart';
import 'package:dialeasypro/data/models/models.dart';
import 'package:dialeasypro/features/dialer/dialer_state.dart';
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

  // APP-H5: a break during the post-call step let the unsaved call be
  // thrown away (a paused dialer can be closed).
  test('no break while a call is waiting for its outcome', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final work = container.read(workSessionProvider.notifier);
    await work.start();

    final dialer = container.read(dialerProvider.notifier);
    dialer.state = DialerState(
      mode: DialerMode.single,
      phase: DialerPhase.postCall,
      queue: [Lead.fromJson({'id': 1, 'name': 'A', 'phone': '+919812300001'})],
      currentCall: DialerCallRecord(
        leadId: 1, leadName: 'A', phoneNumber: '+919812300001', startedAt: DateTime.now(),
      ),
    );

    expect(await work.takeBreak(reason: 'Tea'), isFalse);
    expect(container.read(workSessionProvider).onBreak, isFalse);
    expect(container.read(dialerProvider).phase, DialerPhase.postCall);

    PresenceService.instance.stopQuietly();
  });

  // APP-M8: the next agent on the phone must not inherit the last one's queue.
  test('signing out clears the dialer', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final dialer = container.read(dialerProvider.notifier);
    dialer.state = DialerState(
      mode: DialerMode.queue,
      phase: DialerPhase.paused,
      queue: [Lead.fromJson({'id': 1, 'name': 'A', 'phone': '+919812300001'})],
    );

    dialer.reset();

    expect(container.read(dialerProvider).mode, DialerMode.idle);
    expect(container.read(dialerProvider).queue, isEmpty);
  });
}
