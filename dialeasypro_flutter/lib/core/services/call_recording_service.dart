import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

import 'package:dio/dio.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../data/services/api_client.dart';
import 'setup_service.dart';

// ============================================================
// DialSathi — Call Recording Service (SIM-based)
//
// Android 10+ blocks apps from recording cellular call audio directly, so we
// use the phone's OWN built-in/OEM call recorder (Samsung/Xiaomi/Vivo/Oppo/etc.)
// and then:
//   1) watch the known OEM call-recording folders,
//   2) match each new audio file to the call we just made
//      (phone number embedded in filename + file mtime + duration),
//   3) upload the matched file to the backend, which stores it on Cloudinary
//      and links it to the CallLog.
//
// This is exactly how NeoDove / Runo / TeleCRM do SIM-based recording.
// It requires the device to HAVE a native call recorder and the user to have
// enabled it + granted "All files access". On devices with no recorder
// (stock Android / many Pixels) there is simply no file to capture.
// ============================================================

class CallRecordingService {
  CallRecordingService._();
  static final CallRecordingService instance = CallRecordingService._();

  static const _enabledKey = 'call_recording_enabled';
  static const _processedKey = 'call_recording_processed_paths';

  /// Calls still waiting for their recording file to appear.
  ///
  /// OEM recorders do not finalise the file when the call ends. Xiaomi and
  /// Vivo can take a minute or more, and some write nothing until their own
  /// recorder app is next opened. The post-call scan gives up after ~30s, so
  /// without this queue a recording sitting on the phone was simply never
  /// collected — the one-shot attempt was the only attempt ever made.
  static const _pendingKey = 'call_recording_pending';

  /// How long to keep looking. Past this the file is almost certainly never
  /// coming, and an unbounded queue would rescan forever.
  static const _pendingTtl = Duration(days: 3);

  // Known OEM call-recording directories (relative to external storage root).
  // The list is intentionally broad; we scan every path that exists.
  static const List<String> _candidateDirs = [
    'Call',                              // Generic / Google
    'Recordings/Call',                   // Android 14 generic
    'Recordings/Call Recordings',
    'CallRecordings',
    'Call Recordings',
    'PhoneRecord',                       // Huawei/Honor
    'Sounds/CallRecord',                 // Some Vivo
    'MIUI/sound_recorder/call_rec',      // Xiaomi MIUI
    'MIUI/sound_recorder/call_recorder',
    'Recorder/call',                     // Xiaomi newer
    'Music/Recordings/Call Recordings',  // Samsung (older)
    'Record/Call',                       // Oppo/Realme/OnePlus (ColorOS)
    'DCIM/Call',
    // Deliberately NOT scanned: Sounds, Music/Recordings, Recordings/Voice
    // Recorder and the sound recorder's own folder. They hold voice memos and
    // personal audio, which a time-only match could attach to a customer call.
    'voice_call',                        // Vivo Funtouch
    'record/call',
    'Recordings/PhoneRecord',            // OnePlus OxygenOS 12+
    'Record/PhoneRecord',
    'Music/Recordings/PhoneRecord',
    'Recordings/Call recordings',        // Motorola / some Android 14 builds
    'Recordings/Record/Call',            // Vivo / iQOO (Funtouch 13+, OriginOS)
    'Recordings/CallRecordings',
    'Record/CallRecord',
    'Recorder/Call',                     // Infinix / Tecno / itel (XOS, HiOS)
    'Recorder/CallRecord',
    'Recordings/CallRecord',             // Honor MagicOS
    'Sounds/Call',
  ];

  static const _audioExts = {'.m4a', '.mp3', '.amr', '.wav', '.aac', '.3gp', '.ogg', '.mp4'};

  // ---- Settings -------------------------------------------------

  /// When the phone's own call recorder last produced a file we matched.
  static const _oemSeenKey = 'call_recording_oem_seen_at';

  /// 'auto' (default), 'always' or 'never': whether the app records the
  /// microphone during calls.
  static const _micModeKey = 'call_recording_mic_mode';

  /// Every recording file already uploaded, as "path|size|mtime", so one file
  /// is never attached to two calls (it used to be keyed per call only).
  static const _usedFilesKey = 'call_recording_used_files';

  // ---- Where recordings come from (NeoDove-style "Call Recording Path") ----
  //
  //  * 'builtin'      — the phone's own call recorder (default). Its folder is
  //                     found automatically, or chosen by the agent.
  //  * 'recorder_app' — a call-recorder app (Cube ACR, a recording dialer) on
  //                     phones whose dialer keeps recordings private (the
  //                     Google Phone app). The agent chooses its folder.
  //  * 'app_mic'      — DialSathi records through the microphone during calls
  //                     dialled from the app (no recorder on the phone at all).
  static const _sourceKey = 'call_recording_source';
  static const _folderUriKey = 'call_recording_folder_uri';
  static const _folderLabelKey = 'call_recording_folder_label';
  static const sources = ['builtin', 'recorder_app', 'app_mic'];

  Future<String> recordingSource() async {
    final prefs = await SharedPreferences.getInstance();
    final v = prefs.getString(_sourceKey) ?? 'builtin';
    return sources.contains(v) ? v : 'builtin';
  }

