import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

// ============================================================
// DialEasypro — Permissions Service
// Centralized handling for all runtime permissions
// ============================================================

class PermissionsService {
  PermissionsService._();
  static final PermissionsService instance = PermissionsService._();

  /// Permissions required for the app's core dialer features
  static const List<Permission> _required = [
    Permission.phone,         // CALL_PHONE — direct dial
    Permission.microphone,    // RECORD_AUDIO — voice notes
    Permission.notification,  // Reminders
  ];

  /// Optional permissions
  static const List<Permission> _optional = [
    Permission.contacts,      // Import device contacts
    Permission.storage,       // Save call lists, exports
  ];

  /// Request all required permissions on first launch
  Future<Map<Permission, PermissionStatus>> requestAllOnboarding() async {
    final result = await [..._required, ..._optional].request();
    return result;
  }

  /// Check if all required permissions are granted
  Future<bool> hasAllRequired() async {
    for (final p in _required) {
      if (!await p.isGranted) return false;
    }
    return true;
  }

  Future<bool> requestCallPermission() async {
    final s = await Permission.phone.request();
    return s.isGranted;
  }

  Future<bool> requestMicrophonePermission() async {
    final s = await Permission.microphone.request();
    return s.isGranted;
  }

  /// Show settings if user has permanently denied
  Future<void> openSettings() async {
    await openAppSettings();
  }

  /// Show a friendly permission request dialog before system prompt
  static Future<bool> showPermissionRationale(
    BuildContext context, {
    required String title,
    required String message,
    required IconData icon,
  }) async {
    return await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: Icon(icon, size: 36, color: Colors.amber),
        title: Text(title, style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700)),
        content: Text(message, style: const TextStyle(fontFamily: 'DMSans')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Not now')),
          ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Allow')),
        ],
      ),
    ) ?? false;
  }
}
