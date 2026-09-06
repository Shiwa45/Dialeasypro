import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/services/phone_service.dart';
import '../../core/services/call_recording_service.dart';
import '../../core/services/presence_service.dart';
import '../../data/services/services.dart';
import '../../data/models/models.dart';

// ============================================================
// DialEasypro — Dialer Queue State Manager
// Implements the auto-dialer flow:
//   1. Load queue of leads
//   2. Direct-dial the first lead
//   3. After call ends → mandatory disposition
//   4. After disposition saved → auto-trigger next call
//   5. User can pause/resume/skip at any point
// ============================================================

enum DialerMode { idle, queue, single }
enum DialerPhase {
  idle,             // No active session
  preCall,          // About to dial — showing lead preview
  dialing,          // System dialer launched
  inCall,           // Call connected (system shows native UI)
  postCall,         // Call ended — MUST dispose before next
  disposed,         // Disposition saved → ready for next
  paused,           // User paused the queue
  completed,        // Queue exhausted
}

class DialerCallRecord {
  final int leadId;
  final String leadName;
  final String phoneNumber;
  final DateTime startedAt;
  DateTime? endedAt;
  int durationSec = 0;
  bool wasConnected = false;
  int? dispositionId;
  String? dispositionName;
  String notes = '';
  bool savedToBackend = false;
  // In-app mic recording captured during this call (universal fallback when
  // the device has no OEM call recorder). Set when the call ends.
  File? micRecording;

  DialerCallRecord({
    required this.leadId,
    required this.leadName,
    required this.phoneNumber,
    required this.startedAt,
  });
}

class DialerState {
  final DialerMode mode;
  final DialerPhase phase;
  final List<Lead> queue;
  final int currentIndex;
  final DialerCallRecord? currentCall;
  final List<DialerCallRecord> completedCalls;
  final bool onBreak;

  const DialerState({
    this.mode = DialerMode.idle,
    this.phase = DialerPhase.idle,
    this.queue = const [],
    this.currentIndex = 0,
    this.currentCall,
    this.completedCalls = const [],
    this.onBreak = false,
  });

  Lead? get currentLead => currentIndex < queue.length ? queue[currentIndex] : null;
  int get totalCalls => queue.length;
  int get callsDone => completedCalls.length;
  double get progress => totalCalls > 0 ? callsDone / totalCalls : 0;

  DialerState copyWith({
    DialerMode? mode,
    DialerPhase? phase,
    List<Lead>? queue,
    int? currentIndex,
    DialerCallRecord? currentCall,
    bool clearCurrentCall = false,
    List<DialerCallRecord>? completedCalls,
    bool? onBreak,
  }) => DialerState(
    mode: mode ?? this.mode,
    phase: phase ?? this.phase,
    queue: queue ?? this.queue,
    currentIndex: currentIndex ?? this.currentIndex,
    currentCall: clearCurrentCall ? null : (currentCall ?? this.currentCall),
    completedCalls: completedCalls ?? this.completedCalls,
    onBreak: onBreak ?? this.onBreak,
  );
}

class DialerNotifier extends StateNotifier<DialerState> {
  DialerNotifier() : super(const DialerState()) {
    _phoneSub = PhoneService.instance.events.listen(_onPhoneEvent);
  }

  StreamSubscription<PhoneCallEvent>? _phoneSub;
  Timer? _autoNextTimer;

  // When set, the dialer is consuming a server-side queue: leads are pulled
  // one at a time (locked to this agent) instead of from a preloaded list.
  int? _serverQueueId;

  // True while an auto-dial session is active — gates presence reporting so
  // one-off single calls don't show the agent as "online" to admins.
  bool _sessionActive = false;

  void _presence(String status) {
    if (_sessionActive) PresenceService.instance.report(status);
  }

  /// Start a queue of leads to auto-dial through
  Future<void> startQueue(List<Lead> leads) async {
    if (leads.isEmpty) return;
    _serverQueueId = null;
    _sessionActive = true;
    PresenceService.instance.startSession();
    state = DialerState(
      mode: DialerMode.queue,
      phase: DialerPhase.preCall,
      queue: leads,
      currentIndex: 0,
      completedCalls: const [],
    );
    // Brief pause before first call so user can see preview
    await Future.delayed(const Duration(milliseconds: 800));
    if (state.phase == DialerPhase.preCall) {
      await dialCurrent();
    }
  }

