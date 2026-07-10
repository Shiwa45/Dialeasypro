import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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
import '../dialer/dialer_state.dart';

final _leadDetailProvider = FutureProvider.autoDispose.family<Lead, int>((_, id) => LeadsService.instance.getLead(id));
final _notesProvider = FutureProvider.autoDispose.family<List<LeadNote>, int>((_, id) => LeadsService.instance.listNotes(id).then((r) => r.results));
final _followupsProvider = FutureProvider.autoDispose.family<List<FollowUp>, int>((_, id) => LeadsService.instance.listFollowups(id).then((r) => r.results));
final _callsForLeadProvider = FutureProvider.autoDispose.family<List<CallLog>, int>((_, id) => CallsService.instance.listCalls(leadId: id.toString()).then((r) => r.results));

class LeadDetailScreen extends ConsumerStatefulWidget {
  final int leadId;
  const LeadDetailScreen({super.key, required this.leadId});

  @override
  ConsumerState<LeadDetailScreen> createState() => _LeadDetailScreenState();
}

class _LeadDetailScreenState extends ConsumerState<LeadDetailScreen> with SingleTickerProviderStateMixin {
  late TabController _tab;
  final _noteCtrl = TextEditingController();
  static const _tabs = ['Overview', 'Notes', 'Follow-ups', 'Calls'];

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: _tabs.length, vsync: this);
  }

  @override
  void dispose() {
    _tab.dispose();
    _noteCtrl.dispose();
    super.dispose();
  }

  Future<void> _callLead(Lead lead) async {
    HapticFeedback.heavyImpact();
    await ref.read(dialerProvider.notifier).startSingleCall(lead);
    if (mounted) context.push('/dialer');
  }

  Future<void> _whatsAppLead(Lead lead) async {
    final mode = await UserPrefs.getWhatsAppMode();
    if (!mounted) return;
    if (mode == 'cloud') {
      context.push('/leads/${lead.id}/whatsapp');
    } else {
      // Native — quick dialog with custom message
      _showNativeWAQuick(lead);
    }
  }

  void _showNativeWAQuick(Lead lead) {
    final msgCtrl = TextEditingController();
    showBrutalBottomSheet(
      context: context,
      builder: (ctx) => Padding(
        padding: const EdgeInsets.all(20),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(color: AppColors.successBg, border: Border.all(color: AppColors.success, width: 1.5)),
              child: const Icon(Icons.chat_bubble, color: AppColors.success, size: 20),
            ),
            const SizedBox(width: 10),
            const Expanded(child: Text('Open in WhatsApp', style: AppTextStyles.h3)),
            const TagChip(label: 'NATIVE'),
          ]),
          const SizedBox(height: 14),
          Text(Fmt.displayPhone(lead.phone), style: AppTextStyles.mono),
          const SizedBox(height: 14),
          BrutalTextField(controller: msgCtrl, label: 'Message (optional)', hint: 'Type a quick message…', maxLines: 3),
          const SizedBox(height: 16),
          BrutalButton(
            label: 'OPEN WHATSAPP →',
            iconData: Icons.open_in_new,
            backgroundColor: AppColors.success, textColor: AppColors.white,
            isFullWidth: true,
            onPressed: () async {
              Navigator.pop(ctx);
              final ok = await WhatsAppService.instance.sendNative(
                phoneNumber: lead.phone,
                message: msgCtrl.text.isEmpty ? null : msgCtrl.text,
              );
              if (mounted) {
                if (!ok) AppToast.show(context, 'WhatsApp not installed', isError: true);
              }
            },
          ),
        ]),
      ),
    );
  }

  Future<void> _updateStatus(int id, String status) async {
    try {
      await LeadsService.instance.updateStatus(id, status);
      ref.invalidate(_leadDetailProvider(id));
      if (mounted) AppToast.show(context, 'Status updated', isSuccess: true);
    } catch (_) {
      if (mounted) AppToast.show(context, 'Update failed', isError: true);
    }
  }

  Future<void> _addNote(int id) async {
    if (_noteCtrl.text.trim().isEmpty) return;
    try {
      await LeadsService.instance.createNote(id, _noteCtrl.text.trim());
      _noteCtrl.clear();
      ref.invalidate(_notesProvider(id));
      if (mounted) AppToast.show(context, 'Note added', isSuccess: true);
    } catch (_) {
      if (mounted) AppToast.show(context, 'Failed', isError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(_leadDetailProvider(widget.leadId));
    return async.when(
      loading: () => const Scaffold(body: Center(child: CircularProgressIndicator(color: AppColors.yellow))),
      error: (e, _) => Scaffold(appBar: AppBar(), body: Center(child: Text(e.toString()))),
      data: (lead) => _build(lead),
    );
  }

  Widget _build(Lead lead) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: NestedScrollView(
        headerSliverBuilder: (_, __) => [
          SliverAppBar(
            pinned: true, expandedHeight: 200, backgroundColor: AppColors.white,
            leading: IconButton(icon: const Icon(Icons.arrow_back, color: AppColors.black), onPressed: () => context.pop()),
            actions: [
              IconButton(icon: const Icon(Icons.edit_outlined, color: AppColors.black), onPressed: () => context.push('/leads/${lead.id}/edit')),
              PopupMenuButton<String>(
                icon: const Icon(Icons.more_vert, color: AppColors.black),
                shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero, side: BorderSide(color: AppColors.black, width: 2)),
                onSelected: (v) {
                  if (v == 'copy') {
                    Clipboard.setData(ClipboardData(text: lead.phone));
                    AppToast.show(context, 'Phone copied');
                  }
                  if (v == 'sms') {
                    // launch SMS
                  }
                },
                itemBuilder: (_) => const [
                  PopupMenuItem(value: 'copy', child: Text('Copy Phone')),
                  PopupMenuItem(value: 'sms', child: Text('Send SMS')),
                ],
              ),
            ],
            flexibleSpace: FlexibleSpaceBar(background: _Header(lead: lead, onStatus: _updateStatus)),
            bottom: TabBar(controller: _tab, isScrollable: true, tabs: _tabs.map((t) => Tab(text: t)).toList()),
          ),
        ],
        body: TabBarView(controller: _tab, children: [
          _OverviewTab(lead: lead),
          _NotesTab(leadId: lead.id, noteCtrl: _noteCtrl, onAdd: () => _addNote(lead.id)),
          _FollowupsTab(leadId: lead.id),
          _CallsTab(leadId: lead.id),
        ]),
      ),
      bottomNavigationBar: _ActionBar(lead: lead, onCall: () => _callLead(lead), onWhatsApp: () => _whatsAppLead(lead)),
    );
  }
}

