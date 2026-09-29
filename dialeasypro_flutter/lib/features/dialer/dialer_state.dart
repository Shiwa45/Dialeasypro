import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/services/call_log_service.dart';
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
  /// When Android reported the line open. That is when dialling started, NOT
  /// when the customer answered — only the call log knows that.
  DateTime? offHookAt;
  /// 'call_log' when the figures came from the phone's call log, 'estimate'
  /// otherwise (the agent then confirms "connected" themselves).
  String outcomeSource = 'estimate';
  bool _finishing = false;
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

  /// Why the last action did not go through (a call that could not be
  /// placed, a save that failed, a queue that could not be reached). Shown
  /// once by the dialer screen; cleared by the next successful step.
  final String? error;

  const DialerState({
    this.mode = DialerMode.idle,
    this.phase = DialerPhase.idle,
    this.queue = const [],
    this.currentIndex = 0,
    this.currentCall,
    this.completedCalls = const [],
    this.onBreak = false,
    this.error,
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
    String? error,
    bool clearError = false,
  }) => DialerState(
    mode: mode ?? this.mode,
    phase: phase ?? this.phase,
    queue: queue ?? this.queue,
    currentIndex: currentIndex ?? this.currentIndex,
    currentCall: clearCurrentCall ? null : (currentCall ?? this.currentCall),
    completedCalls: completedCalls ?? this.completedCalls,
    onBreak: onBreak ?? this.onBreak,
    error: clearError ? null : (error ?? this.error),
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

  /// Set when pulling the next lead failed: resuming must pull again, not
  /// re-dial the lead that was just called and saved.
  bool _needsPull = false;

  // True while a queue (server or preloaded) is running.
  bool _sessionActive = false;

  /// A list of leads picked by hand while on a break. Manual calling is what
  /// a break is for, but auto-dialling is not: this list never dials on its
  /// own — the agent taps Call Now for each lead.
  bool _manualList = false;

  /// Where the agent goes back to once a call is saved: available, or the
  /// break they made the call from (with its reason).
  String _restStatus = AgentStatus.available;
  String _restReason = '';

  /// Every call reports presence — manual ones too. They used to report
  /// nothing, so a manual call made on a break was counted as break time in
  /// the Login Report, and talk time never showed on Live Agents.
  void _presence(String status) => PresenceService.instance.report(status);

  void _captureRest() {
    final p = PresenceService.instance;
    if (p.current == AgentStatus.onCall || p.current == AgentStatus.wrapUp) return;
    _restStatus = p.onBreak ? AgentStatus.breakStatus : AgentStatus.available;
    _restReason = p.onBreak ? p.breakReason : '';
  }

  void _returnToRest() {
    PresenceService.instance.report(
      _restStatus,
      breakReason: _restStatus == AgentStatus.breakStatus ? _restReason : null,
    );
  }

  /// Start a queue of leads to auto-dial through
  /// True when the agent is on a break. Auto-dialling is refused until the
  /// break is ended — the break exists so time on it is not dialling time.
  bool get _onBreak => state.onBreak || PresenceService.instance.onBreak;

  /// Call a hand-picked list of leads (Leads → select → call). Returns false
  /// when nothing was started.
  ///
  /// On a break this is manual calling, which a break allows: the list waits
  /// for the agent to tap Call Now for each lead and never advances by
  /// itself. (It used to be refused on a break — while the Leads tab only
  /// opens on one — and then opened an empty dialer that spun forever.)
  Future<bool> startQueue(List<Lead> leads) async {
    if (leads.isEmpty) return false;
    _serverQueueId = null;
    _sessionActive = true;
    _manualList = _onBreak;
    // Going "available" would end the break on the board; a manual list
    // leaves presence to the calls themselves.
    if (!_manualList) PresenceService.instance.startSession();
    state = DialerState(
      mode: DialerMode.queue,
      phase: DialerPhase.preCall,
      queue: leads,
      currentIndex: 0,
      completedCalls: const [],
    );
    if (_manualList) return true;
    // Brief pause before first call so user can see preview. In the
    // background, so the dialer screen opens straight away.
    _autoNextTimer?.cancel();
    _autoNextTimer = Timer(const Duration(milliseconds: 800), () {
      if (state.phase == DialerPhase.preCall) dialCurrent();
    });
    return true;
  }

  /// Start a server-backed queue: pull leads one at a time from the backend.
  /// The backend guarantees each lead is locked to this agent (no double
  /// dialing) and never repeated (worked-state + redial cooldown).
  Future<void> startServerQueue(int queueId) async {
    if (_onBreak) return;
    _manualList = false;
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
      // One retry: a single dropped request used to end the whole queue.
      Map<String, dynamic> res;
      try {
        res = await QueueService.instance.pullNext(qid);
      } catch (_) {
        await Future.delayed(const Duration(seconds: 2));
        res = await QueueService.instance.pullNext(qid);
      }
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
      // Still failing: pause rather than end, so the agent can resume once
      // the connection is back instead of losing the session.
      _needsPull = true;
      state = state.copyWith(
        phase: DialerPhase.paused,
        clearCurrentCall: true,
        error: 'Could not reach the queue. Check your connection and resume.',
      );
    }
  }

  /// Single-call mode (one lead, then return to lead detail)
  Future<void> startSingleCall(Lead lead) async {
    // A queue still open (e.g. paused for a break) is closed properly first:
    // its locked lead released, its session flags cleared. Replacing the
    // state without this kept the queue's flags, so the manual call ended
    // the break on the board and closing the dialer released this lead from
    // a queue it was never in — while the queue's own lead stayed locked.
    if (state.mode == DialerMode.queue) stop();
    _manualList = false;
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
    _captureRest();
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
      clearError: true,
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
      // Permission denied or no SIM: nothing was dialled. This used to go to
      // the post-call screen and demand an outcome for a call that never
      // happened — logging a 0-second call against the lead. Back to the
      // preview instead, saying why.
      state = state.copyWith(
        phase: DialerPhase.preCall,
        clearCurrentCall: true,
        error: 'The call could not be placed. Check phone permission and SIM, then try again.',
      );
      if (state.mode == DialerMode.queue) _autoNextTimer?.cancel();
    }
  }

  void _onPhoneEvent(PhoneCallEvent event) {
    if (state.currentCall == null) return;

    switch (event.status) {
      case CallStatus.active:
        state = state.copyWith(phase: DialerPhase.inCall);
        // Not "connected": Android reports the line open as soon as an
        // outgoing call starts dialling. Settled from the call log at the end.
        state.currentCall!.offHookAt ??= DateTime.now();
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
        _finishCall(state.currentCall!, fallbackDurationSec: event.durationSec);
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
    _finishCall(state.currentCall!, fallbackDurationSec: durationSec);
  }

  /// Settle a finished call's figures, then move to the post-call screen.
  ///
  /// The phone's call log has the real talk time (0 = not answered), so it is
  /// read first; without it the duration is estimated from timestamps and the
  /// agent confirms "connected". The post-call screen opens once this is done
  /// — a few seconds at most — so it shows the right figures from the start.
  Future<void> _finishCall(DialerCallRecord record, {int? fallbackDurationSec}) async {
    if (record._finishing || record.endedAt != null) return;
    record._finishing = true;
    final endedAt = DateTime.now();
    record.endedAt = endedAt;
    _presence(AgentStatus.wrapUp);
    _stopMicIntoRecord(record);

    Map<String, dynamic>? log;
    try {
      log = await CallLogService.instance
          .findOutgoing(record.phoneNumber, record.startedAt)
          .timeout(const Duration(seconds: 5), onTimeout: () => null);
    } catch (_) {
      log = null;
    }
    final outcome = decideCallOutcome(
      log: log,
      dialedAt: record.startedAt,
      endedAt: endedAt,
      offHookAt: record.offHookAt,
    );
    record.durationSec = outcome.source == 'estimate' && fallbackDurationSec != null
        ? fallbackDurationSec
        : outcome.durationSec;
    record.wasConnected = outcome.connected ?? false;
    record.endedAt = outcome.endedAt;
    record.outcomeSource = outcome.source;

    if (!mounted || state.currentCall != record) return;
    state = state.copyWith(phase: DialerPhase.postCall);
  }

  /// Save the disposition and move to next call (in queue mode) or finish.
  ///
  /// Returns false when the call could not be saved; the dialer then stays on
  /// this call so the agent can retry. It used to carry on regardless — the
  /// call was missing from every report and the lead stayed locked.
  Future<bool> dispose_({
    required int dispositionId,
    required String dispositionName,
    String notes = '',
    bool wasConnected = true,
    String? recordingUrl,
  }) async {
    final call = state.currentCall;
    if (call == null) return false;

    call.dispositionId = dispositionId;
    call.dispositionName = dispositionName;
    call.notes = notes;
    call.wasConnected = wasConnected;

    // Save call to backend — retried once, then reported.
    final payload = {
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
    };
    try {
      CallLog created;
      try {
        created = await CallsService.instance.createCall(payload);
      } catch (_) {
        await Future.delayed(const Duration(seconds: 2));
        created = await CallsService.instance.createCall(payload);
      }
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
      state = state.copyWith(
        error: 'This call could not be saved. Check your connection and save again.',
      );
      return false;
    }

    final newCompleted = [...state.completedCalls, call];
    state = state.copyWith(clearError: true);

    // Disposition saved → back to where the agent was: available between
    // calls, or the break a manual call was made from.
    _returnToRest();

    if (state.mode == DialerMode.single) {
      // Single call — done
      state = state.copyWith(
        phase: DialerPhase.completed,
        completedCalls: newCompleted,
        clearCurrentCall: true,
      );
      return true;
    }

    // Server-backed queue — the saved CallLog already marked the lead worked
    // and released its lock on the backend. Pull the next eligible lead.
    if (_serverQueueId != null) {
      state = state.copyWith(completedCalls: newCompleted, clearCurrentCall: true);
      unawaited(_pullAndDialNext());
      return true;
    }

    // Preloaded queue mode — move to next
    final nextIndex = state.currentIndex + 1;
    if (nextIndex >= state.queue.length) {
      state = state.copyWith(
        phase: DialerPhase.completed,
        completedCalls: newCompleted,
        clearCurrentCall: true,
      );
      return true;
    }

    // Brief delay before auto-dialing next
    state = state.copyWith(
      phase: DialerPhase.preCall,
      currentIndex: nextIndex,
      completedCalls: newCompleted,
      clearCurrentCall: true,
    );

    if (_manualList) return true; // the agent taps Call Now

    _autoNextTimer?.cancel();
    _autoNextTimer = Timer(const Duration(seconds: 2), () {
      if (state.phase == DialerPhase.preCall) {
        dialCurrent();
      }
    });
    return true;
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
    if (state.mode == DialerMode.queue && !_manualList) {
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
    if (state.phase != DialerPhase.paused || _onBreak) return;
    state = state.copyWith(clearError: true);
    if (_needsPull && _serverQueueId != null) {
      _needsPull = false;
      state = state.copyWith(phase: DialerPhase.preCall);
      unawaited(_pullAndDialNext());
      return;
    }
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
    _needsPull = false;
    _manualList = false;
    // Stop any in-call mic recording still running (user exited mid-call).
    CallRecordingService.instance.stopMicCapture().then((f) {
      try { f?.deleteSync(); } catch (_) {}
    }).catchError((_) {});
    // The queue ends, the work session does not: the agent stays live and
    // goes back to available (unless on a break). This used to end the whole
    // presence session, so an agent between queues showed as offline.
    if (_sessionActive) {
      if (PresenceService.instance.current != AgentStatus.breakStatus) {
        PresenceService.instance.report(AgentStatus.available);
      }
      _sessionActive = false;
    }
    state = const DialerState();
  }

  /// Go on a manual break — only allowed between calls (not during a live call).
  /// Pauses the dialer and reports the agent as on break.
  Future<void> goOnBreak({String reason = ''}) async {
    // Never with a call waiting for its outcome — see WorkSessionNotifier.takeBreak.
    if (state.phase == DialerPhase.inCall ||
        state.phase == DialerPhase.dialing ||
        state.phase == DialerPhase.postCall) return;
    if (!_sessionActive) return;
    _autoNextTimer?.cancel();
    state = state.copyWith(phase: DialerPhase.paused, onBreak: true);
    await PresenceService.instance.report(AgentStatus.breakStatus, breakReason: reason);
  }

  /// End the break and return to available. By default the dialer resumes;
  /// the work session passes autoResume: false so the agent resumes it
  /// themselves from the Auto Dial screen.
  Future<void> endBreak({bool autoResume = true}) async {
    if (!state.onBreak) return;
    state = state.copyWith(onBreak: false);
    await PresenceService.instance.report(AgentStatus.available);
    if (autoResume) resume();
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
