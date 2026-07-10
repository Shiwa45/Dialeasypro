import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/colors.dart';
import '../../core/widgets/widgets.dart';
import '../../data/services/services.dart';
import 'dialer_state.dart';

// ============================================================
// DialEasypro — Queue Starter Screen
// Shows the admin-defined calling queues this agent is assigned to.
// Each queue pulls leads one at a time from the server — no lead is ever
// served to two agents or repeated (enforced server-side via locking,
// worked-state, and redial cooldown).
// ============================================================

final _availableQueuesProvider = FutureProvider.autoDispose<List<Map<String, dynamic>>>((_) {
  return QueueService.instance.available();
});

class QueueStarterScreen extends ConsumerWidget {
  const QueueStarterScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_availableQueuesProvider);

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Auto-Dialer Queues'),
        leading: IconButton(icon: const Icon(Icons.arrow_back, color: AppColors.black), onPressed: () => context.pop()),
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(_availableQueuesProvider),
        child: async.when(
          loading: () => ListView(padding: const EdgeInsets.all(16), children: List.generate(3, (_) =>
            const Padding(padding: EdgeInsets.only(bottom: 12), child: ShimmerCard(height: 90)))),
          error: (e, _) => EmptyStateView(
            icon: Icons.error_outline, title: 'Could not load queues', message: e.toString()),
          data: (queues) => ListView(
            padding: const EdgeInsets.all(16),
            children: [
              BrutalCard(
                padding: const EdgeInsets.all(18),
                color: AppColors.dark,
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: const [
                  Row(children: [
                    Icon(Icons.flash_on, color: AppColors.yellow, size: 22),
                    SizedBox(width: 8),
                    Text('Power Dialer', style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 16, color: AppColors.yellow)),
                  ]),
                  SizedBox(height: 6),
                  Text(
                    'Pick a queue assigned to you. Leads are dialed one after another — each call needs a disposition before the next. No lead repeats.',
                    style: TextStyle(fontFamily: 'DMSans', fontSize: 12, color: AppColors.muted, height: 1.5),
                  ),
                ]),
              ).animate().fadeIn(),

              const SizedBox(height: 20),
              const Text('YOUR QUEUES', style: AppTextStyles.label),
              const SizedBox(height: 10),

              if (queues.isEmpty)
                BrutalCard(
                  padding: const EdgeInsets.all(20),
                  child: Column(children: const [
                    Icon(Icons.inbox, size: 36, color: AppColors.grey),
                    SizedBox(height: 10),
                    Text('No queues assigned', style: AppTextStyles.h5),
                    SizedBox(height: 6),
                    Text(
                      'Ask your admin to create a calling queue and add you to it.',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontFamily: 'DMSans', fontSize: 12, color: AppColors.grey),
                    ),
                  ]),
                ).animate().fadeIn()
              else
                ...queues.asMap().entries.map((entry) {
                  final i = entry.key;
                  final q = entry.value;
                  final count = (q['pending_count'] as num?)?.toInt() ?? 0;
                  final isAuto = q['mode'] == 'auto';
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: _QueueCard(
                      title: q['name'] as String? ?? 'Queue',
                      subtitle: (q['description'] as String?)?.isNotEmpty == true
                          ? q['description'] as String
                          : '$count lead${count == 1 ? '' : 's'} ready to call',
                      count: count,
                      isAuto: isAuto,
                      onTap: count == 0
                          ? null
                          : () => _startQueue(context, ref, q['id'] as int),
                    ).animate().fadeIn(delay: (80 + i * 50).ms).slideX(begin: 0.05, end: 0),
                  );
                }),

              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: AppColors.yellow.withOpacity(0.4),
                  border: Border.all(color: AppColors.warning, width: 1.5),
                ),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: const [
                  Row(children: [
                    Icon(Icons.lightbulb_outline, size: 16, color: AppColors.warning),
                    SizedBox(width: 6),
                    Text('HOW IT WORKS', style: AppTextStyles.label),
                  ]),
                  SizedBox(height: 8),
                  _Tip('Each lead is locked to you while you call it'),
                  _Tip('A dialed lead never comes back as a new lead'),
                  _Tip('Skipped leads return to the pool after a short hold'),
                  _Tip('Pull counts refresh when you pull down'),
                ]),
              ).animate().fadeIn(delay: 300.ms),
              const SizedBox(height: 40),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _startQueue(BuildContext context, WidgetRef ref, int queueId) async {
    ref.read(dialerProvider.notifier).startServerQueue(queueId);
    context.push('/dialer');
  }
}

class _QueueCard extends StatelessWidget {
  final String title, subtitle;
  final int count;
  final bool isAuto;
  final VoidCallback? onTap;
  const _QueueCard({required this.title, required this.subtitle, required this.count, required this.isAuto, this.onTap});

  @override
  Widget build(BuildContext context) {
    final disabled = onTap == null;
    return BrutalCard(
      onTap: onTap,
      padding: const EdgeInsets.all(14),
      child: Opacity(
        opacity: disabled ? 0.55 : 1,
        child: Row(children: [
          Container(
            width: 48, height: 48,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: count > 0 ? AppColors.yellow : AppColors.greyLight,
              border: Border.all(color: AppColors.black, width: 2),
            ),
            child: Text('$count', style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w900, fontSize: 16)),
          ),
          const SizedBox(width: 12),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Flexible(child: Text(title, style: AppTextStyles.h5, overflow: TextOverflow.ellipsis)),
              if (isAuto) ...[
                const SizedBox(width: 6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                  decoration: BoxDecoration(color: AppColors.warning.withOpacity(0.2), border: Border.all(color: AppColors.warning, width: 1)),
                  child: const Text('AUTO', style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 9, color: AppColors.warning)),
                ),
              ],
            ]),
            const SizedBox(height: 2),
            Text(subtitle, style: AppTextStyles.caption),
          ])),
          Icon(Icons.play_circle_fill, color: count > 0 ? AppColors.dark : AppColors.grey, size: 26),
        ]),
      ),
    );
  }
}

class _Tip extends StatelessWidget {
  final String text;
  const _Tip(this.text);

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 2),
    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('▸ ', style: TextStyle(fontWeight: FontWeight.w700, color: AppColors.warning)),
      Expanded(child: Text(text, style: const TextStyle(fontFamily: 'DMSans', fontSize: 12, color: AppColors.dark, height: 1.4))),
    ]),
  );
}