// ─── Header ─────────────────────────────────────────────────
class _Header extends StatelessWidget {
  final Lead lead;
  final Function(int, String) onStatus;
  const _Header({required this.lead, required this.onStatus});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 70, 16, 0),
      color: AppColors.white,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          BrutalAvatar(name: lead.name, size: 60),
          const SizedBox(width: 14),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(lead.name, style: AppTextStyles.h2, overflow: TextOverflow.ellipsis),
            const SizedBox(height: 3),
            Text(Fmt.displayPhone(lead.phone), style: AppTextStyles.monoLg.copyWith(fontSize: 13, color: AppColors.greyDark)),
            const SizedBox(height: 6),
            Wrap(spacing: 6, runSpacing: 4, children: [
              StatusBadge(status: lead.status, label: lead.statusDisplay, large: true),
              PriorityBadge(priority: lead.priority),
              if (lead.isDnd) const TagChip(label: 'DND', backgroundColor: AppColors.error, textColor: AppColors.white),
            ]),
          ])),
        ]),
        const SizedBox(height: 10),
        SizedBox(height: 32, child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(children: Fmt.leadStatusLabels.entries.take(6).map((e) {
            final active = lead.status == e.key;
            return GestureDetector(
              onTap: () => onStatus(lead.id, e.key),
              child: Container(
                margin: const EdgeInsets.only(right: 6),
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: active ? AppColors.black : AppColors.white,
                  border: Border.all(color: AppColors.black, width: active ? 2 : 1.5),
                ),
                child: Text(e.value,
                    style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10, color: active ? AppColors.white : AppColors.dark)),
              ),
            );
          }).toList()),
        )),
      ]),
    );
  }
}

