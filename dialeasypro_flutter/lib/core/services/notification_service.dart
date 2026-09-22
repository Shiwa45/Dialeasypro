// ============================================================
// DialEasypro — Notifications on the phone
//
// pubspec has carried flutter_local_notifications and timezone since the
// project started and nothing ever imported them. An agent whose lead had a
// follow-up scheduled was told nothing, on any device.
//
// This does two separate jobs, and the split matters:
//
//   * SCHEDULED REMINDERS are handed to Android itself. When the app syncs
//     the agent's upcoming follow-ups, it asks the OS to raise a notification
//     at each one's time. Android then fires it whether or not the app is
//     running, whether or not there is a network, and whether or not the
//     server is up. This is the reliable half and it needs no push
//     credentials of any kind.
//
//   * ARRIVALS — someone else scheduling a follow-up on your lead — come from
//     the server. Those are shown when the app is open and listed in the
//     notification screen. Reaching a phone that has not opened the app since
//     needs FCM, which is not configured; see apps/authentication/push.py.
// ============================================================
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest_all.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

import 'package:shared_preferences/shared_preferences.dart';

import '../../data/models/models.dart';
import '../../data/services/services.dart';
import 'reminder_plan.dart';
import 'server_alert_plan.dart';

class NotificationService {
  NotificationService._();
  static final instance = NotificationService._();

  final FlutterLocalNotificationsPlugin _plugin = FlutterLocalNotificationsPlugin();
  bool _ready = false;

  /// Routes emitted when a notification is tapped, so the app can navigate
  /// once it is up. The controller stays private — exposing it let callers
  /// add events to a stream that only Android should be writing to, and it
  /// has no `listen` of its own, which is the bug that surfaced first.
  final StreamController<String> _openRoute = StreamController<String>.broadcast();
  Stream<String> get onOpenRoute => _openRoute.stream;

  static const AndroidNotificationDetails _followupChannel =
      AndroidNotificationDetails(
    'followups',
    'Follow-up reminders',
    channelDescription: 'Reminders for follow-ups scheduled on your leads.',
    importance: Importance.high,
    priority: Priority.high,
    category: AndroidNotificationCategory.reminder,
  );

  Future<void> init() async {
    if (_ready) return;

    // Timezone data is required before anything can be scheduled at a wall
    // clock time; without it zonedSchedule throws at the first call.
    tzdata.initializeTimeZones();
    try {
      tz.setLocalLocation(tz.getLocation('Asia/Kolkata'));
    } catch (_) {
      // Fall back to UTC rather than failing to initialise at all.
    }

    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const settings = InitializationSettings(android: android);

    await _plugin.initialize(
      settings,
      onDidReceiveNotificationResponse: (response) {
        final route = response.payload;
        if (route != null && route.isNotEmpty) _openRoute.add(route);
      },
    );

    _ready = true;
  }

  /// Ask for the two permissions notifications need.
  ///
  /// Kept OUT of init() on purpose. Both of these show system UI and wait for
  /// a person, and requestExactAlarmsPermission opens Android's "Alarms &
  /// reminders" settings screen, completing only when the user navigates
  /// back. Awaiting that before runApp left the app on a black screen,
  /// blocked on a prompt behind a UI that had not been drawn.
  ///
  /// Call it once there is something on screen: the setup wizard on first
  /// run, or just after login.
  Future<void> requestPermissions() async {
    await init();

    // Named `impl`, not `android`: `android` is the
    // AndroidInitializationSettings inside init(), and shadowing it sent
    // these calls at the wrong object.
    final impl = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();

    // Android 13+ shows nothing at all until this is granted.
    try {
      await impl?.requestNotificationsPermission();
    } catch (e) {
      debugPrint('[Notifications] notification permission unavailable: $e');
    }

    // A reminder is only on time if it is an exact alarm. Without this,
    // Android batches it with whatever else it feels like waking for, which
    // under Doze can be an hour late — on the one notification whose entire
    // value is arriving at the right minute.
    //
    // Android 13+ grants it from the USE_EXACT_ALARM manifest entry. On 12 it
    // is user-revocable, which is what this prompt is for.
    try {
      await impl?.requestExactAlarmsPermission();
    } catch (e) {
      debugPrint('[Notifications] exact alarm permission unavailable: $e');
    }
  }

