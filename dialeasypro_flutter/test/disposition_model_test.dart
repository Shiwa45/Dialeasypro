// Outcomes come in two groups (answered / not answered). The app filters the
// post-call list by group, so every outcome must land in the right one —
// including from an older server, or a list cached before this version.

import 'package:flutter_test/flutter_test.dart';

import 'package:dialeasypro/data/models/models.dart';

void main() {
  test('the group comes from the server', () {
    final d = CallDisposition.fromJson({'id': 1, 'name': 'Busy', 'slug': 'busy', 'category': 'not_connected'});
    expect(d.isConnectedOutcome, isFalse);
  });

  test('an older server: marks_connected decides', () {
    expect(CallDisposition.fromJson({'id': 1, 'name': 'X', 'slug': 'x', 'marks_connected': true}).isConnectedOutcome, isTrue);
    expect(CallDisposition.fromJson({'id': 2, 'name': 'Y', 'slug': 'y', 'marks_connected': false}).isConnectedOutcome, isFalse);
  });

  test('a cached list with neither: the name decides', () {
    expect(CallDisposition.fromJson({'id': 1, 'name': 'Switched Off', 'slug': 'switched_off'}).isConnectedOutcome, isFalse);
    expect(CallDisposition.fromJson({'id': 2, 'name': 'Not Reachable', 'slug': 'not_reachable'}).isConnectedOutcome, isFalse);
    expect(CallDisposition.fromJson({'id': 3, 'name': 'Connected – Interested', 'slug': 'connected_interested'}).isConnectedOutcome, isTrue);
  });

  test('an outcome says what it does to the lead', () {
    final d = CallDisposition.fromJson({
      'id': 1, 'name': 'Interested', 'slug': 'interested', 'category': 'connected',
      'lead_status': 'interested', 'auto_followup_hours': 24,
    });
    expect(d.effectLine, 'Lead → Interested · follow-up in 24 h');
  });

  test('a call saved without an outcome needs one', () {
    final c = CallLog.fromJson({'id': 'a', 'direction': 'outbound', 'phone_number': '+919812300001',
      'started_at': '2026-10-08T10:00:00Z', 'disposition': null});
    expect(c.needsOutcome, isTrue);
  });

  test('a lead carries what its calls came to', () {
    final l = Lead.fromJson({'id': 1, 'name': 'Ravi', 'phone': '+919812300001', 'status': 'contacted',
      'dial_attempts': 3, 'connected_calls': 1, 'last_call_connected': true,
      'last_disposition_name': 'Language barrier'});
    expect(l.dialAttempts, 3);
    expect(l.connectedCalls, 1);
    expect(l.lastCallConnected, isTrue);
    expect(l.lastDispositionName, 'Language barrier');
  });
}
