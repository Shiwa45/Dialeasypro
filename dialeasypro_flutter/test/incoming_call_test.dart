// APP-H6: an incoming call during an auto-dial session must not take over the
// call the dialer is working on.

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:dialeasypro/core/services/phone_service.dart';
import 'package:dialeasypro/core/services/presence_service.dart';
import 'package:dialeasypro/data/models/models.dart';
import 'package:dialeasypro/features/dialer/dialer_state.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));
  tearDown(() => PresenceService.instance.stopQuietly());

  ProviderContainer postCall() {
    final container = ProviderContainer();
    final record = DialerCallRecord(
      leadId: 1, leadName: 'Asha', phoneNumber: '+919812300001', startedAt: DateTime.now(),
    )
      ..endedAt = DateTime.now()
      ..durationSec = 184;
    container.read(dialerProvider.notifier).state = DialerState(
      mode: DialerMode.queue,
      phase: DialerPhase.postCall,
      queue: [Lead.fromJson({'id': 1, 'name': 'Asha', 'phone': '+919812300001'})],
      currentCall: record,
    );
    return container;
  }

  Future<void> emit(CallStatus status, {String? number, int? duration}) async {
    PhoneService.instance.debugEmit(PhoneCallEvent(status: status, number: number, durationSec: duration));
    await Future<void>.delayed(Duration.zero);
  }

  test('a customer calling back during the post-call step changes nothing', () async {
    final container = postCall();
    addTearDown(container.dispose);

    await emit(CallStatus.ringing, number: '+919999900000');
    await emit(CallStatus.active, number: '+919999900000');
    await emit(CallStatus.ended, number: '+919999900000', duration: 30);

    final state = container.read(dialerProvider);
    expect(state.phase, DialerPhase.postCall);
    expect(state.currentCall!.durationSec, 184, reason: 'the other call must not overwrite ours');
  });

  test('an incoming call with a hidden number is ignored too', () async {
    final container = postCall();
    addTearDown(container.dispose);

    await emit(CallStatus.ringing);
    await emit(CallStatus.active);
    await emit(CallStatus.ended, duration: 12);

    expect(container.read(dialerProvider).phase, DialerPhase.postCall);
  });
}
