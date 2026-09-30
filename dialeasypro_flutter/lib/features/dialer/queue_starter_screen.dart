import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/colors.dart';
import '../../core/widgets/widgets.dart';
import '../../data/services/services.dart';
import '../work/work_session.dart';
import 'dialer_state.dart';

// ============================================================
// DialEasypro — Queue Starter Screen
// Shows the admin-defined calling queues this agent is assigned to.
// Each queue pulls leads one at a time from the server — no lead is ever
// served to two agents or repeated (enforced server-side via locking,
// worked-state, and redial cooldown).
// ============================================================

final availableQueuesProvider = FutureProvider.autoDispose<List<Map<String, dynamic>>>((_) {
  return QueueService.instance.available();
});

/// How each queue orders its leads, as the admin chose it on the web.
const _orderLabels = {
  'priority': 'Highest priority first',
  'oldest': 'Oldest leads first',
  'newest': 'Newest leads first',
  'score': 'Highest score first',
  'followup_due': 'Follow-ups due first',
};

class QueueStarterScreen extends ConsumerWidget {
  /// Shown as the Auto Dial home tab: no back button, and [header] (the live
  /// status strip) above the queues.
  final bool embedded;
  final Widget? header;
  final List<Widget> actions;
  const QueueStarterScreen({super.key, this.embedded = false, this.header, this.actions = const []});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(availableQueuesProvider);
    final onBreak = ref.watch(workSessionProvider).onBreak;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text(embedded ? 'Auto Dial' : 'Auto-Dialer Queues'),
        automaticallyImplyLeading: false,
        leading: embedded
            ? null
            : IconButton(icon: const Icon(Icons.arrow_back, color: AppColors.black), onPressed: () => context.pop()),
        actions: actions,
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(availableQueuesProvider),
        child: async.when(
          loading: () => ListView(padding: const EdgeInsets.all(16), children: [
            if (header != null) ...[header!, const SizedBox(height: 20)],
            ...List.generate(
                3, (_) => const Padding(padding: EdgeInsets.only(bottom: 12), child: ShimmerCard(height: 96))),
          ]),
          error: (e, _) =>
              EmptyStateView(icon: Icons.error_outline, title: 'Could not load queues', message: e.toString()),
          data: (queues) {
            final ready = queues.fold<int>(0, (sum, q) => sum + ((q['pending_count'] as num?)?.toInt() ?? 0));
            return ListView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
              children: [
                if (header != null) ...[header!, const SizedBox(height: 24)],

                // ---- Section heading ----
                Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  const Expanded(child: Text('Your queues', style: AppTextStyles.h3)),
                  if (queues.isNotEmpty)
                    Text(
                      '${queues.length} queue${queues.length == 1 ? '' : 's'} · $ready ready',
                      style: AppTextStyles.mono.copyWith(fontSize: 12),
                    ),
                ]),
                const SizedBox(height: 4),
                const Text(
                  'Leads are dialled one after another. Save each call\'s outcome to move on.',
                  style: AppTextStyles.caption,
                ),
                const SizedBox(height: 14),

                if (queues.isEmpty)
                  const _NoQueues().animate().fadeIn()
                else
                  ...queues.asMap().entries.map((entry) {
                    final i = entry.key;
                    final q = entry.value;
                    final count = (q['pending_count'] as num?)?.toInt() ?? 0;
                    final description = (q['description'] as String?)?.trim() ?? '';
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: _QueueCard(
                        title: q['name'] as String? ?? 'Queue',
                        description: description,
                        order: _orderLabels[q['order_by']],
                        count: count,
                        isAuto: q['mode'] == 'auto',
                        onBreak: onBreak,
                        // Greyed out on a break; tapping still explains why.
                        onTap: count == 0 ? null : () => _startQueue(context, ref, q['id'] as int),
                      ).animate().fadeIn(delay: (60 + i * 50).ms).slideY(begin: 0.06, end: 0),
                    );
                  }),

                const SizedBox(height: 12),
                const _HowItWorks().animate().fadeIn(delay: 250.ms),
              ],
            );
          },
        ),
      ),
    );
  }

  Future<void> _startQueue(BuildContext context, WidgetRef ref, int queueId) async {
    // No auto-dialling on a break: time on a break is not dialling time, and
    // the login report counts it separately. The agent ends the break first.
    if (ref.read(workSessionProvider).onBreak) {
      AppToast.show(context, 'You are on a break. End your break to start auto-dialing.', isError: true);
      return;
    }
    ref.read(dialerProvider.notifier).startServerQueue(queueId);
    if (context.mounted) context.push('/dialer');
  }
}

