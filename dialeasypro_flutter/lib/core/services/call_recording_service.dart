import 'dart:async';
import 'dart:io';

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

  /// Start recording the microphone for the current call. Fire-and-forget;
  /// self-guards on the enabled flag and mic permission.
  Future<void> startMicCapture() async {
    if (_micActive) return;
    if (!await isEnabled()) return;
    try {
      if (!await _micRecorder.hasPermission()) return;
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
    } catch (_) {
      _micActive = false;
      _micPath = null;
    }
  }

  /// Stop the mic recording and return the file if it captured real audio.
  Future<File?> stopMicCapture() async {
    if (!_micActive) return null;
    _micActive = false;
    try {
      final path = await _micRecorder.stop();
      final f = File(path ?? _micPath ?? '');
      // Ignore tiny files (mic was silenced by the OS or call never connected).
      if (f.existsSync() && f.statSync().size > 4096) return f;
    } catch (_) {}
    return null;
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
      _deleteQuietly(fallbackFile);
      return;
    }

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
      if (ok) _deleteQuietly(fallbackFile); // keep the file when upload failed
    }
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

        List<FileSystemEntity> entries;
        try {
          entries = dir.listSync(recursive: false, followLinks: false);
        } catch (_) {
          continue;
        }

        for (final e in entries) {
          if (e is! File) continue;
          final name = e.path.split('/').last;
          final ext = _ext(name);
          if (!_audioExts.contains(ext)) continue;

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
      return true;
    } catch (_) {
      // Leave unmarked so a later sync can retry.
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