// ─── Overview Tab ───────────────────────────────────────────
class _OverviewTab extends StatelessWidget {
  final Lead lead;
  const _OverviewTab({required this.lead});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(children: [
        BrutalCard(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionHeader(title: 'Contact', icon: Icons.contact_mail),
          const SizedBox(height: 8), const Divider(),
          InfoRow(label: 'Phone', value: Fmt.displayPhone(lead.phone), icon: Icons.phone),
          if (lead.alternatePhone.isNotEmpty) ...[const Divider(), InfoRow(label: 'Alt Phone', value: Fmt.displayPhone(lead.alternatePhone))],
          const Divider(),
          InfoRow(label: 'Email', value: lead.email.isEmpty ? '—' : lead.email, icon: Icons.mail_outline),
          const Divider(), InfoRow(label: 'City', value: lead.city.isEmpty ? '—' : lead.city, icon: Icons.location_on_outlined),
          const Divider(), InfoRow(label: 'State', value: lead.state.isEmpty ? '—' : lead.state),
          const Divider(), InfoRow(label: 'Source', value: Fmt.sourceLabels[lead.source] ?? lead.source),
          const Divider(), InfoRow(label: 'Assigned To', value: lead.assignedToName ?? '—'),
        ])).animate().fadeIn(),
        const SizedBox(height: 12),
        BrutalCard(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionHeader(title: 'Sales', icon: Icons.trending_up),
          const SizedBox(height: 8), const Divider(),
          InfoRow(label: 'Budget', value: lead.budget != null ? Fmt.inr(lead.budget) : '—'),
          const Divider(), InfoRow(label: 'Deal Value', value: lead.dealValue != null ? Fmt.inr(lead.dealValue) : '—'),
          const Divider(),
          Row(children: [
            const Expanded(flex: 2, child: Text('SCORE', style: AppTextStyles.label)),
            Expanded(flex: 3, child: ScoreBar(score: lead.score)),
          ]),
          const Divider(), InfoRow(label: 'Contacts', value: '${lead.contactCount}×'),
          const Divider(), InfoRow(label: 'Last Contact', value: Fmt.relative(lead.lastContactedAt)),
          const Divider(), InfoRow(label: 'Next F/U', value: lead.nextFollowupAt != null ? Fmt.dateTime(lead.nextFollowupAt) : '—'),
          const Divider(), InfoRow(label: 'Created', value: Fmt.date(lead.createdAt)),
        ])).animate().fadeIn(delay: 100.ms),
        if (lead.requirement.isNotEmpty) ...[
          const SizedBox(height: 12),
          BrutalCard(padding: const EdgeInsets.all(16), color: AppColors.cream, borderColor: AppColors.yellow,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const SectionHeader(title: 'Requirement', icon: Icons.assignment),
              const SizedBox(height: 10),
              Text(lead.requirement, style: AppTextStyles.bodyLg.copyWith(height: 1.5)),
            ]),
          ).animate().fadeIn(delay: 150.ms),
        ],
        if (lead.tags.isNotEmpty) ...[
          const SizedBox(height: 12),
          BrutalCard(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('TAGS', style: AppTextStyles.label),
            const SizedBox(height: 10),
            Wrap(spacing: 6, runSpacing: 6, children: lead.tags.map((t) => TagChip(label: t)).toList()),
          ])).animate().fadeIn(delay: 200.ms),
        ],
        const SizedBox(height: 100),
      ]),
    );
  }
}