  /// Start a server-backed queue: pull leads one at a time from the backend.
  /// The backend guarantees each lead is locked to this agent (no double
  /// dialing) and never repeated (worked-state + redial cooldown).
  Future<void> startServerQueue(int queueId) async {
    _serverQueueId = queueId;
    _sessionActive = true;
    PresenceService.instance.startSession();
    state = const DialerState(
      mode: DialerMode.queue,
      phase: DialerPhase.preCall,
      queue: [],
      currentIndex: 0,
      completedCalls: [],
    );
    await _pullAndDialNext(initial: true);
  }

  /// Pull the next lead from the server queue and dial it, or complete.
  Future<void> _pullAndDialNext({bool initial = false}) async {
    final qid = _serverQueueId;
    if (qid == null) return;
    try {
      final res = await QueueService.instance.pullNext(qid);
      if (res['empty'] == true || res['lead'] == null) {
        state = state.copyWith(phase: DialerPhase.completed, clearCurrentCall: true);
        return;
      }
      final lead = Lead.fromJson(res['lead'] as Map<String, dynamic>);
      // Append the freshly pulled lead and point the index at it.
      final newQueue = [...state.queue, lead];
      state = state.copyWith(
        phase: DialerPhase.preCall,
        queue: newQueue,
        currentIndex: newQueue.length - 1,
        clearCurrentCall: true,
      );
      await Future.delayed(Duration(milliseconds: initial ? 600 : 1500));
      if (state.phase == DialerPhase.preCall) {
        await dialCurrent();
      }
    } catch (_) {
      // On error, stop gracefully at completed so the UI isn't stuck.
      state = state.copyWith(phase: DialerPhase.completed, clearCurrentCall: true);
    }
  }

  /// Single-call mode (one lead, then return to lead detail)
  Future<void> startSingleCall(Lead lead) async {
    state = DialerState(
      mode: DialerMode.single,
      phase: DialerPhase.preCall,
      queue: [lead],
      currentIndex: 0,
    );
    await dialCurrent();
  }

  /// Dial the lead at the current index
  Future<void> dialCurrent() async {
    final lead = state.currentLead;
    if (lead == null) {
      state = state.copyWith(phase: DialerPhase.completed);
      return;
    }

    final record = DialerCallRecord(
      leadId: lead.id,
      leadName: lead.name,
      phoneNumber: lead.phone,
      startedAt: DateTime.now(),
    );

    state = state.copyWith(
      phase: DialerPhase.dialing,
      currentCall: record,
    );

    // Start the fallback recording BEFORE handing the screen to the dialer.
    // RECORD_AUDIO is "while in use": started here the mic stays live behind
    // the dialer via the foreground service, whereas starting it once the call
    // connects (as this used to) means asking a backgrounded app for the
    // microphone — silence on Android 11+, refused on 12+.
    await CallRecordingService.instance.startMicCapture();

    final success = await PhoneService.instance.directDial(lead.phone);
    if (!success) {
      // Never leave the mic and its notification running for a call that was
      // never placed.
      await CallRecordingService.instance.stopMicCapture();
    }
    if (!success) {
      // Permission denied or dial failed — mark and let user retry
      state = state.copyWith(phase: DialerPhase.postCall);
    }
  }

  void _onPhoneEvent(PhoneCallEvent event) {
    if (state.currentCall == null) return;

    switch (event.status) {
      case CallStatus.active:
        state = state.copyWith(phase: DialerPhase.inCall);
        state.currentCall!.wasConnected = true;
        _presence(AgentStatus.onCall);
        // Recording already started at dial time — see dialCurrent(). It
        // cannot be started here: by now the dialer owns the screen and this
        // app is in the background, where the microphone is unavailable.
        break;
      case CallStatus.ringing:
      case CallStatus.dialing:
      case CallStatus.connecting:
        // Stay in dialing/inCall
        break;
      case CallStatus.ended:
      case CallStatus.failed:
        state.currentCall!.endedAt = DateTime.now();
        state.currentCall!.durationSec = event.durationSec ?? 0;
        state = state.copyWith(phase: DialerPhase.postCall);
        _presence(AgentStatus.wrapUp);
        _stopMicIntoRecord(state.currentCall!);
        break;
      case CallStatus.idle:
        break;
    }
  }

