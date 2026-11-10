import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../data/services/api_client.dart';
import 'call_recording_service.dart';
import 'setup_service.dart';

// ============================================================
// DialSathi — Phone call tracking
//
// When the company admin turns it on for an agent (CRM → Settings → Call
// Tracking), the app saves EVERY incoming and outgoing call on the phone —
// including calls not made from the app's dialer, and missed calls — and
// uploads each answered call's recording.
//
// The source is the phone's own call log, read whenever the app runs (start,
// return to the app, after each call, and every few minutes). The call log
// keeps every call, so a call made while the app was closed is picked up the
// next time it opens: nothing is lost, only delayed.
//
// The server merges a call the app's dialer already saved with its call-log
// entry, so a call is never counted twice.
// ============================================================

/// What the phone has allowed, for the setup screen and the router.
class CallTrackingReadiness {
  /// This build can read the call log at all. The Play Store build cannot.
  final bool callLogSupported;
  final bool callLog;
  final bool phone;
  final bool storage;
  /// The agent agreed to the recording disclosure and recording is on.
  final bool recording;
  final bool battery;
  /// The phone uses the Google Phone app, whose recordings no app can read.
  final bool googleDialer;

  const CallTrackingReadiness({
    required this.callLogSupported,
    required this.callLog,
    required this.phone,
    required this.storage,
    required this.recording,
    required this.battery,
    required this.googleDialer,
  });

  /// Everything the agent must allow before working. Battery is advised,
  /// not required. A build without call-log support can't be fixed by the
  /// agent, so it does not hold them up.
  ///
  /// The Google Phone app must not be the default dialer: its recordings are
  /// private to it, so tracked calls would never have one. The agent installs
  /// a dialer that records into a folder and makes it the default.
  bool get complete =>
      !callLogSupported || (callLog && phone && storage && recording && !googleDialer);
}

/// One call-log entry from the phone, as sent to POST /calls/sync/.
/// Pure, so it can be tested without a phone.
Map<String, dynamic>? syncPayloadFor(Map<String, dynamic> entry) {
  final id = '${entry['id'] ?? ''}'.trim();
  final type = '${entry['type'] ?? ''}'.trim();
  final number = '${entry['number'] ?? ''}'.trim();
  final date = (entry['dateMillis'] as num?)?.toInt();
  if (id.isEmpty || type.isEmpty || date == null) return null;
  // Private / withheld numbers: nothing to save against.
  if (number.replaceAll(RegExp(r'[^0-9]'), '').length < 7) return null;
  return {
    'device_id': id,
    'number': number,
    'type': type,
    'started_at': date,
    'duration_seconds': (entry['durationSec'] as num?)?.toInt() ?? 0,
  };
}

/// Where the next sync starts: shortly before the newest entry already sent,
/// so a call still being written to the log when we last read it is not
/// skipped. The server ignores the repeats.
int nextWatermark(int current, Iterable<Map<String, dynamic>> sent) {
  var newest = current;
  for (final e in sent) {
    final d = (e['dateMillis'] as num?)?.toInt() ?? 0;
    if (d > newest) newest = d;
  }
  return newest;
}

class CallTrackingService extends ChangeNotifier {
  CallTrackingService._();
  static final CallTrackingService instance = CallTrackingService._();

  static const _channel = MethodChannel('dialeasypro/call_log');
  static const _sinceKeyPrefix = 'call_tracking_since_';
  static const _overlap = Duration(minutes: 10);
  static const _batch = 200;

  int? _agentId;
  bool _active = false;
  /// The agent has been through the setup screen on this phone.
  bool _started = false;
  CallTrackingReadiness? _readiness;
  Timer? _timer;
  Future<int>? _running;

  /// Last outcome, for Profile.
  DateTime? lastSyncAt;
  String? lastError;
  int lastSynced = 0;

  bool get active => _active;
  CallTrackingReadiness? get readiness => _readiness;

  /// For the router's redirect, which can't await: true while tracking is on
  /// and something the agent must allow is still missing.
  ///
  /// Shown once on each phone even when everything is already allowed: the
  /// agent is told their calls are now tracked before any call leaves it.
  bool get needsSetupSync =>
      _active && _readiness != null && (!_readiness!.complete || !_started);

  // ---- Lifecycle -------------------------------------------------

  /// Called whenever the signed-in agent (or their flag) is known or changes.
  Future<void> configure({required int? agentId, required bool enabled}) async {
    final changed = agentId != _agentId || enabled != _active;
    _agentId = agentId;
    _active = enabled && agentId != null && Platform.isAndroid;
    if (_active) {
      final prefs = await SharedPreferences.getInstance();
      _started = prefs.containsKey('$_sinceKeyPrefix$agentId');
      await refreshReadiness(notify: false);
      _timer ??= Timer.periodic(const Duration(minutes: 10), (_) => syncNow());
      unawaited(syncNow());
    } else {
      _timer?.cancel();
      _timer = null;
      _readiness = null;
    }
    if (changed) notifyListeners();
  }

  Future<CallTrackingReadiness> refreshReadiness({bool notify = true}) async {
    // Fresh each time: the agent may just have switched the default dialer.
    final info = await SetupService.instance.refreshDeviceInfo();
    final supported = info['callLogDeclared'] as bool? ?? true;
    final r = CallTrackingReadiness(
      callLogSupported: supported,
      callLog: supported && await _hasCallLogAccess(),
      phone: await Permission.phone.isGranted,
      storage: await _recordingsReadable(),
      recording: await CallRecordingService.instance.isEnabled(),
      battery: await SetupService.instance.isIgnoringBatteryOptimizations(),
      googleDialer: await CallRecordingService.instance.usesGoogleDialer(),
    );
    final was = _readiness?.complete;
    _readiness = r;
    if (notify || was != r.complete) notifyListeners();
    return r;
  }