// ─── Notes Tab ──────────────────────────────────────────────
class _NotesTab extends ConsumerWidget {
  final int leadId;
  final TextEditingController noteCtrl;
  final VoidCallback onAdd;
  const _NotesTab({required this.leadId, required this.noteCtrl, required this.onAdd});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_notesProvider(leadId));
    return Column(children: [
      Container(
        padding: const EdgeInsets.all(12),
        decoration: const BoxDecoration(color: AppColors.white, border: Border(bottom: BorderSide(color: AppColors.black, width: 2))),
        child: Row(children: [
          Expanded(child: BrutalTextField(controller: noteCtrl, hint: 'Add a note…', maxLines: 3, minLines: 1)),
          const SizedBox(width: 10),
          BrutalButton.primary(label: 'Add', isFullWidth: false, onPressed: onAdd, padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12)),
        ]),
      ),
      Expanded(child: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, __) => const EmptyStateView(icon: Icons.error_outline, title: 'Failed'),
        data: (notes) => notes.isEmpty
            ? const EmptyStateView(icon: Icons.note_add, title: 'No notes yet', message: 'Add the first note above')
            : ListView.builder(
                padding: const EdgeInsets.all(12), itemCount: notes.length,
                itemBuilder: (_, i) => Padding(padding: const EdgeInsets.only(bottom: 10),
                  child: BrutalCard(
                    padding: const EdgeInsets.all(14),
                    color: notes[i].isPinned ? AppColors.cream : AppColors.white,
                    borderColor: notes[i].isPinned ? AppColors.yellow : AppColors.black,
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Row(children: [
                        Text(notes[i].agentName ?? 'System', style: AppTextStyles.h5),
                        if (notes[i].isPinned) const Padding(padding: EdgeInsets.only(left: 6), child: Text('📌', style: TextStyle(fontSize: 12))),
                        const Spacer(),
                        Text(Fmt.relative(notes[i].createdAt), style: AppTextStyles.caption),
                      ]),
                      const SizedBox(height: 8),
                      Text(notes[i].content, style: AppTextStyles.body),
                    ]),
                  ).animate().fadeIn(delay: Duration(milliseconds: i * 50)),
                ),
              ),
      )),
    ]);
  }
}

