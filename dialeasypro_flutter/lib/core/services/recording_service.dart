import 'dart:async';
import 'dart:io';
import 'package:cloudinary_public/cloudinary_public.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';
import 'package:uuid/uuid.dart';

// ============================================================
// DialEasypro — Voice Recording Service
// Records voice notes during/after calls; uploads to Cloudinary.
//
// NOTE on call recording: Android 10+ blocks third-party apps from
// recording cellular calls via MediaRecorder/AudioRecord. The PROPER
// way to record calls in a production CRM is server-side recording
// via your telephony provider (Exotel/Knowlarity/MCUBE). Click-to-call
// API triggers the call through the provider, which records server-side
// and stores the recording URL in CallRecording.playback_url.
//
// This service handles VOICE NOTES (agent's voice memo about a call/lead),
// not the call audio itself.
// ============================================================

class VoiceRecorderService {
  VoiceRecorderService._();
  static final VoiceRecorderService instance = VoiceRecorderService._();

  final _recorder = AudioRecorder();
  CloudinaryPublic? _cloudinary;
  String? _currentPath;
  bool _isRecording = false;

  bool get isRecording => _isRecording;
  String? get currentPath => _currentPath;

  /// Configure Cloudinary — call once during app init.
  /// Use unsigned upload preset for client-side uploads.
  void configure({required String cloudName, required String uploadPreset}) {
    _cloudinary = CloudinaryPublic(cloudName, uploadPreset, cache: false);
  }

  Future<bool> hasPermission() async {
    return await Permission.microphone.isGranted;
  }

  Future<bool> requestPermission() async {
    final s = await Permission.microphone.request();
    return s.isGranted;
  }

  /// Start recording a voice note
  Future<bool> start() async {
    if (_isRecording) return false;
    if (!await hasPermission()) {
      if (!await requestPermission()) return false;
    }

    try {
      final dir = await getTemporaryDirectory();
      final filename = 'voice_${const Uuid().v4()}.m4a';
      _currentPath = '${dir.path}/$filename';

      await _recorder.start(
        const RecordConfig(
          encoder: AudioEncoder.aacLc,
          bitRate: 64000,
          sampleRate: 22050,
        ),
        path: _currentPath!,
      );
      _isRecording = true;
      return true;
    } catch (e) {
      _isRecording = false;
      return false;
    }
  }

  /// Stop recording and return the file path
  Future<String?> stop() async {
    if (!_isRecording) return null;
    try {
      final path = await _recorder.stop();
      _isRecording = false;
      _currentPath = path;
      return path;
    } catch (_) {
      _isRecording = false;
      return null;
    }
  }

  /// Cancel current recording
  Future<void> cancel() async {
    try {
      await _recorder.stop();
      if (_currentPath != null) {
        final f = File(_currentPath!);
        if (await f.exists()) await f.delete();
      }
    } catch (_) {}
    _isRecording = false;
    _currentPath = null;
  }

  /// Upload a recorded file to Cloudinary, returns the URL
  Future<String?> uploadToCloudinary(String filePath, {String folder = 'dialeasypro/voice_notes'}) async {
    if (_cloudinary == null) {
      throw Exception('Cloudinary not configured. Call configure() first.');
    }
    try {
      final file = File(filePath);
      if (!await file.exists()) return null;

      final response = await _cloudinary!.uploadFile(
        CloudinaryFile.fromFile(
          filePath,
          resourceType: CloudinaryResourceType.Auto,
          folder: folder,
        ),
      );
      return response.secureUrl;
    } catch (_) {
      return null;
    }
  }
}