  /// With a recorder app the agent must have chosen its folder; otherwise
  /// any way of reading recordings will do (the folder found automatically,
  /// the media index, or a chosen folder). The microphone needs nothing.
  Future<bool> _recordingsReadable() async {
    final rec = CallRecordingService.instance;
    switch (await rec.recordingSource()) {
      case 'recorder_app':
        return rec.hasFolderAccess();
      case 'app_mic':
        return true;
      default:
        return rec.hasStorageAccess();
    }
  }

  Future<bool> _hasCallLogAccess() async {
    try {
      return await _channel.invokeMethod<bool>('hasCallLogAccess') ?? false;
    } on MissingPluginException {
      return Permission.phone.isGranted;
    } on PlatformException {
      return false;
    }
  }

  /// The agent finished the setup screen: calls from now on are tracked
  /// (not the phone's history from before they agreed).
  Future<void> markStarted() async {
    final id = _agentId;
    if (id == null) return;
    final prefs = await SharedPreferences.getInstance();
    final key = '$_sinceKeyPrefix$id';
    if (!prefs.containsKey(key)) {
      await prefs.setInt(key, DateTime.now().subtract(const Duration(minutes: 5)).millisecondsSinceEpoch);
    }
    _started = true;
    await refreshReadiness();
    unawaited(syncNow());
  }

  /// Sync shortly after a call ends: the phone writes the call-log entry a
  /// moment after hanging up.
  void syncAfterCall() {
    if (!_active) return;
    Future.delayed(const Duration(seconds: 6), syncNow);
  }

  // ---- Sync ------------------------------------------------------

  /// Send new call-log entries. Returns how many calls the server saved.
  /// Concurrent calls share one run.
  Future<int> syncNow() {
    if (!_active) return Future.value(0);
    return _running ??= _sync().whenComplete(() => _running = null);
  }

  Future<int> _sync() async {
    final id = _agentId;
    if (id == null) return 0;
    final prefs = await SharedPreferences.getInstance();
    final key = '$_sinceKeyPrefix$id';
    final since = prefs.getInt(key);
    // Not set up on this phone yet: nothing from before the agent agreed.
    if (since == null) return 0;
    if (!(await refreshReadiness(notify: false)).callLog) {
      lastError = 'The app is not allowed to read your call log.';
      return 0;
    }

    var watermark = since;
    var saved = 0;
    try {
      for (var page = 0; page < 10; page++) {
        final from = watermark - _overlap.inMilliseconds;
        final res = await _channel.invokeMapMethod<String, dynamic>(
          'listSince', {'sinceMillis': from, 'limit': _batch},
        );
        if (res == null || res['ok'] != true) {
          lastError = 'Could not read the call log (${res?['reason'] ?? 'unknown'}).';
          break;
        }
        final entries = [
          for (final e in (res['calls'] as List? ?? const []))
            if (e is Map) e.map((k, v) => MapEntry(k.toString(), v)),
        ];
        final payload = [for (final e in entries) syncPayloadFor(e)].whereType<Map<String, dynamic>>().toList();
        if (payload.isNotEmpty) {
          final r = await ApiClient.instance.dio.post('/calls/sync/', data: {'calls': payload});
          final results = (r.data['results'] as List? ?? const []);
          saved += results.where((x) => x is Map && x['created'] == true).length;
          await _queueRecordings(entries, results);
        }
        final next = nextWatermark(watermark, entries);
        if (next > watermark) {
          watermark = next;
          await prefs.setInt(key, watermark);
        }
        // A short page means we have caught up.
        if (entries.length < _batch) break;
      }
      lastError = null;
    } on DioException catch (e) {
      final data = e.response?.data;
      if (e.response?.statusCode == 403 && data is Map && data['error'] == 'call_tracking_off') {
        // Switched off by the admin: stop until the profile says otherwise.
        lastError = 'Call tracking was turned off by your admin.';
        await configure(agentId: _agentId, enabled: false);
      } else {
        lastError = 'Sync failed: ${ApiClient.errorMessage(e)}';
      }
    } catch (e) {
      lastError = 'Sync failed: $e';
    }
    lastSyncAt = DateTime.now();
    lastSynced = saved;
    notifyListeners();
    return saved;
  }

  Future<void> _queueRecordings(List<Map<String, dynamic>> entries, List results) async {
    final byId = {for (final e in entries) '${e['id']}': e};
    for (final r in results) {
      if (r is! Map || r['needs_recording'] != true) continue;
      final e = byId['${r['device_id']}'];
      final callId = r['call_id'] as String?;
      if (e == null || callId == null) continue;
      try {
        await CallRecordingService.instance.captureForSyncedCall(
          callId: callId,
          phoneNumber: '${e['number'] ?? ''}',
          startedAt: DateTime.fromMillisecondsSinceEpoch((e['dateMillis'] as num).toInt()),
          talkSec: (e['durationSec'] as num?)?.toInt() ?? 0,
          contactName: '${e['cachedName'] ?? ''}',
          leadName: '${r['lead_name'] ?? ''}',
        );
      } catch (_) {
        // Queued for the sweep; never let one recording stop the sync.
      }
    }
  }
}