// ─── Follow-ups Tab ─────────────────────────────────────────
class _FollowupsTab extends ConsumerWidget {
  final int leadId;
  const _FollowupsTab({required this.leadId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_followupsProvider(leadId));
    return Column(children: [
      Container(
        padding: const EdgeInsets.all(12),
        decoration: const BoxDecoration(color: AppColors.white, border: Border(bottom: BorderSide(color: AppColors.black, width: 2))),
        child: BrutalButton.primary(label: '+ SCHEDULE FOLLOW-UP', iconData: Icons.event, onPressed: () => _showFollowupSheet(context, ref, leadId)),
      ),
      Expanded(child: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, __) => const EmptyStateView(icon: Icons.error_outline, title: 'Failed'),
        data: (followups) => followups.isEmpty
            ? const EmptyStateView(icon: Icons.event_busy, title: 'No follow-ups')
            : ListView.builder(
                padding: const EdgeInsets.all(12), itemCount: followups.length,
                itemBuilder: (_, i) {
                  final fu = followups[i];
                  return Padding(padding: const EdgeInsets.only(bottom: 10), child: BrutalCard(
                    padding: const EdgeInsets.all(14),
                    color: fu.isCompleted ? AppColors.successBg : fu.isOverdue ? AppColors.errorBg : AppColors.white,
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Row(children: [
                          TagChip(label: fu.followupTypeDisplay.isEmpty ? fu.followupType : fu.followupTypeDisplay),
                          if (fu.isCompleted) const Padding(padding: EdgeInsets.only(left: 6), child: TagChip(label: '✓ Done', backgroundColor: AppColors.success, textColor: AppColors.white)),
                          if (fu.isOverdue && !fu.isCompleted) const Padding(padding: EdgeInsets.only(left: 6), child: TagChip(label: '⚠ Overdue', backgroundColor: AppColors.error, textColor: AppColors.white)),
                        ]),
                        const SizedBox(height: 6),
                        Text(Fmt.dateTime(fu.scheduledAt), style: AppTextStyles.bodyBold),
                        if (fu.notes.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 4), child: Text(fu.notes, style: AppTextStyles.caption)),
                      ])),
                      if (!fu.isCompleted) BrutalButton.yellow(
                        label: '✓',
                        isFullWidth: false,
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        onPressed: () async {
                          await LeadsService.instance.completeFollowup(fu.id);
                          ref.invalidate(_followupsProvider(leadId));
                          if (context.mounted) AppToast.show(context, 'Marked done', isSuccess: true);
                        },
                      ),
                    ]),
                  ).animate().fadeIn(delay: Duration(milliseconds: i * 50)));
                },
              ),
      )),
    ]);
  }

  void _showFollowupSheet(BuildContext context, WidgetRef ref, int leadId) {
    String type = 'call';
    DateTime? when;
    final notesCtrl = TextEditingController();

    showBrutalBottomSheet(context: context, builder: (ctx) => StatefulBuilder(builder: (ctx, setState) => Padding(
      padding: const EdgeInsets.all(20),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        const Text('Schedule Follow-up', style: AppTextStyles.h2),
        const SizedBox(height: 14),
        const Text('TYPE', style: AppTextStyles.label),
        const SizedBox(height: 6),
        Wrap(spacing: 6, children: ['call', 'whatsapp', 'email', 'visit', 'meeting'].map((t) {
          final sel = type == t;
          return GestureDetector(
            onTap: () => setState(() => type = t),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: sel ? AppColors.black : AppColors.white,
                border: Border.all(color: AppColors.black, width: sel ? 2 : 1.5),
              ),
              child: Text(t.toUpperCase(), style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10, color: sel ? AppColors.white : AppColors.black)),
            ),
          );
        }).toList()),
        const SizedBox(height: 14),
        const Text('WHEN', style: AppTextStyles.label),
        const SizedBox(height: 6),
        Row(children: [
          Expanded(child: BrutalButton.secondary(label: '+1 hour', isFullWidth: true, onPressed: () => setState(() => when = DateTime.now().add(const Duration(hours: 1))))),
          const SizedBox(width: 6),
          Expanded(child: BrutalButton.secondary(label: 'Tomorrow', isFullWidth: true, onPressed: () => setState(() => when = DateTime.now().add(const Duration(days: 1))))),
          const SizedBox(width: 6),
          Expanded(child: BrutalButton.secondary(label: 'Pick', isFullWidth: true, onPressed: () async {
            final d = await showDatePicker(context: ctx, initialDate: DateTime.now().add(const Duration(days: 1)), firstDate: DateTime.now(), lastDate: DateTime.now().add(const Duration(days: 365)));
            if (d != null && ctx.mounted) {
              final t = await showTimePicker(context: ctx, initialTime: const TimeOfDay(hour: 10, minute: 0));
              if (t != null) setState(() => when = DateTime(d.year, d.month, d.day, t.hour, t.minute));
            }
          })),
        ]),
        if (when != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text('Scheduled: ${Fmt.dateTime(when!.toIso8601String())}', style: AppTextStyles.bodyBold.copyWith(color: AppColors.warning))),
        const SizedBox(height: 14),
        BrutalTextField(controller: notesCtrl, label: 'Notes', maxLines: 2),
        const SizedBox(height: 18),
        BrutalButton.primary(label: 'Schedule →', onPressed: when == null ? null : () async {
          try {
            await LeadsService.instance.createFollowup(leadId, {
              'followup_type': type, 'scheduled_at': when!.toUtc().toIso8601String(),
              'notes': notesCtrl.text, 'assigned_to': 0,
            });
            ref.invalidate(_followupsProvider(leadId));
            if (ctx.mounted) { Navigator.pop(ctx); AppToast.show(context, 'Follow-up scheduled', isSuccess: true); }
          } catch (_) {
            if (ctx.mounted) AppToast.show(ctx, 'Failed', isError: true);
          }
        }),
      ]),
    )));
  }
}