  /// Show something now. Used when a notification arrives while the app runs.
  Future<void> show({
    required int id,
    required String title,
    required String body,
    String route = '',
  }) async {
    await init();
    await _plugin.show(
      id,
      title,
      body,
      const NotificationDetails(android: _followupChannel),
      payload: route,
    );
  }

  /// Ask Android to raise a reminder at [when].
  ///
  /// A time already past is skipped rather than fired immediately — an agent
  /// opening the app in the evening should not get a burst of notifications
  /// for everything they did that day.
  Future<bool> scheduleAt({
    required int id,
    required DateTime when,
    required String title,
    required String body,
    String route = '',
  }) async {
    await init();
    final at = tz.TZDateTime.from(when, tz.local);
    if (!at.isAfter(tz.TZDateTime.now(tz.local))) return false;

    // Exact first. A follow-up reminder that arrives whenever Android next
    // feels like waking up is not a reminder.
    for (final mode in const [
      AndroidScheduleMode.exactAllowWhileIdle,
      AndroidScheduleMode.inexactAllowWhileIdle,
    ]) {
      try {
        await _plugin.zonedSchedule(
          id,
          title,
          body,
          at,
          const NotificationDetails(android: _followupChannel),
          androidScheduleMode: mode,
          uiLocalNotificationDateInterpretation:
              UILocalNotificationDateInterpretation.absoluteTime,
          payload: route,
        );
        return true;
      } catch (e) {
        // Exact alarms can be refused on Android 12+. Falling back to inexact
        // means the reminder is late rather than absent, which is the right
        // trade — the previous version gave up here and lost it entirely.
        debugPrint('[Notifications] $mode failed for $id: $e');
      }
    }
    return false;
  }

  Future<void> cancel(int id) async {
    await init();
    await _plugin.cancel(id);
  }

  Future<void> cancelAll() async {
    await init();
    await _plugin.cancelAll();
  }

  static const _announcedKey = 'reminders.overdue_announced';

  /// Reconcile the OS alarm list with the agent's real follow-ups.
  ///
  /// Which reminders to raise is decided by planReminders (reminder_plan.dart),
  /// which is pure and unit-tested. This method only fetches, persists, and
  /// hands the plan to Android.
  ///
  /// The previous version decided inline and got overdue follow-ups wrong:
  /// nothing rang immediately for one already late, and one more than eight
  /// hours late had every occurrence in the past, so nothing was armed at all.
  /// The phone is the only thing that produces an Android notification here —
  /// the server chaser writes an in-app row, and push is not configured — so
  /// those gaps meant an agent simply was not told.
  ///
  /// Returns how many reminders are now armed, or -1 if the fetch failed.
  Future<int> syncFollowupReminders() async {
    await init();

    List<FollowUp> fetched;
    try {
      fetched = await NotificationsService.instance.myUpcomingFollowups();
    } catch (e) {
      // Offline, or the endpoint is unreachable. Leave the alarms already
      // registered with Android alone — stale reminders beat none.
      debugPrint('[Notifications] follow-up sync failed: $e');
      return -1;
    }

    final prefs = await SharedPreferences.getInstance();
    final previously = (prefs.getStringList(_announcedKey) ?? const [])
        .map(int.tryParse)
        .whereType<int>()
        .toSet();

    final plan = planReminders(
      [
        for (final fu in fetched)
          ReminderFollowUp(
            id: fu.id,
            leadId: fu.leadId,
            leadName: fu.leadName ?? '',
            notes: fu.notes,
            due: fu.scheduledAtLocal,
          ),
      ],
      now: DateTime.now(),
      alreadyAnnounced: previously,
    );

    // Clear only the alarms still waiting to fire, not the whole shade.
    // cancelAll() also dismisses notifications Android has already DELIVERED,
    // so a sync on resume wiped the overdue alert and every server alert the
    // agent had not read yet — the app quietly tidying away its own messages.
    await _cancelPendingReminders();

    // Ring the newly-overdue ones now. show() rather than a scheduled alarm:
    // a zonedSchedule for "now" can be dropped as already past.
    for (final r in plan.immediate) {
      try {
        await show(id: r.id, title: r.title, body: r.body, route: r.route);
      } catch (e) {
        debugPrint('[Notifications] could not show ${r.id}: $e');
      }
    }

    var armed = 0;
    for (final r in plan.scheduled) {
      final ok = await scheduleAt(
        id: r.id, when: r.at!, title: r.title, body: r.body, route: r.route,
      );
      if (ok) armed++;
    }

    // Persist only after the alerts went out, so a crash mid-sync re-alerts
    // on the next one rather than silently marking them as told.
    await prefs.setStringList(
      _announcedKey,
      [for (final id in plan.announced) id.toString()],
    );

    debugPrint('[Notifications] ${plan.immediate.length} overdue alert(s) now, '
        '$armed reminder(s) armed across ${fetched.length} follow-up(s)');
    return armed;
  }

