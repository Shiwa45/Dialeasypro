import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'core/services/phone_service.dart';
import 'core/services/recording_service.dart';
import 'core/services/tenant_config.dart';
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
    systemNavigationBarColor: Color(0xFFF5F4F0),
    systemNavigationBarIconBrightness: Brightness.dark,
  ));

  // Hive (local cache)
  await Hive.initFlutter();

  // Tenant config — MUST load before any API call
  await TenantConfig.instance.load();

  // Phone service — listens to system call state
  await PhoneService.instance.init();

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
