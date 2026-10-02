import 'package:url_launcher/url_launcher.dart';

// ============================================================
// DialEasypro — Legal links
//
// Google Play requires a privacy policy reachable from inside the app. The
// address can be changed per build:
//   flutter build appbundle --dart-define=PRIVACY_POLICY_URL=https://...
// The page must exist at that address before the app is published.
// ============================================================

const String kPrivacyPolicyUrl = String.fromEnvironment(
  'PRIVACY_POLICY_URL',
  defaultValue: 'https://easyian.shop/privacy-policy',
);

/// Opens the privacy policy in the browser. False when nothing could open it.
Future<bool> openPrivacyPolicy() async {
  try {
    return await launchUrl(Uri.parse(kPrivacyPolicyUrl), mode: LaunchMode.externalApplication);
  } catch (_) {
    return false;
  }
}
