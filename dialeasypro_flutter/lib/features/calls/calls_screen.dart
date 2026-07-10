import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../../data/models/addon_models.dart';
import '../../data/models/models.dart';
import '../../data/services/services.dart';
import '../ai/call_insight_sheet.dart';
import '../features_provider.dart';

final _callsListProvider = FutureProvider.autoDispose<PaginatedResponse<CallLog>>((_) => CallsService.instance.listCalls());
final _callStatsHeaderProvider = FutureProvider.autoDispose<Map<String, dynamic>>((_) => CallsService.instance.getStats());

class CallsScreen extends ConsumerWidget {
  const CallsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final callsAsync = ref.watch(_callsListProvider);
    final statsAsync = ref.watch(_callStatsHeaderProvider);
    final showInsights = ref.features.has(Feat.aiInsights);

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('Call Log')),
      body: BrutalRefreshIndicator(
        onRefresh: () async {
          ref.invalidate(_callsListProvider);
          ref.invalidate(_callStatsHeaderProvider);
        },
        child: CustomScrollView(slivers: [
          SliverToBoxAdapter(child: statsAsync.when(
            loading: () => const Padding(padding: EdgeInsets.all(16), child: ShimmerCard(height: 80)),
            error: (_, __) => const SizedBox.shrink(),
            data: (s) {
              final today = s['today'] as Map<String, dynamic>? ?? {};
              final period = s['period'] as Map<String, dynamic>? ?? {};
              return Container(
                padding: const EdgeInsets.all(16),
                decoration: const BoxDecoration(
                  color: AppColors.dark,
                  border: Border(bottom: BorderSide(color: AppColors.black, width: 2)),
                ),
                child: Row(children: [
                  Expanded(child: _CallStat(label: 'TODAY', value: '${today['total'] ?? 0}', sub: '${today['connected'] ?? 0} connected')),
                  Container(width: 2, height: 40, color: AppColors.muted.withOpacity(0.3)),
                  Expanded(child: _CallStat(label: 'RATE', value: '${period['connection_rate'] ?? 0}%', sub: 'connection')),
                  Container(width: 2, height: 40, color: AppColors.muted.withOpacity(0.3)),
                  Expanded(child: _CallStat(label: 'AVG', value: Fmt.duration((period['avg_duration_seconds'] as int?) ?? 0), sub: 'duration')),
                ]),
              ).animate().fadeIn();
            },
          )),
          callsAsync.when(
            loading: () => SliverPadding(padding: const EdgeInsets.all(16), sliver: SliverList(delegate: SliverChildBuilderDelegate(
              (_, i) => const Padding(padding: EdgeInsets.only(bottom: 10), child: ShimmerCard(height: 80)),
              childCount: 8,
            ))),
            error: (_, __) => const SliverFillRemaining(child: EmptyStateView(icon: Icons.error_outline, title: 'Failed')),
            data: (res) => res.results.isEmpty
                ? SliverFillRemaining(child: EmptyStateView(
                    icon: Icons.phone_disabled, title: 'No calls yet',
                    message: 'Call a lead and it will appear here',
                    buttonLabel: 'Go to Leads', onAction: () => context.go('/leads'),
                  ))
                : SliverPadding(padding: const EdgeInsets.all(16), sliver: SliverList(delegate: SliverChildBuilderDelegate(
                    (_, i) {
                      final c = res.results[i];
                      return Padding(padding: const EdgeInsets.only(bottom: 10),
                        child: BrutalCard(
                          onTap: c.lead != null ? () => context.push('/leads/${c.lead}') : null,
                          padding: const EdgeInsets.all(14),
                          child: Row(children: [
                            Container(
                              width: 40, height: 40,
                              decoration: BoxDecoration(
                                color: c.isConnected ? AppColors.successBg : AppColors.greyLight,
                                border: Border.all(color: AppColors.black, width: 1.5),
                              ),
                              child: Icon(c.direction == 'outbound' ? Icons.call_made : Icons.call_received,
                                  size: 18, color: c.isConnected ? AppColors.success : AppColors.grey),
                            ),
                            const SizedBox(width: 12),
                            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Row(children: [
                                Expanded(child: Text(c.leadName ?? c.phoneNumber, style: AppTextStyles.h5, overflow: TextOverflow.ellipsis)),
                                const SizedBox(width: 6),
                                if (c.isConnected) const TagChip(label: '✓', backgroundColor: AppColors.success, textColor: AppColors.white)
                                else const TagChip(label: '✕', backgroundColor: AppColors.greyLight),
                              ]),
                              const SizedBox(height: 3),
                              Row(children: [
                                Text(c.durationDisplay, style: AppTextStyles.mono),
                                const SizedBox(width: 8),
                                Text(Fmt.relative(c.startedAt), style: AppTextStyles.caption),
                              ]),
                              if (c.dispositionName != null) Padding(padding: const EdgeInsets.only(top: 4),
                                child: TagChip(label: c.dispositionName!)),
                            ])),
                            // Only offered when the call has audio to analyse.
                            if (showInsights && c.recordingUrl != null)
                              IconButton(
                                tooltip: 'AI insight',
                                icon: const Icon(Icons.auto_awesome, size: 20),
                                onPressed: () => showCallInsightSheet(context, c.id),
                              ),
                          ]),
                        ).animate().fadeIn(delay: Duration(milliseconds: i * 30)),
                      );
                    },
                    childCount: res.results.length,
                  ))),
          ),
        ]),
      ),
    );
  }
}

class _CallStat extends StatelessWidget {
  final String label, value, sub;
  const _CallStat({required this.label, required this.value, required this.sub});

  @override
  Widget build(BuildContext context) => Column(mainAxisSize: MainAxisSize.min, children: [
    Text(label, style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10, color: AppColors.muted, letterSpacing: 0.5)),
    const SizedBox(height: 4),
    Text(value, style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 20, color: AppColors.yellow)),
    Text(sub, style: const TextStyle(fontFamily: 'DMSans', fontSize: 10, color: AppColors.muted)),
  ]);
}
