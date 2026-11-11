import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/services/call_recording_service.dart';
import '../../core/services/setup_service.dart';
import '../../core/theme/colors.dart';
import '../../core/widgets/widgets.dart';

// ============================================================
// DialSathi — Where call recordings come from
//
// The same choice NeoDove and other SIM-based CRMs give: the phone's own
// call recorder (best), a call-recorder app for phones whose dialer keeps
// recordings private (the Google Phone app), or the app's microphone. The
// agent can also point the app at the exact folder their recorder saves to
// and check it after a test call.
// ============================================================

class RecordingSourcePanel extends StatefulWidget {
  /// Called after anything changes, so the parent can re-check readiness.
  final VoidCallback? onChanged;
  const RecordingSourcePanel({super.key, this.onChanged});

  @override
  State<RecordingSourcePanel> createState() => _RecordingSourcePanelState();
}

class _RecordingSourcePanelState extends State<RecordingSourcePanel>
    with WidgetsBindingObserver {
  String _source = 'builtin';
  String _dialerLabel = '';
  String? _folder;
  bool _folderOk = false;
  bool _googleDialer = false;
  BrandGuide? _guide;
  String? _checkResult;
  bool _loading = true;

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
    // Back from the Play Store, the default-apps screen or the recorder:
    // the dialer or the folder may have changed.
    if (state == AppLifecycleState.resumed) _load();
  }

  Future<void> _load() async {
    final svc = CallRecordingService.instance;
    final info = await SetupService.instance.refreshDeviceInfo();
    final source = await svc.recordingSource();
    final folder = await svc.recordingFolder();
    final ok = await svc.hasFolderAccess();
    final google = await svc.usesGoogleDialer();
    final guide = await SetupService.instance.guide();
    if (!mounted) return;
    setState(() {
      _source = source;
      _folder = folder?.label;
      _folderOk = ok;
      _googleDialer = google;
      _dialerLabel = info['dialerLabel'] as String? ?? '';
      _guide = guide;
      _loading = false;
    });
  }

  Future<void> _setSource(String? v) async {
    if (v == null) return;
    await CallRecordingService.instance.setRecordingSource(v);
    setState(() {
      _source = v;
      _checkResult = null;
    });
    widget.onChanged?.call();
  }

  Future<void> _pickFolder() async {
    final label = await CallRecordingService.instance.pickRecordingFolder();
    if (label == null) return;
    await _load();
    widget.onChanged?.call();
    if (mounted) AppToast.show(context, 'Recordings folder set: $label', isSuccess: true);
  }

  Future<void> _clearFolder() async {
    await CallRecordingService.instance.clearRecordingFolder();
    await _load();
    widget.onChanged?.call();
  }

  Future<void> _checkFolder() async {
    final newest = await CallRecordingService.instance.newestInFolder();
    if (!mounted) return;
    setState(() {
      _checkResult = newest == null
          ? 'No recordings from the last 7 days in this folder. Make a short test call with '
              'recording on, then check again — or choose another folder.'
          : 'Newest recording: "${newest.name}", saved '
              '${MaterialLocalizations.of(context).formatShortDate(newest.modified)} '
              '${TimeOfDay.fromDateTime(newest.modified).format(context)}. This folder works.';
    });
  }

  Future<void> _openRecorderSettings() async {
    final where = await SetupService.instance.openCallRecordingSettings();
    if (where == 'none' && mounted) {
      AppToast.show(context, 'Could not open the Phone app settings — follow the steps shown.',
          isError: true);
    }
  }

  Future<void> _openStore(String query) async {
    final uri = Uri.parse('https://play.google.com/store/search?q=${Uri.encodeComponent(query)}&c=apps');
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication) && mounted) {
      AppToast.show(context, 'Open the Play Store and search for "$query".', isError: true);
    }
  }

  Future<void> _openDefaultApps() async {
    final opened = await SetupService.instance.openDefaultDialerSettings();
    if (!opened && mounted) {
      AppToast.show(context, 'Open Settings → Apps → Default apps → Phone app.', isError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.all(12),
        child: Center(child: CircularProgressIndicator(color: AppColors.yellow)),
      );
    }
    final guide = _guide;
    final small = AppTextStyles.caption.copyWith(fontSize: 11.5);

    Widget option(String value, String title, String subtitle) => RadioListTile<String>(
          value: value,
          groupValue: _source,
          onChanged: _setSource,
          contentPadding: EdgeInsets.zero,
          dense: true,
          activeColor: AppColors.success,
          title: Text(title, style: const TextStyle(
              fontFamily: 'PlusJakartaSans', fontSize: 13, fontWeight: FontWeight.w700)),
          subtitle: Text(subtitle, style: small),
        );

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('RECORDING SOURCE', style: AppTextStyles.label),
      if (_dialerLabel.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Text('Your phone app (dialer): $_dialerLabel', style: small),
        ),
      if (_googleDialer)
        Container(
          margin: const EdgeInsets.only(top: 6, bottom: 4),
          padding: const EdgeInsets.all(10),
          color: AppColors.infoBg,
          child: Text(
            'Your phone app is the Google Phone app. It keeps call recordings where no other '
            'app can read them, so recordings cannot reach the CRM. Install a dialer that '
            'records calls and make it your default phone app (option 2).',
            style: small,
          ),
        ),
      option('builtin', "Phone's built-in recorder${_googleDialer ? '' : ' (recommended)'}",
          'Best quality: both sides of every call, including calls not made from DialSathi.'),
      option('recorder_app', 'Recording dialer or recorder app${_googleDialer ? ' (needed on this phone)' : ''}',
          'A phone app (dialer) that records calls, such as ODialer, set as your default phone '
          'app — or a recorder app such as Cube ACR. Select its recordings folder below.'),
      option('app_mic', 'Record with DialSathi (microphone)',
          'Only for calls dialled from DialSathi. Put the call on speaker so both sides are heard.'),
      const SizedBox(height: 6),

      if (_source == 'builtin' && guide != null) ...[
        ...guide.recordingSteps.asMap().entries.map((e) => Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text('${e.key + 1}. ${e.value}', style: small),
            )),
        TextButton(onPressed: _openRecorderSettings, child: const Text('Open Phone settings')),
      ],
      if (_source == 'recorder_app') ...[
        Text('1. Install a dialer that records calls (for example ODialer), or a recorder '
            'app such as Cube ACR.', style: small),
        Text('2. A dialer: make it your default phone app. A recorder app: allow everything it '
            'asks for (including its accessibility helper on newer phones).', style: small),
        Text('3. In its settings, turn on recording for all calls.', style: small),
        Text('4. Make a short test call so it creates its recordings folder.', style: small),
        Text('5. Tap "Select folder" below, choose that folder, then "Check folder".', style: small),
        Wrap(spacing: 4, children: [
          TextButton(onPressed: () => _openStore('ODialer'), child: const Text('Get ODialer')),
          TextButton(onPressed: () => _openStore('Cube ACR'), child: const Text('Get Cube ACR')),
          TextButton(onPressed: _openDefaultApps, child: const Text('Set default phone app')),
        ]),
        Container(
          margin: const EdgeInsets.only(top: 2, bottom: 6),
          padding: const EdgeInsets.all(8),
          color: AppColors.infoBg,
          child: Text(
            'Any dialer works if it (1) saves recordings as audio files on the phone, not only '
            'in its own app or cloud, (2) records every call automatically and (3) names files '
            'with the number or contact name. Check one test recording plays both sides.',
            style: small,
          ),
        ),
      ],

      if (_source != 'app_mic') ...[
        const SizedBox(height: 4),
        const Text('RECORDINGS FOLDER', style: AppTextStyles.label),
        const SizedBox(height: 4),
        Text(
          _folder == null
              ? (_source == 'recorder_app'
                  ? 'Not selected yet — required for a recorder app.'
                  : 'Found automatically. If recordings do not upload, select the folder '
                      'your recorder saves to (find it after a test call).')
              : '${_folderOk ? '✓' : '⚠'} $_folder'
                  '${_folderOk ? '' : ' — access was lost, select it again.'}',
          style: small,
        ),
        Wrap(spacing: 4, children: [
          TextButton(
            onPressed: _pickFolder,
            child: Text(_folder == null ? 'Select folder' : 'Change folder'),
          ),
          if (_folder != null) TextButton(onPressed: _checkFolder, child: const Text('Check folder')),
          if (_folder != null) TextButton(onPressed: _clearFolder, child: const Text('Remove')),
        ]),
        if (_checkResult != null) Text(_checkResult!, style: small),
      ],
    ]);
  }
}
