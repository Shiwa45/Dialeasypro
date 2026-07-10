import 'package:dio/dio.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../data/services/api_client.dart';

// ============================================================
// DialEasypro — WhatsApp Service
// Native (open device WhatsApp) + Cloud (org's WhatsApp Cloud API)
// ============================================================

enum WhatsAppMode { native, cloud }

class WhatsAppService {
  WhatsAppService._();
  static final WhatsAppService instance = WhatsAppService._();

  /// Open native WhatsApp app with pre-filled message
  /// Uses wa.me URL which works on Android/iOS without requiring WhatsApp specifically installed
  Future<bool> sendNative({
    required String phoneNumber,
    String? message,
  }) async {
    final normalized = _normalizeForWhatsApp(phoneNumber);
    // Try wa.me URL first (most reliable across platforms)
    final encoded = Uri.encodeComponent(message ?? '');
    final uri = Uri.parse('https://wa.me/$normalized${message != null ? '?text=$encoded' : ''}');

    if (await canLaunchUrl(uri)) {
      return await launchUrl(uri, mode: LaunchMode.externalApplication);
    }

    // Fallback: whatsapp:// scheme
    final fallback = Uri.parse('whatsapp://send?phone=$normalized&text=$encoded');
    if (await canLaunchUrl(fallback)) {
      return await launchUrl(fallback, mode: LaunchMode.externalApplication);
    }

    return false;
  }

  /// Send via org's configured Cloud API (Interakt/AiSensy/etc.)
  /// Goes through our backend, which handles the actual provider call
  Future<bool> sendCloud({
    required int leadId,
    String? message,
    int? templateId,
  }) async {
    try {
      await ApiClient.instance.dio.post(
        '/comms/whatsapp/send/',
        data: {
          'lead_id': leadId,
          if (message != null) 'message': message,
          if (templateId != null) 'template_id': templateId,
        },
      );
      return true;
    } catch (e) {
      return false;
    }
  }

  /// Apply template variables to template body
  /// Replaces {{1}}, {{2}}, etc. with values
  String applyTemplate(String templateBody, Map<int, String> variables) {
    var result = templateBody;
    variables.forEach((key, value) {
      result = result.replaceAll('{{$key}}', value);
    });
    return result;
  }

  /// List available WhatsApp templates from backend
  Future<List<Map<String, dynamic>>> listTemplates({bool approvedOnly = true}) async {
    try {
      final res = await ApiClient.instance.dio.get(
        '/comms/whatsapp/templates/',
        queryParameters: approvedOnly ? {'approved_only': true} : null,
      );
      return (res.data as List).cast<Map<String, dynamic>>();
    } catch (_) {
      return [];
    }
  }

  String _normalizeForWhatsApp(String phone) {
    // WhatsApp wants format like 919876543210 (no +, no spaces)
    final digits = phone.replaceAll(RegExp(r'[^\d]'), '');
    if (digits.startsWith('91') && digits.length == 12) return digits;
    if (digits.length == 10) return '91$digits';
    return digits;
  }
}
