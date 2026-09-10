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

import '../../data/models/models.dart';
import '../../data/services/services.dart';

class NotificationService {
  NotificationService._();
  static final instance = NotificationService._();

  final FlutterLocalNotificationsPlugin _plugin = FlutterLocalNotificationsPlugin();
  bool _ready = false;

  /// Set when a notification is tapped, so the app can route once it is up.
  final StreamController<String> onOpenRoute = StreamController<String>.broadcast();

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
        if (route != null && route.isNotEmpty) onOpenRoute.add(route);
      },
    );

    // Android 13+ will not show anything until the user grants this.
    final android13 = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    await android13?.requestNotificationsPermission();

    _ready = true;
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

    try {
      await _plugin.zonedSchedule(
        id,
        title,
        body,
        at,
        const NotificationDetails(android: _followupChannel),
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        uiLocalNotificationDateInterpretation:
            UILocalNotificationDateInterpretation.absoluteTime,
        payload: route,
      );
      return true;
    } catch (e) {
      // Exact-alarm permission can be refused on Android 12+. Log rather than
      // throw: a missing reminder must not take down the sync that asked for
      // it, and the in-app list still carries the follow-up.
      debugPrint('[Notifications] could not schedule $id: $e');
      return false;
    }
  }

  Future<void> cancel(int id) async {
    await init();
    await _plugin.cancel(id);
  }

  Future<void> cancelAll() async {
    await init();
    await _plugin.cancelAll();
  }

  /// Reconcile the OS alarm list with the agent's real follow-ups.
  ///
  /// Cancels everything previously scheduled and re-registers from the
  /// server's answer, which is the only way to drop reminders for follow-ups
  /// that were completed or rescheduled on another device.
  ///
  /// Returns how many reminders are now armed.
  Future<int> syncFollowupReminders() async {
    await init();

    List<FollowUp> upcoming;
    try {
      upcoming = await NotificationsService.instance.myUpcomingFollowups();
    } catch (e) {
      // Offline, or the endpoint is unreachable. Leave the alarms already
      // registered with Android alone — stale reminders beat none.
      debugPrint('[Notifications] follow-up sync failed: $e');
      return -1;
    }

    await _plugin.cancelAll();

    var armed = 0;
    for (final fu in upcoming) {
      // The follow-up id is the notification id, so re-syncing replaces
      // rather than duplicates.
      final ok = await scheduleAt(
        id: fu.id,
        when: fu.scheduledAtLocal,
        title: 'Follow up with ${fu.leadName ?? 'your lead'}',
        body: fu.notes.isNotEmpty ? fu.notes : 'Scheduled follow-up is due now.',
        route: '/leads/${fu.leadId}',
      );
      if (ok) armed++;
    }
    debugPrint('[Notifications] armed $armed reminder(s)');
    return armed;
  }
}
