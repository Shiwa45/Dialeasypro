// APP-C2: a call's duration and "connected" come from the phone's call log.
// Android reports the line open as soon as an outgoing call starts dialling,
// so the old code marked every call connected; and it timed calls with a
// counter that stops while the app is frozen behind the dialer.

import 'package:flutter_test/flutter_test.dart';

import 'package:dialeasypro/core/services/call_log_service.dart';

void main() {
  final dialed = DateTime(2026, 9, 29, 11, 0, 0);

  test('an answered call takes its talk time from the call log', () {
    final o = decideCallOutcome(
      log: {'found': true, 'durationSec': 184, 'dateMillis': dialed.millisecondsSinceEpoch},
      dialedAt: dialed,
      endedAt: dialed.add(const Duration(minutes: 4)),
      offHookAt: dialed,
    );

    expect(o.durationSec, 184);
    expect(o.connected, isTrue);
    expect(o.source, 'call_log');
    expect(o.endedAt, dialed.add(const Duration(seconds: 184)));
  });

  test('an unanswered call is not connected, however long it rang', () {
    final o = decideCallOutcome(
      log: {'found': true, 'durationSec': 0, 'dateMillis': dialed.millisecondsSinceEpoch},
      dialedAt: dialed,
      endedAt: dialed.add(const Duration(seconds: 40)),
      offHookAt: dialed, // Android said "call started" — it always does
    );

    expect(o.connected, isFalse);
    expect(o.durationSec, 0);
  });

  test('without the call log, the duration is estimated and connected is left open', () {
    final o = decideCallOutcome(
      log: null,
      dialedAt: dialed,
      endedAt: dialed.add(const Duration(seconds: 95)),
      offHookAt: dialed.add(const Duration(seconds: 5)),
    );

    expect(o.durationSec, 90, reason: 'from timestamps, not a frozen counter');
    expect(o.connected, isNull, reason: 'the agent confirms it');
    expect(o.source, 'estimate');
  });

  test('a missing log entry is treated as unknown, not as connected', () {
    final o = decideCallOutcome(
      log: {'found': false, 'reason': 'permission'},
      dialedAt: dialed,
      endedAt: dialed.add(const Duration(seconds: 30)),
    );

    expect(o.connected, isNull);
  });
}
