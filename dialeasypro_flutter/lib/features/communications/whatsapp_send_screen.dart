import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/services/whatsapp_service.dart';
import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../../data/models/models.dart';
import '../../data/services/services.dart';
import '../auth/auth_provider.dart';

final _templatesProvider = FutureProvider.autoDispose<List<WhatsAppTemplate>>((_) => CommsService.instance.listTemplates(approvedOnly: false));

class WhatsAppSendScreen extends ConsumerStatefulWidget {
  final int leadId;
  const WhatsAppSendScreen({super.key, required this.leadId});

  @override
  ConsumerState<WhatsAppSendScreen> createState() => _WhatsAppSendScreenState();
}

class _WhatsAppSendScreenState extends ConsumerState<WhatsAppSendScreen> {
  String _mode = 'native';
  bool _useTemplate = false;
  WhatsAppTemplate? _selectedTemplate;
  final Map<int, TextEditingController> _vars = {};
  final _customCtrl = TextEditingController();
  Lead? _lead;
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    _loadLead();
    UserPrefs.getWhatsAppMode().then((m) => mounted ? setState(() => _mode = m) : null);
  }

  Future<void> _loadLead() async {
    try {
      final l = await LeadsService.instance.getLead(widget.leadId);
      if (mounted) setState(() => _lead = l);
    } catch (_) {}
  }

  @override
  void dispose() {
    _customCtrl.dispose();
    for (final c in _vars.values) c.dispose();
    super.dispose();
  }

  void _selectTemplate(WhatsAppTemplate t) {
    setState(() {
      _selectedTemplate = t;
      _vars.clear();
      // Find {{1}}, {{2}}, etc.
      final regex = RegExp(r'\{\{(\d+)\}\}');
      final matches = regex.allMatches(t.bodyText);
      for (final m in matches) {
        final n = int.parse(m.group(1)!);
        if (!_vars.containsKey(n)) _vars[n] = TextEditingController();
      }
      // Pre-fill {{1}} with lead name
      if (_vars.containsKey(1) && _lead != null) _vars[1]!.text = _lead!.name;
    });
  }

  String _buildMessage() {
    if (_useTemplate && _selectedTemplate != null) {
      var msg = _selectedTemplate!.bodyText;
      _vars.forEach((k, v) => msg = msg.replaceAll('{{$k}}', v.text));
      return msg;
    }
    return _customCtrl.text;
  }

  Future<void> _send() async {
    if (_lead == null) return;
    final msg = _buildMessage();
    if (msg.trim().isEmpty) {
      AppToast.show(context, 'Type a message first', isError: true);
      return;
    }

    setState(() => _sending = true);
    try {
      if (_mode == 'native') {
        final ok = await WhatsAppService.instance.sendNative(phoneNumber: _lead!.phone, message: msg);
        if (mounted) {
          setState(() => _sending = false);
          if (ok) {
            AppToast.show(context, 'WhatsApp opened', isSuccess: true);
            context.pop();
          } else {
            AppToast.show(context, 'WhatsApp not installed', isError: true);
          }
        }
      } else {
        // Cloud
        final ok = await WhatsAppService.instance.sendCloud(
          leadId: _lead!.id, message: msg,
          templateId: _useTemplate ? _selectedTemplate?.id : null,
        );
        if (mounted) {
          setState(() => _sending = false);
          if (ok) {
            AppToast.show(context, 'Message sent via Cloud API', isSuccess: true);
            context.pop();
          } else {
            AppToast.show(context, 'Cloud send failed. Check API config.', isError: true);
          }
        }
      }
    } catch (_) {
      setState(() => _sending = false);
      if (mounted) AppToast.show(context, 'Send failed', isError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final templatesAsync = ref.watch(_templatesProvider);

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Send WhatsApp'),
        leading: IconButton(icon: const Icon(Icons.arrow_back, color: AppColors.black), onPressed: () => context.pop()),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          // Lead summary
          if (_lead != null) BrutalCard(
            padding: const EdgeInsets.all(14),
            color: AppColors.tealBg,
            borderColor: AppColors.teal,
            child: Row(children: [
              Container(
                width: 44, height: 44,
                decoration: BoxDecoration(color: AppColors.teal, border: Border.all(color: AppColors.black, width: 1.5)),
                child: const Icon(Icons.chat_bubble, color: AppColors.white, size: 20),
              ),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(_lead!.name, style: AppTextStyles.h5),
                Text(Fmt.displayPhone(_lead!.phone), style: AppTextStyles.mono),
              ])),
            ]),
          ).animate().fadeIn(),

          const SizedBox(height: 16),

          // Mode selector
          const Text('SEND VIA', style: AppTextStyles.label),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(child: _ModeOption(
              label: 'Native', subtitle: 'Open WhatsApp', icon: Icons.open_in_new,
              selected: _mode == 'native', color: AppColors.success,
              onTap: () { setState(() => _mode = 'native'); UserPrefs.setWhatsAppMode('native'); },
            )),
            const SizedBox(width: 10),
            Expanded(child: _ModeOption(
              label: 'Cloud API', subtitle: 'Direct send', icon: Icons.cloud_upload,
              selected: _mode == 'cloud', color: AppColors.purple,
              onTap: () { setState(() => _mode = 'cloud'); UserPrefs.setWhatsAppMode('cloud'); },
            )),
          ]),

          const SizedBox(height: 20),

          // Template toggle
          BrutalCard(
            padding: const EdgeInsets.all(12),
            child: Row(children: [
              const Icon(Icons.description_outlined, size: 18),
              const SizedBox(width: 10),
              const Expanded(child: Text('Use Template', style: AppTextStyles.bodyBold)),
              Switch(
                value: _useTemplate,
                onChanged: (v) => setState(() { _useTemplate = v; if (!v) _selectedTemplate = null; }),
                activeColor: AppColors.yellow, activeTrackColor: AppColors.dark,
              ),
            ]),
          ),

          const SizedBox(height: 14),

          if (_useTemplate) ...[
            templatesAsync.when(
              loading: () => const ShimmerCard(height: 100),
              error: (_, __) => const Text('Failed to load templates'),
              data: (templates) => templates.isEmpty
                  ? Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(color: AppColors.warningBg, border: Border.all(color: AppColors.warning, width: 1.5)),
                      child: const Row(children: [
                        Icon(Icons.warning_amber_rounded, color: AppColors.warning),
                        SizedBox(width: 10),
                        Expanded(child: Text('No templates yet. Ask admin to create some.', style: AppTextStyles.body)),
                      ]),
                    )
                  : Column(crossAxisAlignment: CrossAxisAlignment.start, children: templates.map((t) {
                      final sel = _selectedTemplate?.id == t.id;
                      return Padding(padding: const EdgeInsets.only(bottom: 8), child: BrutalCard(
                        onTap: () => _selectTemplate(t),
                        padding: const EdgeInsets.all(12),
                        color: sel ? AppColors.yellow : AppColors.white,
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Row(children: [
                            Expanded(child: Text(t.name, style: AppTextStyles.h5)),
                            TagChip(label: t.status, backgroundColor: t.status == 'approved' ? AppColors.successBg : AppColors.warningBg),
                          ]),
                          const SizedBox(height: 6),
                          Text(t.bodyText, style: AppTextStyles.caption, maxLines: 3, overflow: TextOverflow.ellipsis),
                        ]),
                      ));
                    }).toList()),
            ),

            // Variable inputs
            if (_selectedTemplate != null && _vars.isNotEmpty) ...[
              const SizedBox(height: 16),
              const Text('TEMPLATE VARIABLES', style: AppTextStyles.label),
              const SizedBox(height: 8),
              ..._vars.entries.map((e) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: BrutalTextField(label: 'Variable {{${e.key}}}', controller: e.value, hint: 'Enter value'),
              )),
            ],
          ] else ...[
            BrutalTextField(label: 'Message', controller: _customCtrl, hint: 'Type your message…', maxLines: 6, minLines: 4, onChanged: (_) => setState((){})),
          ],

          const SizedBox(height: 16),

          // Preview
          if ((_useTemplate && _selectedTemplate != null) || _customCtrl.text.isNotEmpty) Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFE7FFDB),
              border: Border.all(color: AppColors.success, width: 2),
              boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(3, 3))],
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Row(children: [
                Icon(Icons.preview, size: 14, color: AppColors.success),
                SizedBox(width: 6),
                Text('PREVIEW', style: AppTextStyles.label),
              ]),
              const SizedBox(height: 8),
              Text(_buildMessage(), style: AppTextStyles.body),
            ]),
          ),

          const SizedBox(height: 24),

          BrutalButton(
            label: _sending ? 'Sending…' : 'SEND WHATSAPP →',
            iconData: Icons.send,
            backgroundColor: _mode == 'native' ? AppColors.success : AppColors.purple,
            textColor: AppColors.white,
            isFullWidth: true, shadowOffset: 5,
            isLoading: _sending,
            onPressed: _sending ? null : _send,
          ),
          const SizedBox(height: 30),
        ]),
      ),
    );
  }
}

class _ModeOption extends StatelessWidget {
  final String label, subtitle;
  final IconData icon;
  final bool selected;
  final Color color;
  final VoidCallback onTap;

  const _ModeOption({
    required this.label, required this.subtitle, required this.icon,
    required this.selected, required this.color, required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return BrutalCard(
      onTap: onTap,
      padding: const EdgeInsets.all(14),
      color: selected ? color : AppColors.white,
      borderColor: AppColors.black,
      shadowOffset: selected ? 3 : 4,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, size: 24, color: selected ? AppColors.white : color),
        const SizedBox(height: 8),
        Text(label, style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 14, color: selected ? AppColors.white : AppColors.black)),
        Text(subtitle, style: TextStyle(fontFamily: 'DMSans', fontSize: 10, color: selected ? AppColors.white.withOpacity(0.85) : AppColors.grey)),
        const SizedBox(height: 6),
        if (selected) const Row(children: [
          Icon(Icons.check_circle, size: 14, color: AppColors.white),
          SizedBox(width: 4),
          Text('ACTIVE', style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 9, color: AppColors.white, letterSpacing: 0.4)),
        ]),
      ]),
    );
  }
}
