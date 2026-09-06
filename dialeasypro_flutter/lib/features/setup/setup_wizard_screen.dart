import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../core/services/call_recording_service.dart';
import '../../core/services/setup_service.dart';
import '../../core/theme/colors.dart';
import '../../core/widgets/widgets.dart';

// ============================================================
// First-run setup.
//
// An agent who installs the app and starts dialling without granting anything
// gets a CRM that logs calls and records none of them, with nothing to say
// why. This walks them through it once.
//
// Every step is skippable on purpose. Blocking the app behind a permission the
// agent cannot grant on their device — "All files access" is Play-restricted,
// some ROMs have no call recorder at all — would be worse than a degraded
// setup, and their manager still needs the call log either way. Each step
// therefore says plainly what stops working if it is skipped.
// ============================================================

class SetupWizardScreen extends ConsumerStatefulWidget {
  const SetupWizardScreen({super.key});

  @override
  ConsumerState<SetupWizardScreen> createState() => _SetupWizardScreenState();
}

class _SetupWizardScreenState extends ConsumerState<SetupWizardScreen>
    with WidgetsBindingObserver {
  BrandGuide? _guide;
  bool _loading = true;

  // Live status, refreshed whenever we come back from a system screen.
  bool _phoneOk = false;
  bool _micOk = false;
  bool _notifyOk = false;
  bool _storageOk = false;
  bool _batteryOk = true;
  bool _recordingOn = false;

  // The one thing we cannot detect: whether the phone's own recorder is on.
  bool _dialerConfirmed = false;

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
    // Returning from a system settings screen is the only signal we get that
    // something may have changed — nothing here fires a callback.
    if (state == AppLifecycleState.resumed) _refresh();
  }

  Future<void> _load() async {
    final guide = await SetupService.instance.guide();
    if (!mounted) return;
    setState(() => _guide = guide);
    await _refresh();
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _refresh() async {
    final phone = await Permission.phone.isGranted;
    final mic = await Permission.microphone.isGranted;
    final notify = await Permission.notification.isGranted;
    final storage = await CallRecordingService.instance.hasStorageAccess();
    final battery = await SetupService.instance.isIgnoringBatteryOptimizations();
    final recording = await CallRecordingService.instance.isEnabled();
    if (!mounted) return;
    setState(() {
      _phoneOk = phone;
      _micOk = mic;
      _notifyOk = notify;
      _storageOk = storage;
      _batteryOk = battery;
      _recordingOn = recording;
    });
  }

  Future<void> _finish() async {
    await SetupService.instance.markComplete();
    if (mounted) context.go('/dashboard');
  }

  // ---- Step actions ----------------------------------------------

  Future<void> _grantCore() async {
    await [Permission.phone, Permission.microphone, Permission.notification].request();
    await _refresh();
    if (!mounted) return;
    if (!_phoneOk || !_micOk) {
      // A permanently-denied permission never prompts again; the app settings
      // screen is the only way back.
      AppToast.show(context,
          'Some permissions were denied. Open app settings to allow them.',
          isError: true);
    }
  }

  Future<void> _grantStorage() async {
    await CallRecordingService.instance.requestStorageAccess();
    await _refresh();
  }

  Future<void> _fixBattery() async {
    await SetupService.instance.requestIgnoreBatteryOptimizations();
    // Status is re-read on resume.
  }

  Future<void> _openAutoStart() async {
    final opened = await SetupService.instance.openAutoStartSettings();
    if (!mounted) return;
    if (!opened) {
      AppToast.show(context,
          'Could not open that screen. Find Autostart in your phone Settings '
          'and allow DialEasypro.',
          isError: true);
    }
  }

  Future<void> _openRecordingSettings() async {
    final where = await SetupService.instance.openCallRecordingSettings();
    if (!mounted) return;
    if (where == 'none') {
      AppToast.show(context,
          'Could not open the Phone app settings — please follow the steps above.',
          isError: true);
    } else if (where != 'settings') {
      AppToast.show(context, 'Opened the Phone app — follow the steps above.');
    }
  }

  Future<void> _toggleRecording(bool value) async {
    await CallRecordingService.instance.setEnabled(value);
    await _refresh();
  }

  // ---- UI ---------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        backgroundColor: AppColors.background,
        body: Center(child: CircularProgressIndicator(color: AppColors.yellow)),
      );
    }

    final guide = _guide!;
    final coreOk = _phoneOk && _micOk;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Set up your phone'),
        automaticallyImplyLeading: false,
        actions: [
          TextButton(
            onPressed: _finish,
            child: const Text('Skip', style: TextStyle(color: AppColors.dark)),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(
            'A few one-time settings so calls dial and record properly on '
            '${guide.label}.',
            style: AppTextStyles.caption,
          ),
          const SizedBox(height: 16),

          // ---- 1. Core permissions ----
          _Step(
            index: 1,
            title: 'Calls, microphone & alerts',
            done: coreOk,
            body: const Text(
              'Needed to dial from the app, record your side of a call, and '
              'show follow-up reminders. Without these the dialer cannot place '
              'calls at all.',
              style: AppTextStyles.caption,
            ),
            action: coreOk ? null : ('Allow', _grantCore),
            secondary: coreOk ? null : ('App settings', () => openAppSettings()),
            checks: [
              _Check('Phone', _phoneOk),
              _Check('Microphone', _micOk),
              _Check('Notifications', _notifyOk),
            ],
          ),

          // ---- 2. Storage ----
          _Step(
            index: 2,
            title: 'Access to recording files',
            done: _storageOk,
            body: const Text(
              'Your phone saves call recordings to its own folder. This lets '
              'the app read that folder and upload the recording to the lead.\n\n'
              'Skipping this means only microphone recordings are captured — '
              'your side of the call, or both sides on speakerphone.',
              style: AppTextStyles.caption,
            ),
            action: _storageOk ? null : ('Allow all files access', _grantStorage),
          ),

          // ---- 3. The phone's own recorder ----
          _Step(
            index: 3,
            title: 'Turn on call recording',
            done: _dialerConfirmed,
            body: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text(
                'This one is set in your phone, not in this app — Android does '
                'not let any app switch it on for you.',
                style: AppTextStyles.caption,
              ),
              const SizedBox(height: 10),
              ...guide.recordingSteps.asMap().entries.map((e) => Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${e.key + 1}. ',
                          style: const TextStyle(
                              fontFamily: 'SpaceGrotesk',
                              fontWeight: FontWeight.w700,
                              fontSize: 12.5)),
                      Expanded(child: Text(e.value, style: AppTextStyles.caption)),
                    ]),
                  )),
              const SizedBox(height: 8),
              CheckboxListTile(
                value: _dialerConfirmed,
                onChanged: (v) => setState(() => _dialerConfirmed = v ?? false),
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                activeColor: AppColors.success,
                title: const Text("I've turned on call recording",
                    style: TextStyle(fontFamily: 'DMSans', fontSize: 13)),
              ),
            ]),
            action: ('Open Phone app settings', _openRecordingSettings),
          ),

          // ---- 4. Background execution ----
          if (!_batteryOk || guide.needsAutoStart)
            _Step(
              index: 4,
              title: 'Keep the app running',
              done: _batteryOk && !guide.needsAutoStart,
              body: Text(
                guide.needsAutoStart
                    ? '${guide.label} phones stop background apps aggressively. '
                        'Allow the app to run in the background, or recordings '
                        'made after a call may never finish uploading.'
                    : 'Exempt the app from battery optimisation so recordings '
                        'finish uploading after a call.',
                style: AppTextStyles.caption,
              ),
              action: _batteryOk ? null : ('Allow background use', _fixBattery),
              secondary:
                  guide.needsAutoStart ? ('Autostart settings', _openAutoStart) : null,
            ),

          // ---- 5. Switch it on in the CRM ----
          _Step(
            index: guide.needsAutoStart || !_batteryOk ? 5 : 4,
            title: 'Upload recordings to the CRM',
            done: _recordingOn,
            body: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text(
                'With this on, every call recording is attached to the lead '
                'automatically. You can change it later in Profile.',
                style: AppTextStyles.caption,
              ),
              const SizedBox(height: 6),
              Row(children: [
                Expanded(child: Text(_recordingOn ? 'Enabled' : 'Disabled',
                    style: AppTextStyles.h5)),
                Switch(
                  value: _recordingOn,
                  activeColor: AppColors.success,
                  onChanged: _toggleRecording,
                ),
              ]),
            ]),
          ),

          const SizedBox(height: 20),
          BrutalButton.primary(label: 'Finish setup →', onPressed: _finish),
          const SizedBox(height: 10),
          Center(
            child: TextButton(
              onPressed: _refresh,
              child: const Text('Re-check status'),
            ),
          ),
          const SizedBox(height: 30),
        ]),
      ),
    );
  }
}

