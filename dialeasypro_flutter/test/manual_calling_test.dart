// APP-H3 / APP-M7: calling a hand-picked list of leads from a break.
// It was refused (then an idle dialer spun forever). On a break it is manual
// calling: allowed, never auto-advancing, and it must not end the break.
// Server auto-dial queues stay refused on a break.

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:dialeasypro/core/services/presence_service.dart';
import 'package:dialeasypro/data/models/models.dart';
import 'package:dialeasypro/features/dialer/dialer_state.dart';

Lead _lead(int id) => Lead.fromJson({'id': id, 'name': 'Lead $id', 'phone': '+91981230000$id'});

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await PresenceService.instance.report(AgentStatus.breakStatus, breakReason: 'Manual calls & WhatsApp');
  });

  tearDown(() => PresenceService.instance.stopQuietly());

  test('a picked list starts on a break and waits for the agent', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final started = await container.read(dialerProvider.notifier).startQueue([_lead(1), _lead(2)]);
    await Future.delayed(const Duration(milliseconds: 1200));

    expect(started, isTrue);
    expect(container.read(dialerProvider).phase, DialerPhase.preCall,
        reason: 'no auto-dial on a break — the agent taps Call Now');
    expect(PresenceService.instance.onBreak, isTrue, reason: 'starting the list must not end the break');
  });

  test('a server auto-dial queue is still refused on a break', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    await container.read(dialerProvider.notifier).startServerQueue(7);

    expect(container.read(dialerProvider).mode, DialerMode.idle);
  });

  test('an empty selection starts nothing', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    expect(await container.read(dialerProvider.notifier).startQueue([]), isFalse);
  });
}
