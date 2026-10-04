import 'dart:async';
import '../../data/services/api_client.dart';

// ============================================================
// DialSathi — Presence Service
//
// Reports the agent's live work status to the backend for admin monitoring.
// Presence is tied to the auto-dial session: starting the dialer marks the
// agent online (available); leaving it marks them offline. Statuses cycle
// available → onCall → wrapUp during the session, with break as a manual
// toggle. A heartbeat keeps the session alive so a crash flips to offline.
//
// All calls are fire-and-forget — presence must never block the dialer.
// ============================================================

class AgentStatus {
  static const offline = 'offline';
  static const available = 'available';
  static const onCall = 'on_call';
  static const wrapUp = 'wrap_up';
  static const breakStatus = 'break';
}

class PresenceService {
  PresenceService._();
  static final PresenceService instance = PresenceService._();

  String _current = AgentStatus.offline;
  String _breakReason = '';
  Timer? _heartbeat;

  String get current => _current;
  bool get onBreak => _current == AgentStatus.breakStatus;
  String get breakReason => _breakReason;

  /// Report a status transition. No-op if unchanged (except offline, which we
  /// always send so the server clears the session promptly).
  Future<void> report(String status, {String? breakReason, int? leadId}) async {
    if (status == _current && status != AgentStatus.offline) return;
    _current = status;
    _breakReason = status == AgentStatus.breakStatus ? (breakReason ?? '') : '';
    try {
      await ApiClient.instance.dio.post('/auth/status/', data: {
        'status': status,
        if (breakReason != null) 'break_reason': breakReason,
        if (leadId != null) 'lead_id': leadId,
      });
    } catch (_) {
      // Ignore — monitoring is best-effort and must not disrupt calling.
    }
  }

  /// Begin a session: go available and start the heartbeat.
  void startSession() {
    report(AgentStatus.available);
    _startHeartbeat();
  }

  /// Stop without telling the server — for when the session is already gone
  /// (tokens cleared or expired). The heartbeat used to keep firing after a
  /// session expired: a 401, a refused refresh and another "session
  /// expired" every 25 seconds until the next login.
  void stopQuietly() {
    _stopHeartbeat();
    _current = AgentStatus.offline;
    _breakReason = '';
  }

  /// End the session: go offline and stop the heartbeat.
  void endSession() {
    _stopHeartbeat();
    report(AgentStatus.offline);
  }

  void _startHeartbeat() {
    _heartbeat?.cancel();
    _heartbeat = Timer.periodic(const Duration(seconds: 25), (_) => _beat());
  }

  /// The heartbeat says what this phone believes its status is. Android
  /// freezes the app during calls and on a locked screen, so the server may
  /// have swept the agent offline meanwhile; the status lets it put them
  /// back. (Only changes are reported, so nothing else would.) It also
  /// repairs a status change whose request was lost to a bad connection.
  Future<void> _beat() async {
    if (_heartbeat == null) return;
    try {
      await ApiClient.instance.dio.post('/auth/status/heartbeat/', data: {
        'status': _current,
        if (_breakReason.isNotEmpty) 'break_reason': _breakReason,
      });
    } catch (_) {}
  }

  /// Re-sync immediately — call when the app comes back to the foreground,
  /// which is exactly when a frozen session needs repairing.
  void resync() {
    if (_heartbeat != null) _beat();
  }

  void _stopHeartbeat() {
    _heartbeat?.cancel();
    _heartbeat = null;
  }
}
