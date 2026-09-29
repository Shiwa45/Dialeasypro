import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/services/presence_service.dart';
import '../dialer/dialer_state.dart';

// ============================================================
// DialEasypro — Work session
//
// An agent signed in to the app is AT WORK: live on the admin's Live Agents
// board, available, with idle time running from the moment they land on the
// auto-dialer. Everything else in the app — leads, manual dialling, WhatsApp,
// reports — is behind a break: the agent takes one to step away from
// auto-dialling, and ending it brings them straight back.
//
// Presence used to exist only while an auto-dial queue was running, so an
// agent who had opened the app showed as offline until they started one, and
// went offline again the moment it ended.
// ============================================================

class WorkSessionState {
  final bool live;
  final bool onBreak;
  final String breakReason;

  /// When the current state (available or break) began — drives the idle /
  /// break timer on the Auto Dial screen.
  final DateTime since;

  const WorkSessionState({
    required this.live,
    required this.onBreak,
    required this.since,
    this.breakReason = '',
  });

  factory WorkSessionState.offline() =>
      WorkSessionState(live: false, onBreak: false, since: DateTime.now());
}

class WorkSessionNotifier extends StateNotifier<WorkSessionState> {
  WorkSessionNotifier(this._ref) : super(WorkSessionState.offline());

  final Ref _ref;

  static const _kOnBreak = 'work_on_break';
  static const _kBreakReason = 'work_break_reason';

  /// Go live. Called when the signed-in app shell opens. A break that was
  /// running when the app was closed carries on, rather than silently turning
  /// into "available" on the admin's board.
  Future<void> start() async {
    if (state.live) return;
    final prefs = await SharedPreferences.getInstance();
    final wasOnBreak = prefs.getBool(_kOnBreak) ?? false;
    final reason = prefs.getString(_kBreakReason) ?? '';

    PresenceService.instance.startSession(); // available + heartbeat
    if (wasOnBreak) {
      unawaited(PresenceService.instance.report(AgentStatus.breakStatus, breakReason: reason));
    }
    state = WorkSessionState(
      live: true, onBreak: wasOnBreak, breakReason: reason, since: DateTime.now(),
    );
  }

  /// Step away from auto-dialling. Refused during a live call.
  Future<bool> takeBreak({String reason = ''}) async {
    if (!state.live || state.onBreak) return state.onBreak;
    final dialer = _ref.read(dialerProvider);
    if (dialer.phase == DialerPhase.inCall || dialer.phase == DialerPhase.dialing) {
      return false;
    }

    if (dialer.mode == DialerMode.queue) {
      // Pauses the queue and reports the break.
      await _ref.read(dialerProvider.notifier).goOnBreak(reason: reason);
    } else {
      unawaited(PresenceService.instance.report(AgentStatus.breakStatus, breakReason: reason));
    }
    await _persist(onBreak: true, reason: reason);
    state = WorkSessionState(live: true, onBreak: true, breakReason: reason, since: DateTime.now());
    return true;
  }

  /// Back to work: available again, and the app returns to Auto Dial.
  Future<void> endBreak() async {
    if (!state.onBreak) return;
    final dialer = _ref.read(dialerProvider);
    if (dialer.onBreak) {
      // Reports available; the queue stays paused until the agent resumes it.
      await _ref.read(dialerProvider.notifier).endBreak(autoResume: false);
    } else {
      unawaited(PresenceService.instance.report(AgentStatus.available));
    }
    await _persist(onBreak: false, reason: '');
    state = WorkSessionState(live: true, onBreak: false, since: DateTime.now());
  }

  /// The session is over (logout, or it expired): forget it locally so the
  /// next sign-in starts a fresh one. start() returns early while `live` is
  /// true, and nothing reset it — so after signing out and back in without
  /// closing the app, no "available" was reported and no heartbeat ran, and
  /// the agent showed offline all shift.
  void signedOut() {
    PresenceService.instance.stopQuietly();
    state = WorkSessionState.offline();
  }

  /// Signing out: offline on the board, heartbeat stopped.
  Future<void> end() async {
    PresenceService.instance.endSession();
    await _persist(onBreak: false, reason: '');
    state = WorkSessionState.offline();
  }

  Future<void> _persist({required bool onBreak, required String reason}) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_kOnBreak, onBreak);
    await prefs.setString(_kBreakReason, reason);
  }
}

final workSessionProvider =
    StateNotifierProvider<WorkSessionNotifier, WorkSessionState>((ref) => WorkSessionNotifier(ref));

/// Routes open while the agent is working (not on break). Everything else —
/// leads, manual dialling, WhatsApp, reports — needs a break first.
bool allowedWhileWorking(String location) {
  const open = ['/auto-dial', '/dialer', '/profile', '/notifications', '/setup', '/login', '/splash'];
  return open.any((p) => location == p || location.startsWith('$p/'));
}

/// Break reasons offered on the Auto Dial screen.
const breakReasons = ['Tea / short break', 'Lunch', 'Meeting', 'Manual calls & WhatsApp', 'Other'];
