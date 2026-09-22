// Which server notifications reach the Android shade.
//
// The symptom this fixes: an agent could see a follow-up notification in the
// app's notification list while the Android notification panel stayed empty.
// The rows were fetched for the bell and never handed to Android, so the only
// people who found out were the ones already looking at the app.
//
// The rules that matter here are the ones that go wrong quietly: re-alerting
// a row that is still unread (it stays unread until it is opened, and the app
// polls every minute), burying the agent under a backlog, and colliding with
// a scheduled reminder's notification id.
import 'package:flutter_test/flutter_test.dart';

import 'package:dialeasypro/core/services/reminder_plan.dart';
import 'package:dialeasypro/core/services/server_alert_plan.dart';
import 'package:dialeasypro/data/models/models.dart';

final _now = DateTime(2026, 9, 22, 15, 30);

AppNotification _n(
  int id, {
  String title = 'Follow-up scheduled',
  String body = 'Ravi Kumar at 4:00 PM',
  String url = '/leads/54',
  DateTime? at,
}) =>
    AppNotification.fromJson({
      'id': id,
      'kind': 'followup_scheduled',
      'title': title,
      'body': body,
      'url': url,
      'is_read': false,
      'created_at': (at ?? _now.subtract(const Duration(minutes: 1))).toIso8601String(),
    });

ServerAlertPlan _plan(
  List<AppNotification> unread, {
  Set<int> announced = const {},
  bool silent = false,
}) =>
    planServerAlerts(unread, alreadyAnnounced: announced, now: _now, silent: silent);

void main() {
  group('what reaches the shade', () {
    test('a new notification is raised', () {
      final plan = _plan([_n(7)]);

      expect(plan.show, hasLength(1));
      expect(plan.show.single.title, 'Follow-up scheduled');
      expect(plan.show.single.body, 'Ravi Kumar at 4:00 PM');
      expect(plan.show.single.route, '/leads/54',
          reason: 'tapping it should open the lead it is about');
    });

    test('one already told about is not raised again', () {
      // The row stays unread until the agent opens it, and the app asks once
      // a minute. Without this the same notification would fire all day.
      final plan = _plan([_n(7)], announced: {7});

      expect(plan.show, isEmpty);
    });

    test('it is recorded as told, so the next poll stays quiet', () {
      final plan = _plan([_n(7)]);

      expect(plan.announced, contains(7));
      expect(_plan([_n(7)], announced: plan.announced).show, isEmpty);
    });

    test('yesterday is not worth interrupting anyone for', () {
      final plan = _plan([_n(7, at: _now.subtract(const Duration(hours: 30)))]);

      expect(plan.show, isEmpty);
      expect(plan.announced, contains(7),
          reason: 'and it must not surface later as if it were new');
    });

    test('a row on the edge of a day old still counts as news', () {
      final plan = _plan([_n(7, at: _now.subtract(const Duration(hours: 23)))]);

      expect(plan.show, hasLength(1));
    });

    test('a notification with no timestamp is still shown', () {
      // Better a notification whose age is unknown than silence.
      final plan = planServerAlerts(
        [AppNotification.fromJson({'id': 7, 'title': 'Overdue', 'created_at': ''})],
        alreadyAnnounced: const {},
        now: _now,
      );

      expect(plan.show, hasLength(1));
    });

    test('a blank title falls back to the app name', () {
      final plan = _plan([_n(7, title: '   ')]);

      expect(plan.show.single.title, 'DialEasypro',
          reason: 'an empty row in the shade reads as a bug');
    });
  });

  group('a backlog', () {
    List<AppNotification> many(int count) => [
          for (var i = 1; i <= count; i++)
            _n(i, at: _now.subtract(Duration(minutes: count - i))),
        ];

    test('is capped so the shade is not flooded', () {
      final plan = _plan(many(12));

      expect(plan.show, hasLength(maxAlertsPerSync));
    });

    test('shows the newest, not whatever came first in the page', () {
      final plan = _plan(many(12));

      // many() makes id 12 the most recent.
      expect(plan.show.first.id, serverSlot(12));
    });

    test('marks the whole backlog as told, so the rest never arrive later', () {
      final plan = _plan(many(12));

      expect(plan.announced, hasLength(12));
      expect(_plan(many(12), announced: plan.announced).show, isEmpty);
    });
  });

  group('signing in', () {
    test('records the existing backlog without showing any of it', () {
      final plan = _plan([_n(7), _n(8)], silent: true);

      expect(plan.show, isEmpty, reason: 'the agent is looking at the app right now');
      expect(plan.announced, containsAll([7, 8]));
    });

    test('and what arrives next is still raised', () {
      final atLogin = _plan([_n(7)], silent: true);

      final later = _plan([_n(7), _n(9)], announced: atLogin.announced);

      expect(later.show, hasLength(1));
      expect(later.show.single.id, serverSlot(9));
    });
  });

  group('notification ids', () {
    test('never collide with a scheduled reminder', () {
      // Reminder ids are non-negative; a collision would mean a reminder and
      // a server alert replacing one another in the shade.
      for (final id in [1, 7, 4321, 2147483647]) {
        expect(serverSlot(id), isNegative);
      }
      expect(occurrenceId(54, 0), isNonNegative);
      expect(occurrenceId(54, immediateSlot), isNonNegative);
    });

    test('are stable for the same notification', () {
      expect(serverSlot(42), serverSlot(42));
    });

    test('differ between notifications', () {
      expect(serverSlot(42), isNot(serverSlot(43)));
    });
  });

  group('the told-set', () {
    test('is bounded, keeping the most recent ids', () {
      final ids = {for (var i = 1; i <= 400; i++) i};

      final kept = boundAnnounced(ids);

      expect(kept, hasLength(300));
      expect(kept.last, 400);
      expect(kept.first, 101);
    });

    test('is left alone while it is small', () {
      expect(boundAnnounced({3, 1, 2}), [1, 2, 3]);
    });
  });
}