  /// Stop the in-call mic recording (if any) and stash the file on the record.
  void _stopMicIntoRecord(DialerCallRecord record) {
    CallRecordingService.instance.stopMicCapture().then((file) {
      if (file != null) record.micRecording = file;
    }).catchError((_) {});
  }

  /// Manually mark current call as ended (when system doesn't notify reliably)
  void markCallEnded({int? durationSec, bool? wasConnected}) {
    if (state.currentCall == null) return;
    state.currentCall!.endedAt = DateTime.now();
    if (durationSec != null) state.currentCall!.durationSec = durationSec;
    if (wasConnected != null) state.currentCall!.wasConnected = wasConnected;
    state = state.copyWith(phase: DialerPhase.postCall);
    _presence(AgentStatus.wrapUp);
    _stopMicIntoRecord(state.currentCall!);
  }

  /// Save the disposition and move to next call (in queue mode) or finish
  Future<void> dispose_({
    required int dispositionId,
    required String dispositionName,
    String notes = '',
    bool wasConnected = true,
    String? recordingUrl,
  }) async {
    final call = state.currentCall;
    if (call == null) return;

    call.dispositionId = dispositionId;
    call.dispositionName = dispositionName;
    call.notes = notes;
    call.wasConnected = wasConnected;

    // Save call to backend
    try {
      final created = await CallsService.instance.createCall({
        'lead': call.leadId,
        'phone_number': call.phoneNumber,
        'direction': 'outbound',
        'started_at': call.startedAt.toUtc().toIso8601String(),
        'ended_at': (call.endedAt ?? DateTime.now()).toUtc().toIso8601String(),
        'duration_seconds': call.durationSec,
        'is_connected': call.wasConnected,
        'disposition': dispositionId,
        'notes': notes,
        if (recordingUrl != null) 'recording_url': recordingUrl,
      });
      call.savedToBackend = true;

      // Call recording: try the phone's OEM recorder file first (two-way
      // audio); fall back to the in-app mic recording captured during the
      // call, which exists on every device. Fire-and-forget; no-op when the
      // feature is off. Attempt whenever the call plausibly happened — the
      // phone-state listener can miss connect events on some OEMs, so don't
      // gate on wasConnected alone.
      final mic = call.micRecording;
      if (mic != null || (call.wasConnected && call.durationSec > 0)) {
        CallRecordingService.instance.captureForCall(
          callId: created.id,
          phoneNumber: call.phoneNumber,
          startedAt: call.startedAt,
          durationSec: call.durationSec,
          fallbackFile: mic,
        ).catchError((_) {});
      }
    } catch (_) {
      // Continue anyway — call is logged locally
    }

    final newCompleted = [...state.completedCalls, call];

    // Disposition saved → back to available (between calls) for the session.
    _presence(AgentStatus.available);

    if (state.mode == DialerMode.single) {
      // Single call — done
      state = state.copyWith(
        phase: DialerPhase.completed,
        completedCalls: newCompleted,
        clearCurrentCall: true,
      );
      return;
    }

    // Server-backed queue — the saved CallLog already marked the lead worked
    // and released its lock on the backend. Pull the next eligible lead.
    if (_serverQueueId != null) {
      state = state.copyWith(completedCalls: newCompleted, clearCurrentCall: true);
      await _pullAndDialNext();
      return;
    }

    // Preloaded queue mode — move to next
    final nextIndex = state.currentIndex + 1;
    if (nextIndex >= state.queue.length) {
      state = state.copyWith(
        phase: DialerPhase.completed,
        completedCalls: newCompleted,
        clearCurrentCall: true,
      );
      return;
    }

    // Brief delay before auto-dialing next
    state = state.copyWith(
      phase: DialerPhase.preCall,
      currentIndex: nextIndex,
      completedCalls: newCompleted,
      clearCurrentCall: true,
    );

    _autoNextTimer?.cancel();
    _autoNextTimer = Timer(const Duration(seconds: 2), () {
      if (state.phase == DialerPhase.preCall) {
        dialCurrent();
      }
    });
  }

