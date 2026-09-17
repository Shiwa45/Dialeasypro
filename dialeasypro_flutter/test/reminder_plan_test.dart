// Which Android reminders get raised for a follow-up, and when.
//
// Notifications cannot be observed from a unit test; the decision about which
// ones to raise can. These pin that decision down, including the two cases
// the previous scheduler got wrong for overdue follow-ups:
//
//   * an already-overdue follow-up fired nothing until the next hourly step,
//     up to 59 minutes away;
//   * one more than eight hours overdue had every occurrence in the past, so
//     nothing was ever armed.
import 'package:flutter_test/flutter_test.dart';

import 'package:dialeasypro/core/services/reminder_plan.dart';

final _now = DateTime(2026, 9, 13, 14, 0);

ReminderFollowUp _fu({
  int id = 42,
  required Duration dueFromNow,
  String name = 'Ravi Kumar',
  String notes = '',
}) =>
    ReminderFollowUp(
      id: id,
      leadId: 7,
      leadName: name,
      notes: notes,
      due: _now.add(dueFromNow),
    );

void main() {
  group('a follow-up not yet due', () {
    test('gets its reminder at exactly the due time', () {
      final plan = planReminders([_fu(dueFromNow: const Duration(hours: 2))], now: _now);

      final first = plan.scheduled.first;
      expect(first.at, _now.add(const Duration(hours: 2)));
      expect(first.title, contains('Ravi Kumar'));
    });

    test('raises nothing immediately', () {
      final plan = planReminders([_fu(dueFromNow: const Duration(hours: 2))], now: _now);

      expect(plan.immediate, isEmpty);
    });

    test('is chased hourly after it falls due', () {
      final plan = planReminders([_fu(dueFromNow: const Duration(hours: 2))], now: _now);

      final times = plan.scheduled.map((r) => r.at).toList();
      expect(times[1], _now.add(const Duration(hours: 3)));
      expect(times[2], _now.add(const Duration(hours: 4)));
    });
  });

  group('an overdue follow-up', () {
    test('rings immediately — the case that was silent', () {
      final plan = planReminders(
        [_fu(dueFromNow: const Duration(minutes: -20))],
        now: _now,
      );

      expect(plan.immediate, hasLength(1));
      expect(plan.immediate.single.title, startsWith('Overdue'));
    });

    test('says how late it is', () {
      final plan = planReminders(
        [_fu(dueFromNow: const Duration(hours: -3, minutes: -15))],
        now: _now,
      );

      expect(plan.immediate.single.body, contains('3h 15m'));
    });

    test('keeps being chased when far more than eight hours late', () {
      // Nine hours late: the old scheduler armed zero reminders here.
      final plan = planReminders(
        [_fu(dueFromNow: const Duration(hours: -9))],
        now: _now,
      );

      expect(plan.scheduled, isNotEmpty,
          reason: 'a follow-up nine hours late must still be chased');
      for (final r in plan.scheduled) {
        expect(r.at!.isAfter(_now), isTrue, reason: 'never arm a time in the past');
      }
    });

    test('the next chase lands within the hour', () {
      final plan = planReminders(
        [_fu(dueFromNow: const Duration(hours: -3, minutes: -15))],
        now: _now,
      );

      final next = plan.scheduled.map((r) => r.at!).reduce((a, b) => a.isBefore(b) ? a : b);
      expect(next.difference(_now), lessThanOrEqualTo(const Duration(hours: 1)));
      expect(next.isAfter(_now), isTrue);
    });

    test('chases stay on the due time\'s hourly grid across re-syncs', () {
      // Sync runs on every app resume. Anchoring to "now" would push the
      // next chase back each time — open the app every ten minutes and it
      // would never ring. The same alarm must come out at the same time.
      final fu = _fu(dueFromNow: const Duration(hours: -3, minutes: -15));

      final early = planReminders([fu], now: _now);
      final later = planReminders([fu], now: _now.add(const Duration(minutes: 10)));

      final a = {for (final r in early.scheduled) r.id: r.at};
      final b = {for (final r in later.scheduled) r.id: r.at};
      for (final id in a.keys.where(b.containsKey)) {
        expect(b[id], a[id], reason: 'occurrence $id drifted between syncs');
      }
    });

    test('stops after three days, matching the server', () {
      final plan = planReminders(
        [_fu(dueFromNow: const Duration(hours: -80))],
        now: _now,
      );

      expect(plan.reminders, isEmpty);
    });

    test('never chases past the three-day window', () {
      final fu = _fu(dueFromNow: const Duration(hours: -70));
      final plan = planReminders([fu], now: _now);

      for (final r in plan.scheduled) {
        expect(r.at!.difference(fu.due), lessThanOrEqualTo(overdueChaseWindow));
      }
    });
  });

  group('the immediate alert fires once, not on every sync', () {
    test('an announced follow-up does not ring again', () {
      final fu = _fu(dueFromNow: const Duration(hours: -2));

      final first = planReminders([fu], now: _now);
      expect(first.immediate, hasLength(1));
      expect(first.announced, contains(fu.id));

      final second = planReminders([fu], now: _now, alreadyAnnounced: first.announced);
      expect(second.immediate, isEmpty, reason: 'sync runs on every resume');
      // It is still chased — only the "just found overdue" alert is suppressed.
      expect(second.scheduled, isNotEmpty);
    });

    test('a completed follow-up is forgotten, so it alerts afresh if it lapses again', () {
      final fu = _fu(dueFromNow: const Duration(hours: -2));

      final announced = planReminders([fu], now: _now).announced;
      // Completed: no longer returned by the server.
      final afterDone = planReminders([], now: _now, alreadyAnnounced: announced);

      expect(afterDone.announced, isNot(contains(fu.id)));
    });
  });

  group('ids', () {
    test('every reminder in a plan has a distinct id', () {
      final plan = planReminders([
        _fu(id: 1, dueFromNow: const Duration(hours: -5)),
        _fu(id: 2, dueFromNow: const Duration(hours: 3)),
        _fu(id: 3, dueFromNow: const Duration(minutes: -10)),
      ], now: _now);

      final ids = plan.reminders.map((r) => r.id).toList();
      expect(ids.toSet(), hasLength(ids.length),
          reason: 'a shared id would make one alarm cancel another');
    });

    test('the immediate alert never collides with an hourly chase', () {
      // 72h window means hourly steps run up to 72; the alert uses slot 99.
      final fu = _fu(dueFromNow: const Duration(hours: -71));
      final plan = planReminders([fu], now: _now);

      final alert = plan.immediate.single.id;
      expect(plan.scheduled.map((r) => r.id), isNot(contains(alert)));
    });

    test('ids fit a 32-bit int for any plausible follow-up id', () {
      final plan = planReminders(
        [_fu(id: 987654321, dueFromNow: const Duration(hours: 1))],
        now: _now,
      );

      for (final r in plan.reminders) {
        expect(r.id, lessThanOrEqualTo(2147483647));
        expect(r.id, greaterThanOrEqualTo(0));
      }
    });
  });

  test('a lead with no name still produces a readable title', () {
    final plan = planReminders(
      [_fu(name: '', dueFromNow: const Duration(minutes: -5))],
      now: _now,
    );

    expect(plan.immediate.single.title, contains('your lead'));
  });
}