// ---- Building blocks ---------------------------------------------

class _Check {
  final String label;
  final bool ok;
  const _Check(this.label, this.ok);
}

class _Step extends StatelessWidget {
  final int index;
  final String title;
  final bool done;
  final Widget body;
  final (String, VoidCallback)? action;
  final (String, VoidCallback)? secondary;
  final List<_Check>? checks;

  const _Step({
    required this.index,
    required this.title,
    required this.done,
    required this.body,
    this.action,
    this.secondary,
    this.checks,
  });

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: BrutalCard(
          padding: const EdgeInsets.all(14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Container(
                width: 24,
                height: 24,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: done ? AppColors.success : AppColors.yellow,
                  border: Border.all(color: AppColors.black, width: 2),
                ),
                child: done
                    ? const Icon(Icons.check, size: 15, color: AppColors.white)
                    : Text('$index',
                        style: const TextStyle(
                            fontFamily: 'SpaceGrotesk',
                            fontWeight: FontWeight.w700,
                            fontSize: 12)),
              ),
              const SizedBox(width: 10),
              Expanded(child: Text(title, style: AppTextStyles.h5)),
            ]),
            const SizedBox(height: 10),
            body,
            if (checks != null) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 12,
                runSpacing: 4,
                children: checks!
                    .map((c) => Row(mainAxisSize: MainAxisSize.min, children: [
                          Icon(c.ok ? Icons.check_circle : Icons.radio_button_unchecked,
                              size: 14,
                              color: c.ok ? AppColors.success : AppColors.grey),
                          const SizedBox(width: 4),
                          Text(c.label,
                              style: const TextStyle(
                                  fontFamily: 'DMSans', fontSize: 11.5)),
                        ]))
                    .toList(),
              ),
            ],
            if (action != null || secondary != null) ...[
              const SizedBox(height: 12),
              Row(children: [
                if (action != null)
                  Expanded(
                    child: BrutalButton.secondary(
                      label: action!.$1,
                      onPressed: action!.$2,
                    ),
                  ),
                if (action != null && secondary != null) const SizedBox(width: 8),
                if (secondary != null)
                  TextButton(onPressed: secondary!.$2, child: Text(secondary!.$1)),
              ]),
            ],
          ]),
        ),
      );
}