  Future<void> setRecordingSource(String source) async {
    if (!sources.contains(source)) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_sourceKey, source);
    // The microphone must stay off when a recorder is in use: holding it
    // stops the phone (or the recorder app) from recording the call.
    await setMicMode(switch (source) {
      'app_mic' => 'always',
      'recorder_app' => 'never',
      _ => 'auto',
    });
  }

  /// The folder the agent chose: (uri, label), or null.
  Future<({String uri, String label})?> recordingFolder() async {
    final prefs = await SharedPreferences.getInstance();
    final uri = prefs.getString(_folderUriKey);
    if (uri == null || uri.isEmpty) return null;
    return (uri: uri, label: prefs.getString(_folderLabelKey) ?? uri);
  }

  /// Opens Android's folder picker. Returns the chosen folder's label, or
  /// null when cancelled.
  Future<String?> pickRecordingFolder() async {
    if (!Platform.isAndroid) return null;
    try {
      final res = await _probeChannel.invokeMapMethod<String, dynamic>('pickRecordingFolder');
      final uri = res?['uri'] as String?;
      if (uri == null || uri.isEmpty) return null;
      final label = res?['label'] as String? ?? uri;
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_folderUriKey, uri);
      await prefs.setString(_folderLabelKey, label);
      return label;
    } catch (_) {
      return null;
    }
  }

  Future<void> clearRecordingFolder() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_folderUriKey);
    await prefs.remove(_folderLabelKey);
  }

  /// Whether the app can still read the chosen folder (the agent can revoke
  /// it, and it is lost when the folder is deleted).
  Future<bool> hasFolderAccess() async {
    final f = await recordingFolder();
    if (f == null || !Platform.isAndroid) return false;
    try {
      return await _probeChannel.invokeMethod<bool>('hasFolderAccess', {'uri': f.uri}) ?? false;
    } catch (_) {
      return false;
    }
  }

  /// The newest recording in the chosen folder from the last week, for the
  /// "Check folder" button: proves the folder is right after a test call.
  Future<({String name, DateTime modified})?> newestInFolder() async {
    final now = DateTime.now();
    final files = await _folderAudio(now.subtract(const Duration(days: 7)), now.add(const Duration(minutes: 1)));
    if (files.isEmpty) return null;
    final m = files.first;
    return (
      name: m['name'] as String? ?? '',
      modified: DateTime.fromMillisecondsSinceEpoch((m['modifiedMillis'] as num?)?.toInt() ?? 0),
    );
  }

  Future<List<Map<String, dynamic>>> _folderAudio(DateTime from, DateTime to) async {
    final f = await recordingFolder();
    if (f == null || !Platform.isAndroid) return const [];
    try {
      final raw = await _probeChannel.invokeListMethod<dynamic>('listFolderAudio', {
        'uri': f.uri,
        'fromMillis': from.millisecondsSinceEpoch,
        'toMillis': to.millisecondsSinceEpoch,
      });
      return [
        for (final e in raw ?? const [])
          if (e is Map) e.map((k, v) => MapEntry(k.toString(), v)),
      ];
    } catch (_) {
      return const [];
    }
  }

  Future<double?> _uriDurationSec(String uri) async {
    try {
      final ms = await _probeChannel.invokeMethod<int>('uriDurationMs', {'uri': uri});
      return ms == null ? null : ms / 1000.0;
    } catch (_) {
      return null;
    }
  }

  Future<String> micMode() async {
    final prefs = await SharedPreferences.getInstance();
    final v = prefs.getString(_micModeKey) ?? 'auto';
    return const {'auto', 'always', 'never'}.contains(v) ? v : 'auto';
  }

  Future<void> setMicMode(String mode) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_micModeKey, mode);
  }

  /// Whether to record the microphone for the next call.
  ///
  /// On a phone with its own call recorder the app must NOT hold the
  /// microphone: while it does, the phone's recorder records nothing (or the
  /// call isn't recorded at all) and the app's own file comes out a fraction
  /// of a second long — on the live system three of eight recorded calls
  /// ended up with a 0.2 s microphone file instead of the call. So in 'auto'
  /// the microphone is used only when this phone has never produced a call
  /// recording and its brand ships without a recorder.
  Future<bool> shouldUseMicFallback() async {
    final source = await recordingSource();
    if (source == 'app_mic') return true;
    if (source == 'recorder_app') return false;
    final mode = await micMode();
    if (mode == 'never') return false;
    if (mode == 'always') return true;
    final prefs = await SharedPreferences.getInstance();
    final seen = DateTime.tryParse(prefs.getString(_oemSeenKey) ?? '');
    if (seen != null && DateTime.now().difference(seen) < const Duration(days: 30)) return false;
    try {
      // Xiaomi, Realme, OnePlus and others now ship the Google Phone app as
      // the dialer. Its recordings stay inside that app where nothing else
      // can read them, so the brand's "has a recorder" says nothing: those
      // phones got neither the phone's file nor the microphone fallback.
      if (await usesGoogleDialer()) return true;
      final brand = (await SetupService.instance.guide()).brand;
      if (brandHasCallRecorder(brand)) return false;
    } catch (_) {
      // Unknown phone: fall through to the microphone.
    }
    return true;
  }

  /// Whether the phone's default dialer is the Google Phone app, whose call
  /// recordings are private to it (not in shared storage).
  Future<bool> usesGoogleDialer() async {
    final info = await SetupService.instance.deviceInfo();
    return isGoogleDialer(info['dialerPackage'] as String? ?? '');
  }

  Future<void> _markOemSeen() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_oemSeenKey, DateTime.now().toIso8601String());
  }

  static const _probeChannel = MethodChannel('dialeasypro/call_log');

  /// Length of an audio file in seconds, read from the file itself; null when
  /// the phone can't tell (older app shell, unreadable file).
  Future<double?> audioDurationSec(String path) async {
    if (!Platform.isAndroid) return null;
    try {
      final ms = await _probeChannel.invokeMethod<int>('audioDurationMs', {'path': path});
      return ms == null ? null : ms / 1000.0;
    } catch (_) {
      return null;
    }
  }

  static String _fileKey(File f) {
    try {
      final st = f.statSync();
      return '${f.path}|${st.size}|${st.modified.millisecondsSinceEpoch}';
    } catch (_) {
      return f.path;
    }
  }

  Future<Set<String>> _usedFiles() async {
    final prefs = await SharedPreferences.getInstance();
    return (prefs.getStringList(_usedFilesKey) ?? const <String>[]).toSet();
  }

  Future<void> _rememberUsed(String key) async {
    final prefs = await SharedPreferences.getInstance();
    final list = prefs.getStringList(_usedFilesKey) ?? <String>[];
    if (list.contains(key)) return;
    list.add(key);
    if (list.length > 1000) list.removeRange(0, list.length - 1000);
    await prefs.setStringList(_usedFilesKey, list);
  }

  /// Remove the Cloudinary account an agent may once have entered for voice
  /// notes. Recordings no longer use it (see _uploadIfNew), and with the
  /// setting gone from Profile it could otherwise never be cleared.
  static Future<void> purgeLegacyCloudinarySettings() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('cloudinary_name');
    await prefs.remove('cloudinary_preset');
  }

  /// The agent agreed to the recording disclosure (RecordingDisclosure).
  /// Versioned: changing what is collected means asking again.
  static const _consentKey = 'call_recording_consent_v1';

  /// Recording is on only with the agent's switch AND their consent. Google
  /// Play requires the disclosure before any call audio is collected, so an
  /// install that had the switch on from before the disclosure existed stays
  /// off until the agent has agreed.
  Future<bool> isEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return (prefs.getBool(_enabledKey) ?? false) && (prefs.getBool(_consentKey) ?? false);
  }

  /// Switches recording on or off. Turning it on without consent is ignored —
  /// show the disclosure first (confirmRecordingDisclosure).
  Future<void> setEnabled(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    if (value && !(prefs.getBool(_consentKey) ?? false)) return;
    await prefs.setBool(_enabledKey, value);
  }

  Future<bool> hasConsent() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_consentKey) ?? false;
  }

  Future<void> recordConsent() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_consentKey, true);
  }

  // ---- Permissions ----------------------------------------------

  /// Whether we currently have the access needed to read recording folders.
  Future<bool> hasStorageAccess() async {
    // A folder the agent chose is readable without any storage permission.
    if (await hasFolderAccess()) return true;
    // MANAGE_EXTERNAL_STORAGE covers OEM folders not indexed by MediaStore.
    if (await Permission.manageExternalStorage.isGranted) return true;
    // Fallbacks (older OS / audio-only access).
    if (await Permission.audio.isGranted) return true;
    if (await Permission.storage.isGranted) return true;
    return false;
  }

  /// Request the broadest access ("All files access") with graceful fallback.
  Future<bool> requestStorageAccess() async {
    var status = await Permission.manageExternalStorage.request();
    if (status.isGranted) return true;
    // Fallback for Android 13+ audio scope / Android ≤12 storage.
    final audio = await Permission.audio.request();
    if (audio.isGranted) return true;
    final storage = await Permission.storage.request();
    return storage.isGranted;
  }

  // ---- In-app mic capture (universal fallback) -------------------
  //
  // Android 10+ blocks recording the call's downlink audio, but recording the
  // MICROPHONE during a call is allowed. With the call on speaker both sides
  // are audible; otherwise the agent side is captured. This works on EVERY
  // device — including those with no OEM call recorder (Pixels/stock Android)
  // — so no call goes completely unrecorded. When an OEM recording IS found,
  // it wins (better quality) and the mic file is discarded.

  final AudioRecorder _micRecorder = AudioRecorder();
  String? _micPath;
  bool _micActive = false;

  /// Native bridge to the microphone foreground service (see
  /// android/.../CallAudioService.kt).
  static const _audioChannel = MethodChannel('dialeasypro/call_audio');

  /// Last thing that went wrong, for the Profile diagnostics panel. Recording
  /// runs entirely in the background, so without this a failure is invisible:
  /// the agent finishes a call and simply never sees a recording, with nothing
  /// anywhere to say why.
  String? lastError;
  DateTime? lastAttemptAt;

  void _note(String message) {
    lastError = message;
    lastAttemptAt = DateTime.now();
  }

  /// Start recording the microphone for the current call.
  ///
  /// MUST be called while the app is still in the foreground — i.e. at dial
  /// time, not when the call connects. RECORD_AUDIO is a "while in use"
  /// permission: once the system dialer takes the screen this app is
  /// backgrounded, where Android 11+ hands out silence and 12+ refuses to
  /// start the foreground service at all. Starting here, before the dialer
  /// appears, is what makes the fallback work on a modern device.
  Future<void> startMicCapture() async {
    if (_micActive) return;
    if (!await isEnabled()) return;
    // Not on a phone that records calls itself — see shouldUseMicFallback.
    if (!await shouldUseMicFallback()) return;
    try {
      if (!await _micRecorder.hasPermission()) {
        _note('Microphone permission not granted — no fallback recording.');
        return;
      }

      // Hold mic access across the app going to the background.
      var serviceStarted = false;
      if (Platform.isAndroid) {
        try {
          serviceStarted = await _audioChannel.invokeMethod<bool>('start') ?? false;
        } on PlatformException catch (e) {
          serviceStarted = false;
          _note('Audio service error: ${e.code}');
        } on MissingPluginException {
          // Older build of the app shell without the native service.
          serviceStarted = false;
        }
        if (!serviceStarted) {
          _note('Could not hold the microphone in the background; '
              'the fallback recording may be silent.');
        }
      }

      // App storage, not the temp folder: a recording whose upload fails is
      // kept for a retry, and Android may clear temp files at any time.
      final dir = await getApplicationSupportDirectory();
      _micPath = '${dir.path}/mic_call_${DateTime.now().millisecondsSinceEpoch}.m4a';
      await _micRecorder.start(
        const RecordConfig(
          encoder: AudioEncoder.aacLc,
          bitRate: 64000,
          sampleRate: 44100,
          numChannels: 1,
        ),
        path: _micPath!,
      );
      _micActive = true;
    } catch (e) {
      _micActive = false;
      _micPath = null;
      _note('Could not start recording: $e');
      await _stopAudioService();
    }
  }

  Future<void> _stopAudioService() async {
    if (!Platform.isAndroid) return;
    try {
      await _audioChannel.invokeMethod('stop');
    } catch (_) {
      // Nothing useful to do; the service stops with the task regardless.
    }
  }

  /// Stop the mic recording and return the file if it captured real audio.
  Future<File?> stopMicCapture() async {
    if (!_micActive) return null;
    _micActive = false;
    try {
      final path = await _micRecorder.stop();
      final f = File(path ?? _micPath ?? '');
      if (!f.existsSync()) {
        _note('Recording produced no file.');
        return null;
      }
      final size = f.statSync().size;
      // A silenced mic still yields a valid, tiny container. Treat that as no
      // recording rather than uploading a file of nothing.
      if (size <= 4096) {
        _note('Recording was empty (${size}B) — Android muted the microphone.');
        _deleteQuietly(f);
        return null;
      }
      // A valid file of a fraction of a second: Android took the microphone
      // away when the call started. These used to be uploaded as the call's
      // recording (0.2 s of audio, nothing for the AI summary to read).
      final seconds = await audioDurationSec(f.path);
      if (seconds != null && seconds < 2) {
        _note('The microphone recording stopped after ${seconds.toStringAsFixed(1)}s — '
            'the phone took the microphone for the call.');
        _deleteQuietly(f);
        return null;
      }
      return f;
    } catch (e) {
      _note('Could not stop recording: $e');
      return null;
    } finally {
      await _stopAudioService();
    }
  }

  // ---- Capture --------------------------------------------------

  /// Find and upload the recording for a just-completed call.
  ///
  /// Tries the phone's own call-recorder folders first (full two-way audio).
  /// If none matches yet and [fallbackFile] (the in-app mic recording) is
  /// provided, uploads that — and keeps looking for the phone's file, which
  /// replaces it on the server when it turns up (it used to be dropped for
  /// good once the mic file was in). Safe to call fire-and-forget.
  ///
  /// [endedAt] is when the call really ended. Matching used to place the end
  /// at start + talk time, which is early by the whole ringing time, so the
  /// right file looked "too late" and a nameless one was rejected.
  Future<void> captureForCall({
    required String callId,
    required String phoneNumber,
    required DateTime startedAt,
    required int durationSec,
    DateTime? endedAt,
    String? leadName,
    String? contactName,
    File? fallbackFile,
  }) async {
    if (!await isEnabled()) {
      // Off in Profile → Call Recording. The single most common reason no
      // recording ever appears, and previously indistinguishable from failure.
      _note('Call recording is turned off in Profile.');
      _deleteQuietly(fallbackFile);
      return;
    }
    lastAttemptAt = DateTime.now();
    final end = endedAt ?? startedAt.add(Duration(seconds: durationSec));
    final job = _Job(
      callId: callId, phone: phoneNumber, startedAt: startedAt, endedAt: end,
      talkSec: durationSec, leadName: leadName ?? '', contactName: contactName ?? '',
    );

    final canScan = await hasStorageAccess();
    if (canScan) {
      // OEM recorders finalise the file a few seconds after the call ends.
      final attempts = fallbackFile != null ? 3 : 6;
      for (var attempt = 0; attempt < attempts; attempt++) {
        await Future.delayed(Duration(seconds: attempt == 0 ? 3 : 5));
        final match = await _findRecordingFile(job);
        if (match != null) {
          if (await _uploadMatch(callId, match)) {
            _cleanupCopy(match);
            _deleteQuietly(fallbackFile); // the phone's file wins
            return;
          }
          break; // found but not uploaded (offline): queue below
        }
      }
    }

    // No phone recording yet — upload the in-app mic recording if we have one.
    if (fallbackFile != null && fallbackFile.existsSync()) {
      final ok = await _uploadIfNew(callId, fallbackFile, 'mic_fallback');
      if (ok) _deleteQuietly(fallbackFile);
      // Keep looking for the phone's own file (it replaces the mic one), or
      // retry the mic upload later if it failed (offline).
      if (canScan || !ok) {
        await _enqueuePending(job, fallbackPath: ok ? null : fallbackFile.path, micUploaded: ok);
      }
      return;
    }

    // Nothing yet — remember the call so a later sweep can pick the file up
    // once the OEM recorder finishes writing it.
    await _enqueuePending(job);

    if (!canScan) {
      _note('No "All files access" — cannot read your phone\'s call-recorder '
          'folder, and no fallback recording was captured.');
    } else {
      _note('No recording yet; will keep checking in the background. Make sure '
          'call recording is enabled in your phone\'s Dialer app.');
    }
  }

  /// Queue the recording of a call saved by phone call tracking (a call the
  /// agent made or took outside the app's dialer) and look for it once now.
  /// The regular sweep keeps looking afterwards. Returns whether it was
  /// uploaded already.
  Future<bool> captureForSyncedCall({
    required String callId,
    required String phoneNumber,
    required DateTime startedAt,
    required int talkSec,
    String contactName = '',
    String leadName = '',
  }) async {
    if (!await isEnabled()) return false;
    final job = _Job(
      callId: callId, phone: phoneNumber, startedAt: startedAt,
      endedAt: startedAt.add(Duration(seconds: talkSec)),
      talkSec: talkSec, leadName: leadName, contactName: contactName,
    );
    if (await hasStorageAccess()) {
      final match = await _findRecordingFile(job);
      if (match != null && await _uploadMatch(callId, match)) {
        _cleanupCopy(match);
        return true;
      }
    }
    await _enqueuePending(job);
    return false;
  }

  // ---- Deferred sync -------------------------------------------

  Future<List<Map<String, dynamic>>> _readPending() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList(_pendingKey) ?? const <String>[];
    final out = <Map<String, dynamic>>[];
    for (final item in raw) {
      try {
        final decoded = jsonDecode(item);
        if (decoded is Map<String, dynamic>) out.add(decoded);
      } catch (_) {
        // Corrupt entry — drop it rather than poisoning every future sweep.
      }
    }
    return out;
  }

  Future<void> _writePending(List<Map<String, dynamic>> items) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(
      _pendingKey,
      items.map((e) => jsonEncode(e)).toList(),
    );
  }

  Future<void> _enqueuePending(_Job job, {String? fallbackPath, bool micUploaded = false}) async {
    final items = await _readPending();
    if (items.any((e) => e['callId'] == job.callId)) return;
    items.add({
      ...job.toJson(),
      'queuedAt': DateTime.now().toIso8601String(),
      if (fallbackPath != null) 'fallbackPath': fallbackPath,
      if (micUploaded) 'micUploaded': true,
    });
    // Bound the queue; oldest go first.
    if (items.length > 200) items.removeRange(0, items.length - 200);
    await _writePending(items);
  }

  /// How many calls are still waiting for a recording file (calls that
  /// already have the mic recording and are only waiting for an upgrade to
  /// the phone's file are not counted).
  Future<int> pendingCount() async =>
      (await _readPending()).where((e) => e['micUploaded'] != true).length;

  /// Re-scan the OEM folders for recordings belonging to earlier calls.
  ///
  /// This is what makes native-recorder capture actually reliable: the file
  /// usually is not there yet when the call ends, so one attempt at that
  /// moment loses it. Safe to call often — it does nothing when the queue is
  /// empty, and each file is uploaded for one call only.
  ///
  /// Returns the number of recordings uploaded.
  Future<int> sweepPending() async {
    if (!await isEnabled()) return 0;
    final items = await _readPending();
    if (items.isEmpty) return 0;
    // Without folder access the OEM scan is skipped, but queued microphone
    // recordings are still retried — they need no storage permission.
    final canScan = await hasStorageAccess();
    if (!canScan) {
      _note('No "All files access" — ${items.length} call(s) still waiting for '
          'their recording.');
    }

    final now = DateTime.now();
    final remaining = <Map<String, dynamic>>[];
    var uploaded = 0;

    for (final item in items) {
      final job = _Job.fromJson(item);
      if (job == null) continue; // unusable entry
      final queuedAt = DateTime.tryParse(item['queuedAt'] as String? ?? '');
      final fallbackPath = item['fallbackPath'] as String?;
      final micUploaded = item['micUploaded'] == true;
      // A call that already has the mic recording waits a day for the
      // phone's file; one with nothing waits three.
      final ttl = micUploaded ? const Duration(days: 1) : _pendingTtl;
      if (queuedAt != null && now.difference(queuedAt) > ttl) {
        if (fallbackPath != null) _deleteQuietly(File(fallbackPath));
        continue; // expired — stop looking
      }

      final match = canScan ? await _findRecordingFile(job) : null;
      if (match == null) {
        // A mic recording whose upload failed earlier: try it again, and keep
        // looking for the phone's own file afterwards.
        final fallback = fallbackPath == null ? null : File(fallbackPath);
        if (fallback != null && fallback.existsSync()) {
          if (await _uploadIfNew(job.callId, fallback, 'mic_fallback')) {
            uploaded++;
            _deleteQuietly(fallback);
            if (canScan) {
              remaining.add({...item, 'micUploaded': true}..remove('fallbackPath'));
            }
            continue;
          }
        }
        remaining.add(item);
        continue;
      }

      if (await _uploadMatch(job.callId, match)) {
        uploaded++;
        _cleanupCopy(match);
        // The phone's own recording won; the queued mic copy is not needed.
        if (fallbackPath != null) _deleteQuietly(File(fallbackPath));
      } else {
        remaining.add(item); // upload failed (offline?) — try again later
      }
    }

    await _writePending(remaining);
    if (uploaded > 0) lastError = null;
    return uploaded;
  }

  /// Every audio file under [dir], following dated subfolders a few levels
  /// deep. Returns [] rather than throwing on an unreadable directory — a
  /// permission-denied folder must not abort the whole scan.
  List<File> _listAudioFiles(Directory dir, {required int maxDepth}) {
    final found = <File>[];
    void walk(Directory d, int depth) {
      List<FileSystemEntity> entries;
      try {
        entries = d.listSync(recursive: false, followLinks: false);
      } catch (_) {
        return;
      }
      for (final e in entries) {
        if (e is File) {
          if (_audioExts.contains(_ext(e.path.split('/').last))) found.add(e);
        } else if (e is Directory && depth < maxDepth) {
          walk(e, depth + 1);
        }
      }
    }

    walk(dir, 0);
    return found;
  }

  /// Throw away a recording that must not be uploaded (an unanswered call).
  void discard(File? f) => _deleteQuietly(f);

  void _deleteQuietly(File? f) {
    if (f == null) return;
    try {
      if (f.existsSync()) f.deleteSync();
    } catch (_) {}
  }

  Future<_Match?> _findRecordingFile(_Job job) async {
    final roots = await _externalRoots();
    final used = await _usedFiles();

    // A file of this call was still being written when the call started, so
    // it can't have been finished before then: anything older belongs to an
    // earlier call (a redial to the same number used to pick up the previous
    // call's recording). The upper bound is generous — some recorders write
    // the file late — but nameless files are held to 20 s by the scorer.
    final windowStart = job.startedAt.subtract(const Duration(seconds: 5));
    final windowEnd = job.endedAt.add(const Duration(hours: 6));

    final candidates = <_Candidate>[];
    final seenPaths = <String>{};

    ({int score, String matchedBy})? score(String name, DateTime mtime, {double? seconds}) {
      ({int score, String matchedBy})? best;
      // The lead's name and the name the phone's contacts show for the
      // number: a recorder names the file after the contact.
      for (final who in {job.leadName, job.contactName}) {
        final r = scoreRecordingCandidate(
          fileName: name,
          modified: mtime,
          phoneNumber: job.phone,
          callEnd: job.endedAt,
          callStart: job.startedAt,
          leadName: who,
          fileDurationSec: seconds,
          talkSec: job.talkSec,
        );
        if (r != null && (best == null || r.score > best.score)) best = r;
      }
      return best;
    }

    // 1. Known call-recorder folders (needs "All files access" on most phones).
    for (final root in roots) {
      for (final rel in _candidateDirs) {
        final dir = Directory('${root.path}/$rel');
        if (!dir.existsSync()) continue;

        // Recursive: several OEMs bucket recordings into dated subfolders
        // (Recordings/Call/2026-09/...), which a flat listing never saw.
        // Depth-limited so a mis-detected root cannot walk the whole card.
        for (final e in _listAudioFiles(dir, maxDepth: 2)) {
          // The same folder can be reached twice (case-insensitive storage).
          if (!seenPaths.add(e.path.toLowerCase())) continue;
          FileStat stat;
          try {
            stat = e.statSync();
          } catch (_) {
            continue;
          }
          final mtime = stat.modified;
          if (mtime.isBefore(windowStart) || mtime.isAfter(windowEnd)) continue;
          if (stat.size < 1024) continue; // ignore empty/placeholder files
          if (used.contains(_fileKey(e))) continue; // already another call's

          final scored = score(e.path.split('/').last, mtime);
          if (scored != null) {
            candidates.add(_Candidate(
              file: e, name: e.path.split('/').last, mtime: mtime, scored: scored, size: stat.size,
            ));
          }
        }
      }
    }

    // 2. Android's media index: finds recordings in folders the list above
    //    doesn't know (every ROM update renames one), and works with only the
    //    audio permission — the Play Store build has no "All files access".
    for (final m in await _mediaStoreAudio(windowStart, windowEnd)) {
      final path = m['path'] as String? ?? '';
      final name = m['name'] as String? ?? '';
      final folder = m['folder'] as String? ?? '';
      if (path.isNotEmpty && !seenPaths.add(path.toLowerCase())) continue;
      final size = (m['size'] as num?)?.toInt() ?? 0;
      if (size < 1024) continue;
      final mtime = DateTime.fromMillisecondsSinceEpoch((m['modifiedMillis'] as num?)?.toInt() ?? 0);
      if (mtime.isBefore(windowStart) || mtime.isAfter(windowEnd)) continue;
      final durMs = (m['durationMs'] as num?)?.toInt() ?? -1;
      final seconds = durMs > 0 ? durMs / 1000.0 : null;
      final scored = score(name, mtime, seconds: seconds);
      if (scored == null) continue;
      // A file outside any call-recording folder is accepted only when its
      // name identifies the call. A voice memo saved right after a call must
      // not be taken for it on timing alone.
      if (scored.matchedBy == 'timestamp' && !looksLikeCallRecordingFolder('$folder/$name')) continue;
      final file = path.isEmpty ? null : File(path);
      if (file != null && used.contains(_fileKey(file))) continue;
      candidates.add(_Candidate(
        file: file, uri: m['uri'] as String?, name: name, mtime: mtime, scored: scored,
        seconds: seconds, size: size,
      ));
    }

    // 3. The folder the agent chose (their recorder's, or a recorder app's
    //    such as Cube ACR). Trusted like the known call-recorder folders: a
    //    nameless file written right at the end of the call counts.
    for (final m in await _folderAudio(windowStart, windowEnd)) {
      final name = m['name'] as String? ?? '';
      final size = (m['size'] as num?)?.toInt() ?? 0;
      if (size < 1024) continue;
      final mtime = DateTime.fromMillisecondsSinceEpoch((m['modifiedMillis'] as num?)?.toInt() ?? 0);
      final scored = score(name, mtime);
      if (scored == null) continue;
      candidates.add(_Candidate(
        file: null, uri: m['uri'] as String?, name: name, mtime: mtime, scored: scored, size: size,
      ));
    }

    // One physical file can be reached several ways (its folder, the media
    // index, the chosen folder): keep it once, and never reuse a file another
    // call already took.
    final seenIds = <String>{};
    candidates.removeWhere((c) => !seenIds.add(c.identity) || used.contains(c.identity));
    if (candidates.isEmpty) return null;

    // Check the best few against their real length: a file longer than the
    // whole call is another call's recording, and among the rest the one
    // closest to the talk time wins.
    candidates.sort((a, b) => b.scored.score.compareTo(a.scored.score));
    _Candidate? best;
    ({int score, String matchedBy})? bestScored;
    for (final c in candidates.take(5)) {
      final seconds = c.seconds ??
          (c.file != null && _readable(c.file!)
              ? await audioDurationSec(c.file!.path)
              : (c.uri != null ? await _uriDurationSec(c.uri!) : null));
      final rescored = score(c.name, c.mtime, seconds: seconds);
      if (rescored != null && (bestScored == null || rescored.score > bestScored.score)) {
        bestScored = rescored;
        best = c;
      }
    }
    if (best == null || bestScored == null) return null;

    // Readable where it is, or copied out through the media index / folder.
    if (best.file != null && _readable(best.file!)) {
      return _Match(best.file!, bestScored.matchedBy, sourceKey: best.identity, sourceName: best.name);
    }
    final uri = best.uri;
    if (uri == null || uri.isEmpty) return null;
    final copy = await _copyFromMediaStore(uri, best.name);
    if (copy == null) {
      _note('Found the recording "${best.name}" but Android would not let the app read it.');
      return null;
    }
    return _Match(copy, bestScored.matchedBy, isCopy: true, sourceKey: best.identity, sourceName: best.name);
  }

  static const _mediaChannel = MethodChannel('dialeasypro/call_log');

  Future<List<Map<String, dynamic>>> _mediaStoreAudio(DateTime from, DateTime to) async {
    if (!Platform.isAndroid) return const [];
    try {
      final raw = await _mediaChannel.invokeListMethod<dynamic>('findAudio', {
        'fromMillis': from.millisecondsSinceEpoch,
        'toMillis': to.millisecondsSinceEpoch,
      });
      return [
        for (final e in raw ?? const [])
          if (e is Map) e.map((k, v) => MapEntry(k.toString(), v)),
      ];
    } on MissingPluginException {
      return const [];
    } on PlatformException {
      return const [];
    }
  }

  Future<File?> _copyFromMediaStore(String uri, String name) async {
    try {
      final dir = await getApplicationSupportDirectory();
      final safe = name.replaceAll(RegExp(r'[^A-Za-z0-9._ +-]'), '_');
      final dest = '${dir.path}/rec_copy_${DateTime.now().millisecondsSinceEpoch}_$safe';
      final path = await _mediaChannel.invokeMethod<String>('copyAudio', {'uri': uri, 'dest': dest});
      return path == null ? null : File(path);
    } catch (_) {
      return null;
    }
  }

  bool _readable(File f) {
    try {
      final raf = f.openSync();
      raf.closeSync();
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> _uploadMatch(String callId, _Match m) =>
      _uploadIfNew(callId, m.file, m.matchedBy, sourceKey: m.sourceKey, sourceName: m.sourceName);

  void _cleanupCopy(_Match m) {
    if (m.isCopy) _deleteQuietly(m.file);
  }

  Future<bool> _uploadIfNew(String callId, File file, String matchedBy,
      {String? sourceKey, String? sourceName}) async {
    final prefs = await SharedPreferences.getInstance();
    final processed = prefs.getStringList(_processedKey) ?? <String>[];
    // The original file's identity: a copy made through the media index or
    // the chosen folder has a new path every time.
    final usedKey = sourceKey ?? _fileKey(file);
    final key = '$callId::$usedKey';
    if (processed.contains(key) || processed.contains('$callId::${file.path}')) return true;

    try {
      final dio = ApiClient.instance.dio;
      final name = sourceName ?? file.path.split('/').last;
      final seconds = await audioDurationSec(file.path);

      // Always through our own backend, which stores it with the server's
      // credentials. The app used to prefer a Cloudinary account typed into
      // the (since removed) voice-notes settings on the phone — customer call
      // audio went to whatever account an agent had entered, and after the
      // settings were removed there was no way to see or change it.
      final form = FormData.fromMap({
        'matched_by': matchedBy,
        'source_filename': name,
        if (seconds != null) 'duration_seconds': seconds.round().toString(),
        'file': await MultipartFile.fromFile(file.path, filename: name),
      });
      await dio.post('/calls/$callId/recording/', data: form);

      processed.add(key);
      // Keep the processed list bounded.
      if (processed.length > 500) {
        processed.removeRange(0, processed.length - 500);
      }
      await prefs.setStringList(_processedKey, processed);
      if (matchedBy != 'mic_fallback') {
        await _rememberUsed(usedKey);
        await _markOemSeen();
      }
      lastError = null;
      return true;
    } on DioException catch (e) {
      if (e.response?.statusCode == 422) {
        // The server refused the file itself (an empty mic recording):
        // nothing to retry.
        _note('Recording not kept: ${ApiClient.errorMessage(e)}');
        return true;
      }
      // The upload is the step most likely to fail in the field (no signal,
      // expired token) and it used to fail mute.
      _note('Upload failed: ${ApiClient.errorMessage(e)}');
      return false;
    } catch (e) {
      _note('Upload failed: $e');
      return false;
    }
  }

  // ---- Helpers --------------------------------------------------

  Future<List<Directory>> _externalRoots() async {
    final roots = <Directory>[];
    // Primary external storage.
    final primary = Directory('/storage/emulated/0');
    if (primary.existsSync()) roots.add(primary);
    // Scan /storage/* for SD cards / other volumes.
    try {
      final storage = Directory('/storage');
      if (storage.existsSync()) {
        for (final e in storage.listSync()) {
          if (e is Directory &&
              !e.path.endsWith('/emulated') &&
              !e.path.endsWith('/self')) {
            roots.add(e);
          }
        }
      }
    } catch (_) {}
    return roots;
  }

  String _ext(String name) {
    final i = name.lastIndexOf('.');
    return i < 0 ? '' : name.substring(i).toLowerCase();
  }
}

class _Match {
  final File file;
  final String matchedBy;
  /// A copy made through the media index, deleted after upload.
  final bool isCopy;
  /// Identity of the original file ("used once" bookkeeping) and its name.
  final String? sourceKey;
  final String? sourceName;
  _Match(this.file, this.matchedBy, {this.isCopy = false, this.sourceKey, this.sourceName});
}

class _Candidate {
  final File? file;
  final String? uri;
  final String name;
  final DateTime mtime;
  final ({int score, String matchedBy}) scored;
  final double? seconds;
  final int size;
  _Candidate({
    required this.file, this.uri, required this.name, required this.mtime,
    required this.scored, this.seconds, this.size = 0,
  });

  /// The same physical file, whichever way it was found: name, size and
  /// modification time to the second.
  String get identity => recordingIdentity(name, size, mtime);
}

/// One call waiting for its recording.
class _Job {
  final String callId;
  final String phone;
  final DateTime startedAt;
  final DateTime endedAt;
  final int talkSec;
  final String leadName;
  /// The name the phone's contacts show for the number (call log).
  final String contactName;

  _Job({
    required this.callId,
    required this.phone,
    required this.startedAt,
    required this.endedAt,
    required this.talkSec,
    required this.leadName,
    this.contactName = '',
  });

  Map<String, dynamic> toJson() => {
        'callId': callId,
        'phone': phone,
        'startedAt': startedAt.toIso8601String(),
        'endedAt': endedAt.toIso8601String(),
        'durationSec': talkSec,
        'leadName': leadName,
        'contactName': contactName,
      };

  /// Entries queued by older builds have no endedAt: start + talk time.
  static _Job? fromJson(Map<String, dynamic> m) {
    final callId = m['callId'] as String?;
    final started = DateTime.tryParse(m['startedAt'] as String? ?? '');
    if (callId == null || started == null) return null;
    final talk = (m['durationSec'] as num?)?.toInt() ?? 0;
    return _Job(
      callId: callId,
      phone: m['phone'] as String? ?? '',
      startedAt: started,
      endedAt: DateTime.tryParse(m['endedAt'] as String? ?? '') ?? started.add(Duration(seconds: talk)),
      talkSec: talk,
      leadName: m['leadName'] as String? ?? '',
      contactName: m['contactName'] as String? ?? '',
    );
  }
}

/// One recording file's identity across the ways it can be found (its
/// folder, the media index, the folder the agent chose).
String recordingIdentity(String name, int size, DateTime modified) =>
    'id:${name.toLowerCase()}|$size|${modified.millisecondsSinceEpoch ~/ 1000}';

/// The Google Phone app. Its call recordings are stored inside the app,
/// out of reach of every other app, so nothing can collect them.
bool isGoogleDialer(String dialerPackage) =>
    dialerPackage.trim().toLowerCase() == 'com.google.android.dialer';

/// Whether a folder/file path looks like a call recorder's (as opposed to a
/// voice recorder's or music).
bool looksLikeCallRecordingFolder(String path) {
  final p = path.toLowerCase();
  if (p.contains('voice recorder') || p.contains('voicerecorder') || p.contains('voice memo')) return false;
  return p.contains('call') || p.contains('phonerecord') || p.contains('voice_call');
}

/// Brands whose phones ship with a call recorder of their own. On these the
/// app leaves the microphone alone (see shouldUseMicFallback).
bool brandHasCallRecorder(PhoneBrand brand) => const {
      PhoneBrand.samsung,
      PhoneBrand.xiaomi,
      PhoneBrand.vivo,
      PhoneBrand.oppoRealme,
      PhoneBrand.transsion,
    }.contains(brand);

/// Whether a run of digits in a file name is a date-time stamp near the call
/// (e.g. "2610141413" = 2026-10-14 14:13) rather than a phone number.
///
/// Recorders that name files "<contact>-yyMMddHHmm" put a ten-digit stamp in
/// the name; it was read as somebody else's phone number and the file was
/// thrown away.
bool looksLikeTimestamp(String run, DateTime near) {
  DateTime? parse(String y, String mo, String d, String h, String mi, [String s = '0']) {
    final year = int.parse(y.length == 2 ? '20$y' : y);
    final month = int.parse(mo), day = int.parse(d), hour = int.parse(h), minute = int.parse(mi);
    final second = int.parse(s);
    if (month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59 || second > 59) {
      return null;
    }
    return DateTime(year, month, day, hour, minute, second);
  }

  final candidates = <DateTime?>[];
  String p(int a, int b) => run.substring(a, b);
  try {
    switch (run.length) {
      case 10: // yyMMddHHmm
        candidates.add(parse(p(0, 2), p(2, 4), p(4, 6), p(6, 8), p(8, 10)));
      case 12: // yyMMddHHmmss or yyyyMMddHHmm
        candidates.add(parse(p(0, 2), p(2, 4), p(4, 6), p(6, 8), p(8, 10), p(10, 12)));
        candidates.add(parse(p(0, 4), p(4, 6), p(6, 8), p(8, 10), p(10, 12)));
      case 14: // yyyyMMddHHmmss
        candidates.add(parse(p(0, 4), p(4, 6), p(6, 8), p(8, 10), p(10, 12), p(12, 14)));
    }
  } catch (_) {
    return false;
  }
  return candidates.any((t) => t != null && t.difference(near).abs() <= const Duration(days: 2));
}

/// How well an audio file matches a call, or null when it must not be used.
///
/// * The call's number in the name: strong match.
/// * The lead's name in the name (the number saved as a contact): strong.
/// * A different phone number in the name: never used.
/// * Nothing identifying: used only when written within 20 seconds of the
///   call's real end.
/// * [fileDurationSec], when known: a file longer than the whole call can't
///   be its recording; the closer to the talk time, the better.
({int score, String matchedBy})? scoreRecordingCandidate({
  required String fileName,
  required DateTime modified,
  required String phoneNumber,
  required DateTime callEnd,
  DateTime? callStart,
  String leadName = '',
  double? fileDurationSec,
  int talkSec = 0,
}) {
  String last10(String s) {
    final d = s.replaceAll(RegExp(r'[^0-9]'), '');
    return d.length > 10 ? d.substring(d.length - 10) : d;
  }

  // Longer than the call itself (plus slack for the recorder's start/stop).
  if (fileDurationSec != null && callStart != null) {
    final span = callEnd.difference(callStart).inSeconds;
    if (span > 0 && fileDurationSec > span + 15) return null;
  }
  var lengthBonus = 0;
  if (fileDurationSec != null && talkSec > 0) {
    lengthBonus = 30 - (fileDurationSec - talkSec).abs().round().clamp(0, 30);
  }

  final wanted = last10(phoneNumber);
  // Digit runs of 10-12 look like phone numbers (10 digits, or with 91 / 0
  // in front) — unless they read as a date-time near the call. Longer runs
  // are timestamps (20260929143205) and are ignored.
  final runs = RegExp(r'\d+').allMatches(fileName).map((m) => m.group(0)!);
  final numbersInName = runs
      .where((r) => r.length >= 10 && r.length <= 12 && !looksLikeTimestamp(r, callEnd))
      .map(last10)
      .toList();
  final delta = modified.difference(callEnd).inSeconds.abs();
  final nearBonus = delta <= 90 ? 90 - delta : 0;

  // The call's number anywhere in the name, even spaced out
  // ("Call +91 98123 00001 ...").
  final allDigits = fileName.replaceAll(RegExp(r'[^0-9]'), '');
  if (wanted.length == 10 && (numbersInName.contains(wanted) || allDigits.contains(wanted))) {
    return (score: 200 + nearBonus + lengthBonus, matchedBy: 'filename_number');
  }
  if (numbersInName.isNotEmpty) return null; // named with someone else's number

  // The lead's name, when the number is saved as a contact and the recorder
  // names the file after it ("Ravi Kumar_241017_143205.m4a").
  final letters = RegExp(r'[^a-z]');
  final wantedName = leadName.toLowerCase().replaceAll(letters, '');
  final nameInFile = fileName.toLowerCase().replaceAll(letters, '');
  if (wantedName.length >= 4 && nameInFile.contains(wantedName) && delta <= 15 * 60) {
    return (score: 150 + nearBonus + lengthBonus, matchedBy: 'filename_name');
  }

  if (delta > 20) return null;
  return (score: 20 + (20 - delta) + lengthBonus, matchedBy: 'timestamp');
}