class _QueueCard extends StatelessWidget {
  final String title, description;
  final String? order;
  final int count;
  final bool isAuto;
  final bool onBreak;
  final VoidCallback? onTap;
  const _QueueCard({
    required this.title,
    required this.description,
    required this.order,
    required this.count,
    required this.isAuto,
    required this.onBreak,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final empty = count == 0;
    final ready = !empty && !onBreak;

    // The shadow sits on an outer box and the white card is the Material on
    // top of it, so the ripple and the fill both stay above the shadow.
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(color: AppColors.ink.withValues(alpha: 0.06), blurRadius: 16, offset: const Offset(0, 4)),
        ],
      ),
      child: Material(
        color: AppColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: AppColors.line),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(children: [
              // ---- Leads ready ----
              Container(
                width: 64,
                padding: const EdgeInsets.symmetric(vertical: 10),
                decoration: BoxDecoration(
                  color: empty ? AppColors.sunken : AppColors.brand50,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(children: [
                  Text(
                    '$count',
                    style: AppTextStyles.monoLg.copyWith(
                      fontSize: count > 999 ? 16 : 22,
                      color: empty ? AppColors.text3 : AppColors.brandInk,
                    ),
                  ),
                  Text(
                    'READY',
                    style:
                        AppTextStyles.label.copyWith(fontSize: 9, color: empty ? AppColors.text3 : AppColors.brandInk),
                  ),
                ]),
              ),
              const SizedBox(width: 14),

              // ---- Name, mode, order ----
              Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(title, style: AppTextStyles.h4, maxLines: 1, overflow: TextOverflow.ellipsis),
                if (description.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(description, style: AppTextStyles.caption, maxLines: 2, overflow: TextOverflow.ellipsis),
                ],
                const SizedBox(height: 8),
                Wrap(spacing: 6, runSpacing: 6, children: [
                  _Chip(
                    icon: isAuto ? Icons.bolt : Icons.touch_app_outlined,
                    label: isAuto ? 'Power dial' : 'Manual pull',
                    color: isAuto ? AppColors.brass : AppColors.text2,
                    background: isAuto ? AppColors.brass50 : AppColors.sunken,
                  ),
                  if (order != null)
                    _Chip(
                      icon: Icons.sort,
                      label: order!,
                      color: AppColors.text2,
                      background: AppColors.sunken,
                    ),
                ]),
              ])),
              const SizedBox(width: 12),

              // ---- Start ----
              Column(mainAxisSize: MainAxisSize.min, children: [
                Container(
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: ready ? AppColors.brand : AppColors.sunken,
                    boxShadow: ready
                        ? [
                            BoxShadow(
                                color: AppColors.brand.withValues(alpha: 0.35),
                                blurRadius: 12,
                                offset: const Offset(0, 4))
                          ]
                        : null,
                  ),
                  child: Icon(
                    empty
                        ? Icons.inbox_outlined
                        : onBreak
                            ? Icons.lock_outline
                            : Icons.play_arrow_rounded,
                    color: ready ? AppColors.white : AppColors.text3,
                    size: ready ? 28 : 20,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  empty
                      ? 'Empty'
                      : onBreak
                          ? 'On break'
                          : 'Start',
                  style:
                      AppTextStyles.label.copyWith(fontSize: 9.5, color: ready ? AppColors.brandInk : AppColors.text3),
                ),
              ]),
            ]),
          ),
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color, background;
  const _Chip({required this.icon, required this.label, required this.color, required this.background});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(999)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 4),
          Text(label, style: AppTextStyles.caption.copyWith(fontSize: 11, fontWeight: FontWeight.w600, color: color)),
        ]),
      );
}

class _NoQueues extends StatelessWidget {
  const _NoQueues();

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 28),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppColors.line),
        ),
        child: Column(children: [
          Container(
            width: 56,
            height: 56,
            decoration: const BoxDecoration(color: AppColors.brand50, shape: BoxShape.circle),
            child: const Icon(Icons.playlist_add_check, color: AppColors.brand, size: 28),
          ),
          const SizedBox(height: 14),
          const Text('No queues assigned yet', style: AppTextStyles.h4),
          const SizedBox(height: 6),
          const Text(
            'Ask your admin to create a calling queue and add you to it. Pull down to refresh.',
            textAlign: TextAlign.center,
            style: AppTextStyles.caption,
          ),
        ]),
      );
}

class _HowItWorks extends StatelessWidget {
  const _HowItWorks();

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.surface2,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppColors.line),
        ),
        child: const Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(Icons.info_outline, size: 16, color: AppColors.text2),
            SizedBox(width: 6),
            Text('HOW IT WORKS', style: AppTextStyles.label),
          ]),
          SizedBox(height: 12),
          _Tip(Icons.lock_outline, 'Each lead is locked to you while you call it'),
          _Tip(Icons.block, 'A dialled lead never comes back as a new lead'),
          _Tip(Icons.schedule, 'Skipped leads return to the pool after a short hold'),
          _Tip(Icons.refresh, 'Pull down to refresh the counts'),
        ]),
      );
}

class _Tip extends StatelessWidget {
  final IconData icon;
  final String text;
  const _Tip(this.icon, this.text);

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Row(children: [
          Container(
            width: 26,
            height: 26,
            decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.line)),
            child: Icon(icon, size: 14, color: AppColors.brand),
          ),
          const SizedBox(width: 10),
          Expanded(child: Text(text, style: AppTextStyles.caption.copyWith(color: AppColors.text))),
        ]),
      );
}
