import 'dart:io';

import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

// ============================================================
// DialEasypro — First-run setup
//
// An agent who installs the app and starts dialling without granting anything
// gets a CRM that logs calls and records none of them, silently. This drives
// the one-time walkthrough that prevents that.
//
// The awkward part is call recording. Android gives no API to switch a
// phone's call recorder on, and every OEM buries it somewhere different — so
// the app can open the right screen (best effort) but the agent has to flip
// the switch. Per-brand instructions below are the reliable half of that; the
// deep link is a convenience that may or may not land.
// ============================================================

enum PhoneBrand { samsung, xiaomi, vivo, oppoRealme, transsion, motorola, google, other }

class BrandGuide {
  final PhoneBrand brand;
  final String label;

  /// What the agent should look for. Written as "look for this", not as a
  /// fixed menu path, because OEM menus are renamed between ROM versions and
  /// a stale path is worse than a description.
  final List<String> recordingSteps;

  /// Whether this brand kills background apps unless whitelisted. Xiaomi,
  /// Vivo, Oppo/Realme and Transsion do; the recording sweep and presence
  /// heartbeat stop working without it.
  final bool needsAutoStart;

  const BrandGuide({
    required this.brand,
    required this.label,
    required this.recordingSteps,
    this.needsAutoStart = false,
  });
}

class SetupService {
  SetupService._();
  static final SetupService instance = SetupService._();

  static const _channel = MethodChannel('dialeasypro/setup');
  static const _completedKey = 'setup_completed_v1';

  Map<String, dynamic>? _cachedInfo;
  bool? _completeCache;

  // ---- Completion flag -------------------------------------------

  /// Synchronous view for the router's redirect, which cannot await.
  ///
  /// Defaults to `true` when not yet loaded: showing the dashboard a moment
  /// early is recoverable, whereas bouncing an already-configured agent into
  /// the wizard on every cold start is not.
  bool get isCompleteSync => _completeCache ?? true;

  /// Read the flag before the first route is built. Called from main().
  Future<void> preload() async {
    _completeCache = await isComplete();
  }

  Future<bool> isComplete() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_completedKey) ?? false;
  }

  /// Marked when the agent finishes (or deliberately skips) the wizard. The
  /// key is versioned so a future release that needs a new permission can run
  /// the walkthrough again instead of assuming old installs are set up.
  Future<void> markComplete() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_completedKey, true);
    _completeCache = true;
  }

  Future<void> resetForTesting() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_completedKey);
    _completeCache = false;
  }

  // ---- Device ----------------------------------------------------

  Future<Map<String, dynamic>> deviceInfo() async {
    if (_cachedInfo != null) return _cachedInfo!;
    if (!Platform.isAndroid) return _cachedInfo = const {};
    try {
      final raw = await _channel.invokeMapMethod<String, dynamic>('deviceInfo');
      return _cachedInfo = (raw ?? const {});
    } on PlatformException {
      return _cachedInfo = const {};
    } on MissingPluginException {
      return _cachedInfo = const {};
    }
  }

  Future<BrandGuide> guide() async {
    final info = await deviceInfo();
    final key = '${info['manufacturer'] ?? ''} ${info['brand'] ?? ''}'.toLowerCase();
    return guideFor(key);
  }

  /// Split out from [guide] so the brand table is testable without a device.
  static BrandGuide guideFor(String manufacturerAndBrand) {
    final k = manufacturerAndBrand.toLowerCase();

    if (k.contains('samsung')) {
      return const BrandGuide(
        brand: PhoneBrand.samsung,
        label: 'Samsung',
        recordingSteps: [
          'Open the Phone app, tap the three dots, then Settings.',
          'Tap "Record calls".',
          'Turn on "Auto record calls".',
        ],
      );
    }
    if (k.contains('xiaomi') || k.contains('redmi') || k.contains('poco')) {
      return const BrandGuide(
        brand: PhoneBrand.xiaomi,
        label: 'Xiaomi / Redmi / POCO',
        recordingSteps: [
          'Open the Phone app, tap the three dots, then Settings.',
          'Tap "Call recording".',
          'Turn on "Record calls automatically".',
        ],
        needsAutoStart: true,
      );
    }
    if (k.contains('vivo') || k.contains('iqoo')) {
      return const BrandGuide(
        brand: PhoneBrand.vivo,
        label: 'Vivo / iQOO',
        recordingSteps: [
          'Open the Phone app, then its Settings.',
          'Tap "Call recording".',
          'Turn on automatic recording for all calls.',
        ],
        needsAutoStart: true,
      );
    }
    if (k.contains('oppo') || k.contains('realme') || k.contains('oneplus')) {
      return const BrandGuide(
        brand: PhoneBrand.oppoRealme,
        label: 'Oppo / Realme / OnePlus',
        recordingSteps: [
          'Open the Phone app, then Settings.',
          'Tap "Call recording".',
          'Turn on "Automatically record calls" and choose All calls.',
        ],
        needsAutoStart: true,
      );
    }
    if (k.contains('infinix') || k.contains('tecno') || k.contains('itel') ||
        k.contains('transsion')) {
      return const BrandGuide(
        brand: PhoneBrand.transsion,
        label: 'Infinix / Tecno / itel',
        recordingSteps: [
          'Open the Phone app, tap the three dots, then Settings.',
          'Look for "Call recording" or "Auto record".',
          'Turn it on for all calls.',
        ],
        needsAutoStart: true,
      );
    }
    if (k.contains('motorola') || k.contains('moto') || k.contains('lenovo')) {
      return const BrandGuide(
        brand: PhoneBrand.motorola,
        label: 'Motorola',
        recordingSteps: [
          'Motorola uses the Google Phone app.',
          'Open Phone, tap the three dots, then Settings.',
          'Tap "Call recording" and turn it on. If that entry is missing, your '
              'region or carrier does not allow it — the app will record through '
              'the microphone instead.',
        ],
      );
    }
    if (k.contains('google') || k.contains('pixel')) {
      return const BrandGuide(
        brand: PhoneBrand.google,
        label: 'Google Pixel',
        recordingSteps: [
          'Open Phone, tap the three dots, then Settings.',
          'Tap "Call recording" if it is present.',
          'Many Pixels have no call recorder at all. The app will record '
              'through the microphone — put calls on speaker to capture both sides.',
        ],
      );
    }
    return const BrandGuide(
      brand: PhoneBrand.other,
      label: 'your phone',
      recordingSteps: [
        'Open the Phone app and find its Settings.',
        'Look for "Call recording", "Record calls" or "Auto record".',
        'Turn on automatic recording for all calls. If there is no such '
            'setting, the app records through the microphone instead.',
      ],
    );
  }

  // ---- OEM screens (best effort) ---------------------------------

  /// Where the agent ended up: 'settings' | 'dialer' | 'app_info' | 'none'.
  Future<String> openCallRecordingSettings() =>
      _invoke<String>('openCallRecordingSettings', 'none');

  Future<bool> isIgnoringBatteryOptimizations() =>
      _invoke<bool>('isIgnoringBatteryOptimizations', true);

  Future<bool> requestIgnoreBatteryOptimizations() =>
      _invoke<bool>('requestIgnoreBatteryOptimizations', false);

  Future<bool> openAutoStartSettings() =>
      _invoke<bool>('openAutoStartSettings', false);

  Future<T> _invoke<T>(String method, T fallback) async {
    if (!Platform.isAndroid) return fallback;
    try {
      return await _channel.invokeMethod<T>(method) ?? fallback;
    } on PlatformException {
      return fallback;
    } on MissingPluginException {
      // App shell predates this channel.
      return fallback;
    }
  }
}