  /// Skip the current lead without calling (e.g. found out it's wrong number)
  Future<void> skip({String reason = 'Skipped'}) async {
    final current = state.currentLead;
    if (current == null) return;

    // Server-backed queue — release the lock (not marked dialed) so the lead
    // returns to the pool after its TTL, then pull the next one.
    if (_serverQueueId != null) {
      try {
        await QueueService.instance.release(current.id, markDialed: false);
      } catch (_) {}
      await _pullAndDialNext();
      return;
    }

    final nextIndex = state.currentIndex + 1;
    if (nextIndex >= state.queue.length) {
      state = state.copyWith(phase: DialerPhase.completed, clearCurrentCall: true);
      return;
    }
    state = state.copyWith(
      phase: DialerPhase.preCall,
      currentIndex: nextIndex,
      clearCurrentCall: true,
    );
    if (state.mode == DialerMode.queue) {
      _autoNextTimer?.cancel();
      _autoNextTimer = Timer(const Duration(seconds: 1), () {
        if (state.phase == DialerPhase.preCall) dialCurrent();
      });
    }
  }

  /// Pause the auto-dialer
  void pause() {
    _autoNextTimer?.cancel();
    state = state.copyWith(phase: DialerPhase.paused);
  }

  /// Resume after pause
  void resume() {
    if (state.phase != DialerPhase.paused) return;
    if (state.currentCall != null && state.currentCall!.endedAt != null) {
      // We were mid-disposition
      state = state.copyWith(phase: DialerPhase.postCall);
    } else {
      state = state.copyWith(phase: DialerPhase.preCall);
      dialCurrent();
    }
  }

  /// Stop the queue entirely
  void stop() {
    _autoNextTimer?.cancel();
    // Release any lead still locked to this agent on the server.
    final current = state.currentLead;
    if (_serverQueueId != null && current != null && state.phase != DialerPhase.completed) {
      QueueService.instance.release(current.id, markDialed: false).catchError((_) {});
    }
    _serverQueueId = null;
    // Stop any in-call mic recording still running (user exited mid-call).
    CallRecordingService.instance.stopMicCapture().then((f) {
      try { f?.deleteSync(); } catch (_) {}
    }).catchError((_) {});
    // End the session → agent goes offline on the monitoring dashboard.
    if (_sessionActive) {
      PresenceService.instance.endSession();
      _sessionActive = false;
    }
    state = const DialerState();
  }

  /// Go on a manual break — only allowed between calls (not during a live call).
  /// Pauses the dialer and reports the agent as on break.
  Future<void> goOnBreak({String reason = ''}) async {
    if (state.phase == DialerPhase.inCall || state.phase == DialerPhase.dialing) return;
    if (!_sessionActive) return;
    _autoNextTimer?.cancel();
    state = state.copyWith(phase: DialerPhase.paused, onBreak: true);
    await PresenceService.instance.report(AgentStatus.breakStatus, breakReason: reason);
  }

  /// End the break and return to available; resumes the dialer.
  Future<void> endBreak() async {
    if (!state.onBreak) return;
    state = state.copyWith(onBreak: false);
    await PresenceService.instance.report(AgentStatus.available);
    resume();
  }

  /// Mark current call's notes (during call)
  void updateCallNotes(String notes) {
    if (state.currentCall == null) return;
    state.currentCall!.notes = notes;
  }

  @override
  void dispose() {
    _phoneSub?.cancel();
    _autoNextTimer?.cancel();
    super.dispose();
  }
}

final dialerProvider = StateNotifierProvider<DialerNotifier, DialerState>(
  (_) => DialerNotifier(),
);
