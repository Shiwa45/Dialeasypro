import 'dart:async';
import '../../data/services/api_client.dart';

// ============================================================
// DialEasypro — Presence Service
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
  Timer? _heartbeat;

  String get current => _current;

  /// Report a status transition. No-op if unchanged (except offline, which we
  /// always send so the server clears the session promptly).
  Future<void> report(String status, {String? breakReason, int? leadId}) async {
    if (status == _current && status != AgentStatus.offline) return;
    _current = status;
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

  /// End the session: go offline and stop the heartbeat.
  void endSession() {
    _stopHeartbeat();
    report(AgentStatus.offline);
  }

  void _startHeartbeat() {
    _heartbeat?.cancel();
    _heartbeat = Timer.periodic(const Duration(seconds: 25), (_) async {
      try {
        await ApiClient.instance.dio.post('/auth/status/heartbeat/');
      } catch (_) {}
    });
  }

  void _stopHeartbeat() {
    _heartbeat?.cancel();
    _heartbeat = null;
  }
}