// ─── Calls Tab ──────────────────────────────────────────────
class _CallsTab extends ConsumerWidget {
  final int leadId;
  const _CallsTab({required this.leadId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_callsForLeadProvider(leadId));
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (_, __) => const EmptyStateView(icon: Icons.error_outline, title: 'Failed'),
      data: (calls) => calls.isEmpty
          ? const EmptyStateView(icon: Icons.phone_disabled, title: 'No calls yet', message: 'Tap CALL to dial')
          : ListView.builder(padding: const EdgeInsets.all(12), itemCount: calls.length, itemBuilder: (_, i) {
              final c = calls[i];
              return Padding(padding: const EdgeInsets.only(bottom: 10), child: BrutalCard(padding: const EdgeInsets.all(14), child: Row(children: [
                Container(width: 38, height: 38, decoration: BoxDecoration(
                  color: c.isConnected ? AppColors.successBg : AppColors.greyLight,
                  border: Border.all(color: AppColors.black, width: 1.5),
                ), child: Icon(c.direction == 'outbound' ? Icons.call_made : Icons.call_received,
                    size: 16, color: c.isConnected ? AppColors.success : AppColors.grey)),
                const SizedBox(width: 12),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Text(c.durationDisplay, style: AppTextStyles.h5),
                    const SizedBox(width: 8),
                    if (c.isConnected) const TagChip(label: 'Connected', backgroundColor: AppColors.success, textColor: AppColors.white)
                    else const TagChip(label: 'No Answer', backgroundColor: AppColors.greyLight),
                    if (c.dispositionName != null) Padding(padding: const EdgeInsets.only(left: 6), child: TagChip(label: c.dispositionName!)),
                  ]),
                  const SizedBox(height: 3),
                  Text(Fmt.relative(c.startedAt), style: AppTextStyles.caption),
                  if (c.notes.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 4), child: Text(c.notes, style: AppTextStyles.caption, maxLines: 2, overflow: TextOverflow.ellipsis)),
                  if (c.recordingUrl != null) Padding(padding: const EdgeInsets.only(top: 4), child: Row(children: [
                    const Icon(Icons.mic, size: 12, color: AppColors.purple),
                    const SizedBox(width: 3),
                    const Text('Recording', style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10, color: AppColors.purple)),
                  ])),
                ])),
              ])).animate().fadeIn(delay: Duration(milliseconds: i * 50)));
            }),
    );
  }
}

// ─── Action Bar (sticky bottom: CALL + WHATSAPP) ────────────
class _ActionBar extends StatelessWidget {
  final Lead lead;
  final VoidCallback onCall, onWhatsApp;
  const _ActionBar({required this.lead, required this.onCall, required this.onWhatsApp});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      decoration: const BoxDecoration(
        color: AppColors.white,
        border: Border(top: BorderSide(color: AppColors.black, width: 2)),
        boxShadow: [BoxShadow(color: AppColors.black, offset: Offset(0, -3))],
      ),
      child: SafeArea(
        child: Row(children: [
          Expanded(child: BrutalButton(
            label: 'CALL',
            iconData: Icons.phone,
            backgroundColor: AppColors.success, textColor: AppColors.white,
            isFullWidth: true, shadowOffset: 4,
            onPressed: onCall,
          )),
          const SizedBox(width: 10),
          Expanded(child: BrutalButton(
            label: 'WHATSAPP',
            iconData: Icons.chat_bubble,
            backgroundColor: AppColors.teal, textColor: AppColors.white,
            isFullWidth: true, shadowOffset: 4,
            onPressed: onWhatsApp,
          )),
        ]),
      ),
    );
  }
}
