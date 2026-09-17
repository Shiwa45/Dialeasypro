// ============================================================
// DialEasypro — Which reminders to raise, and when
//
// Pure: no plugin, no clock of its own, no storage. It takes the follow-ups,
// the time, and what has already been announced, and returns a plan. That is
// what makes it testable — Android notifications cannot be observed from a
// unit test, but the decision about which ones to raise can be.
//
// It exists because the previous version got overdue follow-ups wrong in
// exactly the case that matters:
//
//   * An already-overdue follow-up never fired immediately. Its reminder sat
//     at the due time, which was in the past and so skipped. The first thing
//     that could ring was the next hourly chase, up to 59 minutes away.
//
//   * Chases were anchored to the due time and capped at eight. A follow-up
//     nine hours overdue had every occurrence in the past, so nothing was
//     armed — ever.
//
// And the phone is the only thing that rings. The server's chaser writes an
// in-app notification and pushes over a socket, but push is not configured, so
// an Android notification exists only if this plan armed one.
// ============================================================

/// How long an overdue follow-up keeps being chased. Matches the server's
/// OVERDUE_CHASE_HOURS so the phone and the bell stop at the same point.
const Duration overdueChaseWindow = Duration(hours: 72);

/// How many future chases are armed at once. The plan is rebuilt on every
/// sync, so this only has to cover the gap until the app is next opened.
const int chasesAhead = 8;

/// Reserved occurrence slot for the "you have just been found overdue" alert,
/// kept clear of the hourly steps (which run 0..80) so the two never share an
/// id and cancel each other.
const int immediateSlot = 99;

class ReminderFollowUp {
  final int id;
  final int leadId;
  final String leadName;
  final String notes;
  final DateTime due;

  const ReminderFollowUp({
    required this.id,
    required this.leadId,
    required this.leadName,
    required this.notes,
    required this.due,
  });
}

class PlannedReminder {
  final int id;
  final DateTime? at; // null means "show now"
  final String title;
  final String body;
  final String route;

  const PlannedReminder({
    required this.id,
    required this.at,
    required this.title,
    required this.body,
    required this.route,
  });

  bool get immediate => at == null;

  @override
  String toString() => 'PlannedReminder($id, ${at ?? 'now'}, $title)';
}

class ReminderPlan {
  final List<PlannedReminder> reminders;

  /// Follow-up ids that are overdue as of this plan and have been announced.
  /// Persisted, so the immediate alert is raised once per follow-up rather
  /// than on every sync — sync runs on every app resume.
  final Set<int> announced;

  const ReminderPlan(this.reminders, this.announced);

  Iterable<PlannedReminder> get immediate => reminders.where((r) => r.immediate);
  Iterable<PlannedReminder> get scheduled => reminders.where((r) => !r.immediate);
}

/// Notification ids are Java ints. Two trailing digits per follow-up give
/// each occurrence its own stable id, so re-planning replaces an alarm rather
/// than stacking another; the modulo keeps it inside 32 bits.
int occurrenceId(int followupId, int slot) => (followupId % 21000000) * 100 + slot;

ReminderPlan planReminders(
  List<ReminderFollowUp> followUps, {
  required DateTime now,
  Set<int> alreadyAnnounced = const {},
}) {
  final out = <PlannedReminder>[];
  final stillOverdue = <int>{};

  for (final fu in followUps) {
    final route = '/leads/${fu.leadId}';
    final who = fu.leadName.isEmpty ? 'your lead' : fu.leadName;
    final extra = fu.notes.isEmpty ? '' : ' ${fu.notes}';

    if (fu.due.isAfter(now)) {
      // ---- Not due yet: the reminder, then chases after it -------------
      out.add(PlannedReminder(
        id: occurrenceId(fu.id, 0),
        at: fu.due,
        title: 'Follow up with $who',
        body: fu.notes.isEmpty ? 'This follow-up is due now.' : fu.notes,
        route: route,
      ));
      for (var k = 1; k <= chasesAhead; k++) {
        out.add(PlannedReminder(
          id: occurrenceId(fu.id, k),
          at: fu.due.add(Duration(hours: k)),
          title: 'Still waiting: $who',
          body: 'Overdue by ${k}h.$extra',
          route: route,
        ));
      }
      continue;
    }

    // ---- Already overdue ---------------------------------------------
    final late = now.difference(fu.due);
    if (late > overdueChaseWindow) {
      // Past the window it needs a person, not another notification.
      continue;
    }
    stillOverdue.add(fu.id);

    // Ring now, once. Without this an agent opening the app to an overdue
    // follow-up saw nothing until the next hourly step came round.
    if (!alreadyAnnounced.contains(fu.id)) {
      out.add(PlannedReminder(
        id: occurrenceId(fu.id, immediateSlot),
        at: null,
        title: 'Overdue: follow up with $who',
        body: 'Was due ${_ago(late)} ago.$extra',
        route: route,
      ));
    }

    // Chase on the hourly grid that the due time sets, starting from the
    // first step after now. Anchoring to the due time rather than to "now"
    // keeps the phase stable: sync runs on every resume, and re-anchoring to
    // now would push the next chase back by however long the agent had been
    // away — open the app every ten minutes and it would never ring at all.
    final firstStep = (late.inMinutes ~/ 60) + 1;
    for (var k = firstStep; k < firstStep + chasesAhead; k++) {
      final at = fu.due.add(Duration(hours: k));
      if (at.difference(fu.due) > overdueChaseWindow) break;
      out.add(PlannedReminder(
        id: occurrenceId(fu.id, k),
        at: at,
        title: 'Still waiting: $who',
        body: 'Overdue by ${k}h.$extra',
        route: route,
      ));
    }
  }

  // Announced-ness is kept only for follow-ups still overdue, so a completed
  // or rescheduled one drops out and alerts afresh if it lapses again. It is
  // resolved from the source list rather than by dividing the notification
  // id, because occurrenceId folds the id through a modulo.
  final resolved = <int>{
    for (final fu in followUps)
      if (stillOverdue.contains(fu.id) &&
          (alreadyAnnounced.contains(fu.id) ||
              out.any((r) => r.immediate && r.id == occurrenceId(fu.id, immediateSlot))))
        fu.id,
  };

  return ReminderPlan(out, resolved);
}

String _ago(Duration d) {
  if (d.inHours >= 1) {
    final h = d.inHours;
    final m = d.inMinutes % 60;
    return m == 0 ? '${h}h' : '${h}h ${m}m';
  }
  return '${d.inMinutes.clamp(1, 59)}m';
}
