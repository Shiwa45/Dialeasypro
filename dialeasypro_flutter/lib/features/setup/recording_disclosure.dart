import 'package:flutter/material.dart';

import '../../core/legal.dart';
import '../../core/services/call_recording_service.dart';
import '../../core/theme/colors.dart';

// ============================================================
// DialSathi — Call recording disclosure
//
// Google Play's User Data policy requires a prominent in-app disclosure, and
// the user's agreement, before an app collects personal or sensitive data —
// call audio included — and before it asks for the runtime permission that
// collects it. This is that disclosure. Nothing is recorded, and the
// microphone is not requested, until the agent taps "I agree"
// (CallRecordingService.isEnabled checks the stored consent).
// ============================================================

/// Shows the disclosure unless already agreed. True when the agent agrees.
Future<bool> confirmRecordingDisclosure(BuildContext context) async {
  if (await CallRecordingService.instance.hasConsent()) return true;
  if (!context.mounted) return false;
  final agreed = await showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (_) => const RecordingDisclosureDialog(),
  );
  if (agreed == true) {
    await CallRecordingService.instance.recordConsent();
    return true;
  }
  return false;
}

class RecordingDisclosureDialog extends StatelessWidget {
  const RecordingDisclosureDialog({super.key});

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: AppColors.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      titlePadding: const EdgeInsets.fromLTRB(22, 22, 22, 4),
      contentPadding: const EdgeInsets.fromLTRB(22, 8, 22, 0),
      title: const Row(children: [
        Icon(Icons.mic_none_rounded, color: AppColors.brand),
        SizedBox(width: 10),
        Expanded(child: Text('Call recording', style: AppTextStyles.h3)),
      ]),
      content: SingleChildScrollView(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
          const Text(
            'With call recording on, DialSathi records the calls you make to leads '
            'from this app and uploads each recording to your company’s CRM.',
            style: AppTextStyles.body,
          ),
          const SizedBox(height: 14),
          const _Point(
            icon: Icons.graphic_eq,
            title: 'What is collected',
            text: 'The audio of the call, through your microphone and from recordings '
                'your phone’s own call recorder saves, with the number called and the time.',
          ),
          const _Point(
            icon: Icons.fact_check_outlined,
            title: 'Why',
            text: 'Each recording is attached to its lead so your managers can review '
                'calls for quality and training.',
          ),
          const _Point(
            icon: Icons.lock_outline,
            title: 'Who can hear it',
            text: 'Only people in your company who can open that lead in the CRM. '
                'Recordings are uploaded over an encrypted connection.',
          ),
          const _Point(
            icon: Icons.toggle_on_outlined,
            title: 'Your choice',
            text: 'Recording runs only during calls placed from the app. Turn it off '
                'any time in Profile. Let the people you call know calls may be recorded.',
          ),
          const SizedBox(height: 4),
          TextButton(
            onPressed: openPrivacyPolicy,
            style: TextButton.styleFrom(padding: EdgeInsets.zero, foregroundColor: AppColors.brand),
            child: const Text('Read the privacy policy'),
          ),
        ]),
      ),
      actionsPadding: const EdgeInsets.fromLTRB(16, 4, 16, 14),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Not now'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(true),
          style: FilledButton.styleFrom(backgroundColor: AppColors.brand),
          child: const Text('I agree'),
        ),
      ],
    );
  }
}

class _Point extends StatelessWidget {
  final IconData icon;
  final String title, text;
  const _Point({required this.icon, required this.title, required this.text});

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Icon(icon, size: 18, color: AppColors.text2),
      const SizedBox(width: 10),
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: AppTextStyles.h5),
        const SizedBox(height: 2),
        Text(text, style: AppTextStyles.caption),
      ])),
    ]),
  );
}
