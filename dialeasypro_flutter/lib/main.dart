import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'core/services/phone_service.dart';
import 'core/services/setup_service.dart';
import 'core/services/recording_service.dart';
import 'core/services/tenant_config.dart';
import 'core/services/notification_service.dart';
import 'app.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Orientation lock — portrait only
  await SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);

  // Status bar style
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.dark,
    // Deep green, so the phone's own nav bar continues the bottom bar.
    systemNavigationBarColor: Color(0xFF062A20),
    systemNavigationBarIconBrightness: Brightness.light,
  ));

  // Everything below is local setup: preferences, a cache, a stream
  // subscription. None of it may block on a person, and none of it is worth
  // an unusable app if it fails — an uncaught throw here shows the same black
  // screen as a hang, with no clue which line did it.
  try {
    // Hive (local cache)
    await Hive.initFlutter();

    // Tenant config — MUST load before any API call
    await TenantConfig.instance.load();

    // Phone service — listens to system call state
    await PhoneService.instance.init();

    // First-run flag, read before the router builds its first route.
    await SetupService.instance.preload();
  } catch (e, st) {
    debugPrint('[main] startup step failed, continuing: $e');
    debugPrint('$st');
  }

  // Notifications: wiring only, and deliberately NOT awaited.
  //
  // This used to await the full init, which included the permission prompts.
  // requestExactAlarmsPermission opens a system settings screen, so the app
  // hung on a black screen waiting for a prompt behind a UI that had not
  // been drawn. Nothing before runApp may wait on a person.
  //
  // The prompts now live in requestPermissions(), called by the setup wizard
  // and after login. Every other entry point on the service calls init()
  // itself, so a notification arriving before this finishes still works.
  unawaited(NotificationService.instance.init().catchError((Object e) {
    debugPrint('[main] notification init failed: $e');
  }));

  // Cloudinary — load saved config (if user has set it in Profile)
  try {
    final prefs = await SharedPreferences.getInstance();
    final cloudName = prefs.getString('cloudinary_name');
    final preset = prefs.getString('cloudinary_preset');
    if (cloudName != null && cloudName.isNotEmpty && preset != null && preset.isNotEmpty) {
      VoiceRecorderService.instance.configure(cloudName: cloudName, uploadPreset: preset);
    }
  } catch (_) {}

  runApp(const ProviderScope(child: DialEasyproApp()));
}
