import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/services/call_recording_service.dart';
import '../../core/services/call_tracking_service.dart';
import '../../core/services/phone_service.dart';
import '../../core/services/setup_service.dart';
import '../../core/theme/colors.dart';
import '../../core/widgets/widgets.dart';
import '../auth/auth_provider.dart';
import 'recording_disclosure.dart';
import 'recording_source_panel.dart';

// ============================================================
// DialSathi — Call tracking setup
//
// Shown when the company admin has turned phone call tracking on for this
// agent. The agent must allow call-log and recording access before working:
// from then on every incoming and outgoing call on the phone is saved to the
// CRM with its recording. Shown once per phone even when everything is
// already allowed, so the agent knows before any call is collected.
// ============================================================

class CallTrackingSetupScreen extends ConsumerStatefulWidget {
  const CallTrackingSetupScreen({super.key});

  @override
  ConsumerState<CallTrackingSetupScreen> createState() => _CallTrackingSetupScreenState();
}

class _CallTrackingSetupScreenState extends ConsumerState<CallTrackingSetupScreen>
    with WidgetsBindingObserver {
  CallTrackingReadiness? _r;
  BrandGuide? _guide;
  bool _allFiles = true;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _load();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Back from a system settings screen: re-read what was allowed.
    if (state == AppLifecycleState.resumed) _refresh();
  }

  Future<void> _load() async {
    final guide = await SetupService.instance.guide();
    final allFiles = await SetupService.instance.hasAllFilesAccessOption();
    if (!mounted) return;
    setState(() {
      _guide = guide;
      _allFiles = allFiles;
    });
    await _refresh();
  }

  Future<void> _refresh() async {
    final r = await CallTrackingService.instance.refreshReadiness();
    if (mounted) setState(() => _r = r);
  }

  Future<void> _run(Future<void> Function() step) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await step();
    } finally {
      await _refresh();
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _allowCalls() => _run(() async {
        final status = await Permission.phone.request();
        // The phone-state listener yields nothing when attached before the
        // permission existed.
        await PhoneService.instance.init();
        if (!status.isGranted && mounted) {
          AppToast.show(context,
              'Call log access was not allowed. Open App settings → Permissions and allow '
              '"Call logs" and "Phone".',
              isError: true);
        }
      });

  Future<void> _allowStorage() => _run(() async {
        await CallRecordingService.instance.requestStorageAccess();
      });

  Future<void> _allowRecording() => _run(() async {
        if (!await CallRecordingService.instance.hasConsent()) {
          if (!mounted || !await confirmRecordingDisclosure(context)) return;
        }
        // The microphone is only the fallback for calls dialled from the
        // app on phones without a usable recorder.
        await Permission.microphone.request();
        await CallRecordingService.instance.setEnabled(true);
      });

  Future<void> _allowBattery() => _run(() async {
        await SetupService.instance.requestIgnoreBatteryOptimizations();
      });

  Future<void> _getDialer() async {
    final uri = Uri.parse('https://play.google.com/store/search?q=Odialer&c=apps');
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication) && mounted) {
      AppToast.show(context, 'Open the Play Store and search for "Odialer".', isError: true);
    }
  }

  Future<void> _openDefaultApps() async {
    final opened = await SetupService.instance.openDefaultDialerSettings();
    if (!opened && mounted) {
      AppToast.show(context, 'Open Settings → Apps → Default apps → Phone app.', isError: true);
    }
  }

  Future<void> _continue() async {
    await CallTrackingService.instance.markStarted();
    if (mounted) context.go('/');
  }

  @override
  Widget build(BuildContext context) {
    final r = _r;
    final guide = _guide;
    if (r == null || guide == null) {
      return const Scaffold(
        backgroundColor: AppColors.background,
        body: Center(child: CircularProgressIndicator(color: AppColors.yellow)),
      );
    }

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Call tracking'),
        automaticallyImplyLeading: false,
        actions: [
          TextButton(
            onPressed: () => ref.read(authProvider.notifier).logout(),
            child: const Text('Sign out', style: TextStyle(color: AppColors.dark)),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          BrutalCard(
            padding: const EdgeInsets.all(14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: const [
              Text('Your admin has turned on call tracking', style: AppTextStyles.h5),
              SizedBox(height: 8),
              Text(
                'From now on, every incoming and outgoing call on this phone — including '
                'calls you make outside DialSathi and missed calls — is saved to the CRM '
                'with its number, time and duration, and answered calls are uploaded with '
                'their recording. Allow the access below to continue.',
                style: AppTextStyles.caption,
              ),
            ]),
          ),
          const SizedBox(height: 12),

          if (!r.callLogSupported)
            _Item(
              title: 'This version of the app cannot read the call log',
              done: false,
              body: 'Google Play does not allow apps from the Play Store to read the call log. '
                  'Ask your admin for the DialSathi app download link to use call tracking. '
                  'Until then, only calls made from the app are saved.',
            )
          else ...[
            if (r.googleDialer)
              _Item(
                title: 'Switch from the Google Phone app',
                done: false,
                body: 'The Google Phone app keeps call recordings where DialSathi cannot read them. '
                    'Install a dialer that records calls (for example Odialer), make it your default '
                    'phone app, then choose "Recording dialer app" below and select its folder.',
                action: ('Get Odialer', _getDialer),
                secondary: ('Set default phone app', _openDefaultApps),
              ),
            _Item(
              title: 'Call log and phone',
              done: r.callLog && r.phone,
              body: 'Reads your incoming, outgoing and missed calls so they reach the CRM.',
              action: r.callLog && r.phone ? null : ('Allow', _allowCalls),
              secondary: r.callLog && r.phone ? null : ('App settings', () => openAppSettings()),
            ),
            _Item(
              title: 'Call recording',
              done: r.recording,
              body: 'Uploads the recording of each answered call. You will see exactly what is '
                  'collected before you agree.',
              action: r.recording ? null : ('Turn on', _allowRecording),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: BrutalCard(
                padding: const EdgeInsets.all(14),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('Where recordings come from', style: AppTextStyles.h5),
                  const SizedBox(height: 8),
                  RecordingSourcePanel(onChanged: _refresh),
                ]),
              ),
            ),
            _Item(
              title: 'Access to recording files',
              done: r.storage,
              body: (_allFiles
                      ? 'Lets the app read the folder where your phone saves call recordings.'
                      : 'Lets the app find the call recordings your phone saves as audio files.') +
                  ' With a call recorder app, select its folder above instead.',
              action: r.storage
                  ? null
                  : (_allFiles ? 'Allow all files access' : 'Allow audio access', _allowStorage),
            ),
            if (!r.battery)
              _Item(
                title: 'Keep the app running (recommended)',
                done: false,
                body: 'Lets calls and recordings upload soon after each call instead of the '
                    'next time you open the app.',
                action: ('Allow background use', _allowBattery),
              ),
          ],

          const SizedBox(height: 16),
          BrutalButton.primary(
            label: r.complete ? 'Continue →' : 'Allow everything above to continue',
            onPressed: r.complete && !_busy ? _continue : null,
          ),
          const SizedBox(height: 10),
          Center(child: TextButton(onPressed: _refresh, child: const Text('Re-check'))),
          const SizedBox(height: 30),
        ]),
      ),
    );
  }
}

class _Item extends StatelessWidget {
  final String title;
  final bool done;
  final String body;
  final (String, VoidCallback)? action;
  final (String, VoidCallback)? secondary;

  const _Item({
    required this.title,
    required this.done,
    required this.body,
    this.action,
    this.secondary,
  });

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: BrutalCard(
          padding: const EdgeInsets.all(14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Icon(done ? Icons.check_circle : Icons.radio_button_unchecked,
                  size: 20, color: done ? AppColors.success : AppColors.dark),
              const SizedBox(width: 8),
              Expanded(child: Text(title, style: AppTextStyles.h5)),
            ]),
            const SizedBox(height: 8),
            Text(body, style: AppTextStyles.caption),
            if (action != null || secondary != null) ...[
              const SizedBox(height: 10),
              Wrap(spacing: 8, runSpacing: 8, children: [
                if (action != null)
                  BrutalButton.primary(label: action!.$1, onPressed: action!.$2, isFullWidth: false),
                if (secondary != null)
                  TextButton(onPressed: secondary!.$2, child: Text(secondary!.$1)),
              ]),
            ],
          ]),
        ),
      );
}
