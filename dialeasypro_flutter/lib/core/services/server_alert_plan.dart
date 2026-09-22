// ============================================================
// DialEasypro — Which server notifications reach the shade
//
// The server writes a Notification row when someone schedules a follow-up on
// your lead, when one falls due, and hourly while one stays overdue. The app
// read those rows for the bell and the notifications screen and stopped
// there: they appeared inside the app and nowhere else. An agent who was not
// already looking at the app was told nothing.
//
// This decides which of them Android should raise. Kept pure and separate
// from NotificationService for the same reason as reminder_plan.dart: the
// service can only be exercised with a live API and the notifications plugin
// attached, and the rules here are where the mistakes actually happen —
// re-alerting something already shown, burying the agent under a backlog, or
// colliding with a scheduled reminder's id.
// ============================================================
import '../../data/models/models.dart';

/// How many of a backlog to put on screen at once. The rest are still marked
/// as told, so they do not arrive later as a burst.
const int maxAlertsPerSync = 5;

/// Nothing older than this is worth interrupting someone for — it is already
/// in the in-app list, which is where history belongs.
const Duration serverAlertMaxAge = Duration(hours: 24);

/// An Android notification id for a server notification.
///
/// A negative space of its own. Reminder ids (reminder_plan.occurrenceId) are
/// non-negative, and an overlap would mean a follow-up reminder and a server
/// alert silently replacing one another in the shade.
int serverSlot(int notificationId) => -1 - (notificationId.abs() % 2000000000);

class ServerAlert {
  final int id;
  final String title, body, route;

  const ServerAlert({
    required this.id,
    required this.title,
    required this.body,
    required this.route,
  });
}

class ServerAlertPlan {
  /// What to show now, newest first.
  final List<ServerAlert> show;

  /// Every notification id now considered told — including the ones not
  /// shown, so they are never raised later out of their moment.
  final Set<int> announced;

  const ServerAlertPlan({required this.show, required this.announced});
}

/// Decide what to raise for [unread].
///
/// [alreadyAnnounced] is what previous syncs have told the agent about. A row
/// stays unread until it is opened, so without this every poll would re-raise
/// the same notification, once a minute, forever.
///
/// [silent] records everything as told without showing any of it. Used at
/// login, where the backlog is history the agent is about to see in the app.
ServerAlertPlan planServerAlerts(
  List<AppNotification> unread, {
  required Set<int> alreadyAnnounced,
  required DateTime now,
  bool silent = false,
}) {
  final announced = <int>{...alreadyAnnounced};

  final fresh = unread.where((n) => !alreadyAnnounced.contains(n.id)).toList()
    ..sort((a, b) {
      // Newest first, so a capped backlog shows the most recent rather than
      // whatever the page happened to start with.
      final at = a.createdAtLocal, bt = b.createdAtLocal;
      if (at == null || bt == null) return b.id.compareTo(a.id);
      return bt.compareTo(at);
    });

  final show = <ServerAlert>[];
  for (final n in fresh) {
    announced.add(n.id);

    if (silent || show.length >= maxAlertsPerSync) continue;

    final at = n.createdAtLocal;
    if (at != null && now.difference(at) > serverAlertMaxAge) continue;

    show.add(ServerAlert(
      id: serverSlot(n.id),
      // A notification with no title would render as a blank row in the
      // shade, which reads as a bug rather than a message.
      title: n.title.trim().isEmpty ? 'DialEasypro' : n.title,
      body: n.body,
      route: n.url,
    ));
  }

  return ServerAlertPlan(show: show, announced: announced);
}

/// Keep the told-set bounded: an id only matters until the row stops coming
/// back as unread, and an unbounded list in shared preferences grows for the
/// life of the install.
List<int> boundAnnounced(Set<int> announced, {int keep = 300}) {
  final sorted = announced.toList()..sort();
  return sorted.length > keep ? sorted.sublist(sorted.length - keep) : sorted;
}
