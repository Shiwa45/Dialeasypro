import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../core/services/recording_service.dart';
import '../../core/services/call_recording_service.dart';
import '../../core/services/tenant_config.dart';
import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../../data/services/services.dart';
import '../auth/auth_provider.dart';

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _oldPw = TextEditingController();
  final _newPw = TextEditingController();
  final _confirmPw = TextEditingController();
  final _cloudName = TextEditingController();
  final _uploadPreset = TextEditingController();
  String _waMode = 'native';
  bool _saving = false, _changingPw = false, _savingCloud = false;
  bool _callRecEnabled = false;

  @override
  void initState() {
    super.initState();
    final a = ref.read(currentAgentProvider);
    _name.text = a?.name ?? '';
    _phone.text = a?.phone ?? '';
    _loadPrefs();
  }

  Future<void> _loadPrefs() async {
    final m = await UserPrefs.getWhatsAppMode();
    final prefs = await SharedPreferences.getInstance();
    final recEnabled = await CallRecordingService.instance.isEnabled();
    if (mounted) setState(() {
      _waMode = m;
      _cloudName.text = prefs.getString('cloudinary_name') ?? '';
      _uploadPreset.text = prefs.getString('cloudinary_preset') ?? '';
      _callRecEnabled = recEnabled;
    });
  }

  @override
  void dispose() {
    for (final c in [_name, _phone, _oldPw, _newPw, _confirmPw, _cloudName, _uploadPreset]) c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final agent = ref.watch(currentAgentProvider);
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('My Profile'),
        leading: IconButton(icon: const Icon(Icons.arrow_back, color: AppColors.black), onPressed: () => context.pop()),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          // Avatar card
          BrutalCard(padding: const EdgeInsets.all(18), color: AppColors.dark, child: Row(children: [
            BrutalAvatar(name: agent?.name ?? 'A', size: 64, backgroundColor: AppColors.yellow),
            const SizedBox(width: 16),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(agent?.name ?? '', style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 18, color: AppColors.yellow)),
              Text(agent?.email ?? '', style: const TextStyle(fontFamily: 'DMSans', fontSize: 12, color: AppColors.muted)),
              const SizedBox(height: 6),
              TagChip(label: agent?.roleDisplay ?? agent?.role ?? '', backgroundColor: AppColors.yellow),
            ])),
          ])).animate().fadeIn(),

          const SizedBox(height: 16),

          // Workspace info
          BrutalCard(padding: const EdgeInsets.all(14), color: AppColors.infoBg, borderColor: AppColors.info,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: const [
                Icon(Icons.business, size: 18, color: AppColors.info),
                SizedBox(width: 8),
                Text('Workspace', style: AppTextStyles.h5),
              ]),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                decoration: BoxDecoration(
                  color: AppColors.white,
                  border: Border.all(color: AppColors.black, width: 1.5),
                ),
                child: Row(children: [
                  Expanded(child: Text(
                    TenantConfig.instance.summary,
                    style: const TextStyle(fontFamily: 'monospace', fontWeight: FontWeight.w600, fontSize: 13, color: AppColors.black),
                    overflow: TextOverflow.ellipsis,
                  )),
                  TagChip(
                    label: 'CONNECTED',
                    backgroundColor: AppColors.success,
                    textColor: AppColors.white,
                  ),
                ]),
              ),
              const SizedBox(height: 4),
              Text(
                TenantConfig.instance.apiBaseUrl,
                style: const TextStyle(fontFamily: 'monospace', fontSize: 10, color: AppColors.greyDark),
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 10),
              BrutalButton.secondary(
                label: 'Switch Workspace',
                iconData: Icons.swap_horiz,
                isFullWidth: true,
                onPressed: () async {
                  final ok = await showBrutalConfirm(
                    context: context,
                    title: 'Switch Workspace?',
                    message: 'You will be signed out and need to enter another workspace name and credentials.',
                    confirmLabel: 'Switch',
                    danger: true,
                  );
                  if (ok == true && context.mounted) {
                    await TenantConfig.instance.clear();
                    await ref.read(authProvider.notifier).switchWorkspace();
                    if (context.mounted) context.go('/login');
                  }
                },
              ),
            ]),
          ).animate().fadeIn(delay: 50.ms),

          const SizedBox(height: 14),

          // WhatsApp Mode Preference
          BrutalCard(padding: const EdgeInsets.all(14), color: AppColors.tealBg, borderColor: AppColors.teal,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: const [
                Icon(Icons.chat_bubble_outline, size: 18, color: AppColors.teal),
                SizedBox(width: 8),
                Text('WhatsApp Default Mode', style: AppTextStyles.h5),
              ]),
              const SizedBox(height: 4),
              const Text('Used when you tap WhatsApp on a lead', style: AppTextStyles.caption),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(child: _WaModeBox(
                  label: 'NATIVE',
                  subtitle: 'Opens device WhatsApp',
                  selected: _waMode == 'native',
                  color: AppColors.success,
                  onTap: () { setState(() => _waMode = 'native'); UserPrefs.setWhatsAppMode('native'); },
                )),
                const SizedBox(width: 10),
                Expanded(child: _WaModeBox(
                  label: 'CLOUD',
                  subtitle: 'Via Cloud API',
                  selected: _waMode == 'cloud',
                  color: AppColors.purple,
                  onTap: () { setState(() => _waMode = 'cloud'); UserPrefs.setWhatsAppMode('cloud'); },
                )),
              ]),
            ]),
          ).animate().fadeIn(delay: 80.ms),

          const SizedBox(height: 14),

          // Profile fields
          BrutalCard(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const SectionHeader(title: 'Edit Profile', icon: Icons.edit),
            const SizedBox(height: 14),
            BrutalTextField(label: 'Full Name', controller: _name),
            const SizedBox(height: 12),
            BrutalTextField(label: 'Phone', controller: _phone, keyboardType: TextInputType.phone),
            const SizedBox(height: 16),
            BrutalButton.primary(
              label: _saving ? 'Saving…' : 'Save Profile',
              isLoading: _saving,
              onPressed: () async {
                setState(() => _saving = true);
                try {
                  await AuthService.instance.updateProfile({'name': _name.text.trim(), 'phone': _phone.text.trim()});
                  await ref.read(authProvider.notifier).refreshProfile();
                  if (mounted) AppToast.show(context, 'Profile updated', isSuccess: true);
                } catch (_) {
                  if (mounted) AppToast.show(context, 'Failed', isError: true);
                }
                setState(() => _saving = false);
              },
            ),
          ])).animate().fadeIn(delay: 120.ms),

          const SizedBox(height: 14),

          // Cloudinary settings
          BrutalCard(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const SectionHeader(title: 'Cloudinary (Voice Notes)', icon: Icons.cloud_upload),
            const SizedBox(height: 4),
            const Text('Voice notes recorded during calls will be uploaded to your Cloudinary unsigned preset.',
                style: AppTextStyles.caption),
            const SizedBox(height: 12),
            BrutalTextField(label: 'Cloud Name', controller: _cloudName, hint: 'e.g. dialeasypro'),
            const SizedBox(height: 12),
            BrutalTextField(label: 'Unsigned Upload Preset', controller: _uploadPreset, hint: 'e.g. voice_notes_unsigned'),
            const SizedBox(height: 14),
            BrutalButton.yellow(
              label: _savingCloud ? 'Saving…' : 'Save Cloudinary',
              isFullWidth: true,
              isLoading: _savingCloud,
              onPressed: () async {
                setState(() => _savingCloud = true);
                final prefs = await SharedPreferences.getInstance();
                await prefs.setString('cloudinary_name', _cloudName.text.trim());
                await prefs.setString('cloudinary_preset', _uploadPreset.text.trim());
                if (_cloudName.text.trim().isNotEmpty && _uploadPreset.text.trim().isNotEmpty) {
                  VoiceRecorderService.instance.configure(
                    cloudName: _cloudName.text.trim(),
                    uploadPreset: _uploadPreset.text.trim(),
                  );
                }
                setState(() => _savingCloud = false);
                if (mounted) AppToast.show(context, 'Cloudinary configured', isSuccess: true);
              },
            ),
          ])).animate().fadeIn(delay: 160.ms),

          const SizedBox(height: 14),

          // Call recording (SIM-based)
          BrutalCard(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const SectionHeader(title: 'Call Recording', icon: Icons.mic_external_on),
            const SizedBox(height: 4),
            const Text(
              'Auto-upload call recordings to the lead. Uses your phone\'s built-in '
              'call recorder when available ("All files access" needed to read its '
              'folder). On phones without one, the app records via the microphone '
              'during the call — use speakerphone to capture both sides.',
              style: AppTextStyles.caption,
            ),
            const SizedBox(height: 12),
            Row(children: [
              Expanded(child: Text(
                _callRecEnabled ? 'Enabled' : 'Disabled',
                style: AppTextStyles.h5,
              )),
              Switch(
                value: _callRecEnabled,
                activeColor: AppColors.success,
                onChanged: (val) async {
                  if (val) {
                    // Best-effort: storage access improves quality (reads the
                    // OEM recorder's file), but the mic fallback works without
                    // it — so never block enabling on this permission.
                    final storageOk = await CallRecordingService.instance.requestStorageAccess();
                    final micOk = (await Permission.microphone.request()).isGranted;
                    if (!storageOk && !micOk && mounted) {
                      AppToast.show(context,
                          'Grant microphone or storage access to record calls', isError: true);
                      return;
                    }
                    if (!storageOk && mounted) {
                      AppToast.show(context,
                          'Mic-only mode: recordings capture your side (both on speaker)');
                    }
                  }
                  await CallRecordingService.instance.setEnabled(val);
                  if (mounted) setState(() => _callRecEnabled = val);
                  if (mounted) {
                    AppToast.show(context, val ? 'Call recording auto-upload ON' : 'Turned off',
                        isSuccess: val);
                  }
                },
              ),
            ]),
            if (_callRecEnabled) ...[
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.all(10),
                color: AppColors.infoBg,
                child: const Text(
                  'Best quality comes from your phone's own call recorder — turn it '
                  'on in the Dialer app settings and grant "All files access" here. '
                  'Without one, the app records through the microphone; put the call '
                  'on speaker so both sides are captured.',
                  style: TextStyle(fontFamily: 'DMSans', fontSize: 11.5, color: AppColors.dark, height: 1.4),
                ),
              ),
              // Recording happens with the app in the background, so a failure
              // is otherwise completely invisible: the agent finishes a call
              // and no recording ever appears, with nothing to explain it.
              if (CallRecordingService.instance.lastError != null) ...[
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: AppColors.white,
                    border: Border.all(color: AppColors.error, width: 2),
                  ),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('LAST RECORDING ISSUE', style: AppTextStyles.label),
                    const SizedBox(height: 4),
                    Text(
                      CallRecordingService.instance.lastError!,
                      style: const TextStyle(
                          fontFamily: 'DMSans', fontSize: 11.5,
                          color: AppColors.dark, height: 1.4),
                    ),
                  ]),
                ),
              ],
            ],
          ])).animate().fadeIn(delay: 180.ms),

          const SizedBox(height: 14),

          // Change password
          BrutalCard(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const SectionHeader(title: 'Change Password', icon: Icons.lock),
            const SizedBox(height: 14),
            BrutalTextField(label: 'Current Password', controller: _oldPw, obscureText: true),
            const SizedBox(height: 12),
            BrutalTextField(label: 'New Password', controller: _newPw, obscureText: true),
            const SizedBox(height: 12),
            BrutalTextField(label: 'Confirm New', controller: _confirmPw, obscureText: true),
            const SizedBox(height: 14),
            BrutalButton.primary(
              label: _changingPw ? 'Changing…' : 'Change Password',
              isLoading: _changingPw,
              onPressed: () async {
                if (_newPw.text != _confirmPw.text) {
                  AppToast.show(context, 'Passwords do not match', isError: true);
                  return;
                }
                setState(() => _changingPw = true);
                final ok = await ref.read(authProvider.notifier).changePassword(
                  oldPw: _oldPw.text, newPw: _newPw.text, confirmPw: _confirmPw.text,
                );
                setState(() => _changingPw = false);
                if (mounted) {
                  if (ok) {
                    _oldPw.clear(); _newPw.clear(); _confirmPw.clear();
                    AppToast.show(context, 'Password changed', isSuccess: true);
                  } else AppToast.show(context, 'Failed', isError: true);
                }
              },
            ),
          ])).animate().fadeIn(delay: 200.ms),

          const SizedBox(height: 14),

          // Account info
          BrutalCard(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const SectionHeader(title: 'Account', icon: Icons.info_outline),
            const SizedBox(height: 8), const Divider(),
            InfoRow(label: 'Employee ID', value: agent?.employeeId.isEmpty == true ? '—' : agent?.employeeId ?? '—'),
            const Divider(),
            InfoRow(label: 'Logins', value: '${agent?.totalLoginCount ?? 0}'),
            const Divider(),
            InfoRow(label: 'Last Active', value: Fmt.relative(agent?.lastActiveAt)),
            const Divider(),
            InfoRow(label: 'Joined', value: Fmt.date(agent?.createdAt)),
          ])).animate().fadeIn(delay: 240.ms),

          const SizedBox(height: 20),

          BrutalButton.danger(
            label: '⏻  Sign Out',
            isFullWidth: true,
            onPressed: () async {
              final ok = await showBrutalConfirm(
                context: context, title: 'Sign Out?',
                message: 'You will be logged out and need to sign in again.',
                confirmLabel: 'Sign Out', danger: true,
              );
              if (ok == true && context.mounted) {
                await ref.read(authProvider.notifier).logout();
                if (context.mounted) context.go('/login');
              }
            },
          ),
          const SizedBox(height: 40),
        ]),
      ),
    );
  }
}

class _WaModeBox extends StatelessWidget {
  final String label, subtitle;
  final bool selected;
  final Color color;
  final VoidCallback onTap;
  const _WaModeBox({required this.label, required this.subtitle, required this.selected, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return BrutalCard(
      onTap: onTap,
      padding: const EdgeInsets.all(10),
      color: selected ? color : AppColors.white,
      shadowOffset: selected ? 3 : 4,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(
            width: 12, height: 12,
            decoration: BoxDecoration(
              color: selected ? AppColors.white : AppColors.white,
              border: Border.all(color: AppColors.black, width: 1.5),
            ),
            child: selected ? const Icon(Icons.check, size: 8, color: AppColors.black) : null,
          ),
          const SizedBox(width: 6),
          Text(label, style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 11, color: selected ? AppColors.white : AppColors.black)),
        ]),
        const SizedBox(height: 3),
        Text(subtitle, style: TextStyle(fontFamily: 'DMSans', fontSize: 10, color: selected ? AppColors.white.withOpacity(0.85) : AppColors.grey)),
      ]),
    );
  }
}