  /// Drop the alarms that have not fired yet, leaving delivered ones alone.
  ///
  /// Reminder ids are non-negative (reminder_plan.occurrenceId); ids raised
  /// for server notifications are negative, so this cannot cancel those.
  Future<void> _cancelPendingReminders() async {
    try {
      for (final p in await _plugin.pendingNotificationRequests()) {
        if (p.id >= 0) await _plugin.cancel(p.id);
      }
    } catch (e) {
      debugPrint('[Notifications] could not list pending reminders: $e');
    }
  }

  // ---- Notifications the SERVER raised -------------------------------

  static const _serverAnnouncedKey = 'notifications.server_announced';

  /// Put anything the server has raised for this agent into the Android
  /// notification shade.
  ///
  /// The server writes a Notification row when someone schedules a follow-up
  /// on your lead, when one falls due and hourly while one stays overdue. The
  /// app fetched those rows for the bell and the notifications screen and
  /// stopped there, so they appeared INSIDE the app and nowhere else: an
  /// agent not already looking at the app was told nothing. Local reminders
  /// covered only what the phone had synced, and only at the scheduled time.
  ///
  /// Push (FCM) is still not configured — see apps/authentication/push.py —
  /// so this reaches the shade while the app is running. The scheduled alarms
  /// remain the path that works with the app closed.
  ///
  /// [silent] records what is already unread as told without showing any of
  /// it. Used at login: that backlog is history the agent is about to see in
  /// the app anyway, and a stack of it in the shade a minute after signing in
  /// is noise, not news.
  ///
  /// Returns how many alerts were raised, or -1 if the fetch failed.
  Future<int> syncServerNotifications({bool silent = false}) async {
    await init();

    List<AppNotification> unread;
    try {
      // Cheap first: the common answer is "nothing new", and that costs one
      // small request rather than a page of rows.
      if (await NotificationsService.instance.unreadCount() == 0) return 0;
      unread = await NotificationsService.instance.list(unreadOnly: true, pageSize: 30);
    } catch (e) {
      debugPrint('[Notifications] server notification sync failed: $e');
      return -1;
    }

    final prefs = await SharedPreferences.getInstance();
    final previously = (prefs.getStringList(_serverAnnouncedKey) ?? const [])
        .map(int.tryParse)
        .whereType<int>()
        .toSet();

    // What to raise is decided by planServerAlerts (server_alert_plan.dart),
    // which is pure and unit-tested. This method only fetches, shows and
    // persists.
    final plan = planServerAlerts(
      unread,
      alreadyAnnounced: previously,
      now: DateTime.now(),
      silent: silent,
    );

    var shown = 0;
    for (final alert in plan.show) {
      try {
        await show(id: alert.id, title: alert.title, body: alert.body, route: alert.route);
        shown++;
      } catch (e) {
        debugPrint('[Notifications] could not show server alert ${alert.id}: $e');
      }
    }

    await prefs.setStringList(
      _serverAnnouncedKey,
      [for (final id in boundAnnounced(plan.announced)) '$id'],
    );

    if (shown > 0) debugPrint('[Notifications] raised $shown server alert(s)');
    return shown;
  }

  /// Forget which overdue follow-ups were announced. For logout, so the next
  /// agent on this handset is alerted about their own rather than inheriting
  /// the previous agent's "already told" state.
  Future<void> clearAnnounced() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_announcedKey);
    await prefs.remove(_serverAnnouncedKey);
  }
}
