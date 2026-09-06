import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

import 'package:cloudinary_public/cloudinary_public.dart';
import 'package:dio/dio.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../data/services/api_client.dart';

// ============================================================
// DialEasypro — Call Recording Service (SIM-based)
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
    'Sounds',
    'MIUI/sound_recorder/call_rec',      // Xiaomi MIUI
    'MIUI/sound_recorder/call_recorder',
    'Recorder/call',                     // Xiaomi newer
    'Android/data/com.android.soundrecorder/files',
    'Music/Recordings/Call Recordings',  // Samsung (older)
    'Recordings/Voice Recorder',
    'Record/Call',                       // Oppo/Realme/OnePlus (ColorOS)
    'Music/Recordings',
    'DCIM/Call',
    'voice_call',                        // Vivo Funtouch
    'record/call',
  ];

  static const _audioExts = {'.m4a', '.mp3', '.amr', '.wav', '.aac', '.3gp', '.ogg', '.mp4'};

  // ---- Settings -------------------------------------------------

  Future<bool> isEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_enabledKey) ?? false;
  }

  Future<void> setEnabled(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_enabledKey, value);
  }

  // ---- Permissions ----------------------------------------------

  /// Whether we currently have the access needed to read recording folders.
  Future<bool> hasStorageAccess() async {
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

      final dir = await getTemporaryDirectory();
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
  /// Tries the phone's OEM call-recorder folders first (full two-way audio).
  /// If no OEM file matches and [fallbackFile] (the in-app mic recording) is
  /// provided, uploads that instead — so every device ends up with SOME
  /// recording. Safe to call fire-and-forget.
  Future<void> captureForCall({
    required String callId,
    required String phoneNumber,
    required DateTime startedAt,
    required int durationSec,
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

    // OEM folder scan needs storage access; the mic fallback does not.
    if (await hasStorageAccess()) {
      // Retry window: OEM recorders finalise the file a few seconds after the
      // call ends. Fewer retries when we hold a fallback anyway.
      final attempts = fallbackFile != null ? 3 : 6;
      for (var attempt = 0; attempt < attempts; attempt++) {
        await Future.delayed(Duration(seconds: attempt == 0 ? 4 : 5));
        final match = await _findRecordingFile(
          phoneNumber: phoneNumber,
          startedAt: startedAt,
          durationSec: durationSec,
        );
        if (match != null) {
          await _uploadIfNew(callId, match.file, match.matchedBy);
          _deleteQuietly(fallbackFile); // OEM file wins
          return;
        }
      }
    }

    // No OEM recording found — upload the in-app mic recording if we have one.
    if (fallbackFile != null && fallbackFile.existsSync()) {
      final ok = await _uploadIfNew(callId, fallbackFile, 'mic_fallback');
      if (ok) {
        lastError = null;
        _deleteQuietly(fallbackFile); // keep the file when upload failed
      }
      return;
    }

    // Nothing yet — remember the call so a later sweep can pick the file up
    // once the OEM recorder finishes writing it.
    await _enqueuePending(
      callId: callId,
      phoneNumber: phoneNumber,
      startedAt: startedAt,
      durationSec: durationSec,
    );

    if (!await hasStorageAccess()) {
      _note('No "All files access" — cannot read your phone\'s call-recorder '
          'folder, and no fallback recording was captured.');
    } else {
      _note('No recording yet; will keep checking in the background. Make sure '
          'call recording is enabled in your phone\'s Dialer app.');
    }
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

  Future<void> _enqueuePending({
    required String callId,
    required String phoneNumber,
    required DateTime startedAt,
    required int durationSec,
  }) async {
    final items = await _readPending();
    if (items.any((e) => e['callId'] == callId)) return;
    items.add({
      'callId': callId,
      'phone': phoneNumber,
      'startedAt': startedAt.toIso8601String(),
      'durationSec': durationSec,
      'queuedAt': DateTime.now().toIso8601String(),
    });
    // Bound the queue; oldest go first.
    if (items.length > 200) items.removeRange(0, items.length - 200);
    await _writePending(items);
  }

  /// How many calls are still waiting for a recording file.
  Future<int> pendingCount() async => (await _readPending()).length;

  /// Re-scan the OEM folders for recordings belonging to earlier calls.
  ///
  /// This is what makes native-recorder capture actually reliable: the file
  /// usually is not there yet when the call ends, so one attempt at that
  /// moment loses it. Safe to call often — it does nothing when the queue is
  /// empty, and each upload is deduplicated by callId+path.
  ///
  /// Returns the number of recordings uploaded.
  Future<int> sweepPending() async {
    if (!await isEnabled()) return 0;
    final items = await _readPending();
    if (items.isEmpty) return 0;
    if (!await hasStorageAccess()) {
      _note('No "All files access" — ${items.length} call(s) still waiting for '
          'their recording.');
      return 0;
    }

    final now = DateTime.now();
    final remaining = <Map<String, dynamic>>[];
    var uploaded = 0;

    for (final item in items) {
      final callId = item['callId'] as String?;
      final phone = item['phone'] as String? ?? '';
      final startedAt = DateTime.tryParse(item['startedAt'] as String? ?? '');
      final queuedAt = DateTime.tryParse(item['queuedAt'] as String? ?? '');
      final durationSec = (item['durationSec'] as num?)?.toInt() ?? 0;

      if (callId == null || startedAt == null) continue; // unusable entry
      if (queuedAt != null && now.difference(queuedAt) > _pendingTtl) {
        continue; // expired — stop looking
      }

      final match = await _findRecordingFile(
        phoneNumber: phone,
        startedAt: startedAt,
        durationSec: durationSec,
      );
      if (match == null) {
        remaining.add(item);
        continue;
      }

      if (await _uploadIfNew(callId, match.file, match.matchedBy)) {
        uploaded++;
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

  void _deleteQuietly(File? f) {
    if (f == null) return;
    try {
      if (f.existsSync()) f.deleteSync();
    } catch (_) {}
  }

  Future<_Match?> _findRecordingFile({
    required String phoneNumber,
    required DateTime startedAt,
    required int durationSec,
  }) async {
    final roots = await _externalRoots();
    final last10 = _digits(phoneNumber);
    final last10Short = last10.length > 10 ? last10.substring(last10.length - 10) : last10;

    // The recording should have been created during/just after the call.
    final windowStart = startedAt.subtract(const Duration(minutes: 2));
    final windowEnd = DateTime.now().add(const Duration(seconds: 30));

    _Match? best;
    int bestScore = 0;

    for (final root in roots) {
      for (final rel in _candidateDirs) {
        final dir = Directory('${root.path}/$rel');
        if (!dir.existsSync()) continue;

        // Recursive: several OEMs bucket recordings into dated subfolders
        // (Recordings/Call/2026-09/...), which a flat listing never saw.
        // Depth-limited so a mis-detected root cannot walk the whole card.
        final entries = _listAudioFiles(dir, maxDepth: 2);

        for (final e in entries) {
          final name = e.path.split('/').last;

          FileStat stat;
          try {
            stat = e.statSync();
          } catch (_) {
            continue;
          }
          final mtime = stat.modified;
          if (mtime.isBefore(windowStart) || mtime.isAfter(windowEnd)) continue;
          if (stat.size < 1024) continue; // ignore empty/placeholder files

          // Score the candidate.
          int score = 0;
          String matchedBy = 'timestamp';

          // Strong signal: phone number embedded in filename.
          final nameDigits = _digits(name);
          if (last10Short.isNotEmpty && nameDigits.contains(last10Short)) {
            score += 100;
            matchedBy = 'filename_number';
          }

          // Time proximity to call end (closer = better).
          final callEnd = startedAt.add(Duration(seconds: durationSec));
          final deltaSec = (mtime.difference(callEnd).inSeconds).abs();
          if (deltaSec <= 90) score += (90 - deltaSec); // up to +90

          if (score > bestScore) {
            bestScore = score;
            best = _Match(e, matchedBy);
          }
        }
      }
    }

    // Require at least a reasonable match (number match, or tight time window).
    if (best != null && bestScore >= 20) return best;
    return null;
  }

  Future<bool> _uploadIfNew(String callId, File file, String matchedBy) async {
    final prefs = await SharedPreferences.getInstance();
    final processed = prefs.getStringList(_processedKey) ?? <String>[];
    final key = '$callId::${file.path}';
    if (processed.contains(key)) return true;

    try {
      final dio = ApiClient.instance.dio;
      final name = file.path.split('/').last;

      // Preferred: upload directly to Cloudinary using the workspace's
      // configured cloud name + unsigned preset (same setup as voice notes),
      // then just LINK the resulting URL on the backend. This avoids streaming
      // large audio through our own server and needs no server-side creds.
      final cloudName = prefs.getString('cloudinary_name') ?? '';
      final preset = prefs.getString('cloudinary_preset') ?? '';

      if (cloudName.isNotEmpty && preset.isNotEmpty) {
        final cloudinary = CloudinaryPublic(cloudName, preset, cache: false);
        final res = await cloudinary.uploadFile(
          CloudinaryFile.fromFile(
            file.path,
            resourceType: CloudinaryResourceType.Auto,
            folder: 'dialeasypro/call_recordings',
          ),
        );
        await dio.post('/calls/$callId/recording/', data: {
          'cloud_url': res.secureUrl,
          'cloud_public_id': res.publicId,
          'source_filename': name,
          'matched_by': matchedBy,
          'format': _ext(name).replaceAll('.', ''),
        });
      } else {
        // Fallback: stream the raw file to the backend, which uploads it to
        // Cloudinary using server-side credentials.
        final form = FormData.fromMap({
          'matched_by': matchedBy,
          'source_filename': name,
          'file': await MultipartFile.fromFile(file.path, filename: name),
        });
        await dio.post('/calls/$callId/recording/', data: form);
      }

      processed.add(key);
      // Keep the processed list bounded.
      if (processed.length > 500) {
        processed.removeRange(0, processed.length - 500);
      }
      await prefs.setStringList(_processedKey, processed);
      lastError = null;
      return true;
    } on DioException catch (e) {
      // The upload is the step most likely to fail in the field (no signal,
      // expired token, Cloudinary preset wrong) and it used to fail mute.
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

  String _digits(String s) => s.replaceAll(RegExp(r'[^0-9]'), '');

  String _ext(String name) {
    final i = name.lastIndexOf('.');
    return i < 0 ? '' : name.substring(i).toLowerCase();
  }
}

class _Match {
  final File file;
  final String matchedBy;
  _Match(this.file, this.matchedBy);
}
