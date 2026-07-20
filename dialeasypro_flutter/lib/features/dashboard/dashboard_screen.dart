import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../../data/models/models.dart';
import '../../data/services/services.dart';
import '../auth/auth_provider.dart';

final _statsProvider = FutureProvider.autoDispose<LeadStats>((_) => LeadsService.instance.getStats());
final _callStatsProvider = FutureProvider.autoDispose<Map<String, dynamic>>((_) => CallsService.instance.getStats());
final _recentLeadsProvider = FutureProvider.autoDispose<PaginatedResponse<Lead>>(
  (_) => LeadsService.instance.listLeads(pageSize: 5),
);

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final agent = ref.watch(currentAgentProvider);
    final statsAsync = ref.watch(_statsProvider);
    final callsAsync = ref.watch(_callStatsProvider);
    final leadsAsync = ref.watch(_recentLeadsProvider);

    return Scaffold(
      backgroundColor: AppColors.background,
      body: BrutalRefreshIndicator(
        onRefresh: () async {
          ref.invalidate(_statsProvider);
          ref.invalidate(_callStatsProvider);
          ref.invalidate(_recentLeadsProvider);
        },
        child: CustomScrollView(
          slivers: [
            // ─── Top bar ─────────────────────────────────────────
            SliverAppBar(
              pinned: true,
              backgroundColor: AppColors.white,
              elevation: 0,
              titleSpacing: 16,
              title: Row(children: [
                Container(
                  width: 36, height: 36,
                  decoration: BoxDecoration(
                    color: AppColors.yellow,
                    border: Border.all(color: AppColors.black, width: 2),
                  ),
                  child: const Center(child: Text('D', style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 18))),
                ),
                const SizedBox(width: 10),
                const Text('DialEasypro', style: AppTextStyles.h3),
              ]),
              actions: [
                IconButton(
                  icon: const Icon(Icons.notifications_outlined, color: AppColors.black),
                  onPressed: () {},
                ),
                Padding(
                  padding: const EdgeInsets.only(right: 12, top: 8, bottom: 8),
                  child: GestureDetector(
                    onTap: () => context.go('/profile'),
                    child: BrutalAvatar(name: agent?.name ?? 'A', size: 36),
                  ),
                ),
              ],
              bottom: const PreferredSize(
                preferredSize: Size.fromHeight(2),
                child: Divider(height: 2, thickness: 2, color: AppColors.black),
              ),
            ),

            // ─── Content ──────────────────────────────────────────
            SliverPadding(
              padding: const EdgeInsets.all(16),
              sliver: SliverList(delegate: SliverChildListDelegate([

                // Greeting
                _Greeting(agent: agent).animate().fadeIn(duration: 250.ms),
                const SizedBox(height: 16),

                // BIG Auto-Dialer CTA
                _AutoDialerCTA().animate().slideY(begin: 0.1, end: 0, duration: 350.ms, delay: 80.ms).fadeIn(delay: 80.ms),
                const SizedBox(height: 16),

                // KPI Cards (colorful)
                statsAsync.when(
                  loading: () => GridView.count(
                    crossAxisCount: 2, shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    crossAxisSpacing: 10, mainAxisSpacing: 10, childAspectRatio: 1.4,
                    children: List.generate(4, (_) => const ShimmerCard(height: 80)),
                  ),
                  error: (_, __) => const SizedBox.shrink(),
                  data: (stats) => Column(children: [
                    Row(children: [
                      Expanded(child: CompactKpi(
                        label: 'New Today', value: '${stats.newLeadsToday}',
                        color: AppColors.info, icon: Icons.fiber_new,
                      )),
                      const SizedBox(width: 10),
                      Expanded(child: CompactKpi(
                        label: 'Follow-ups',
                        value: '${stats.followupsDue}',
                        color: AppColors.warning, icon: Icons.alarm,
                      )),
                    ]),
                    const SizedBox(height: 10),
                    Row(children: [
                      Expanded(child: CompactKpi(
                        label: 'Active Leads', value: '${stats.activeLeads}',
                        color: AppColors.purple, icon: Icons.trending_up,
                      )),
                      const SizedBox(width: 10),
                      Expanded(child: CompactKpi(
                        label: 'Conversion', value: '${stats.conversionRate.toStringAsFixed(1)}%',
                        color: AppColors.success, icon: Icons.emoji_events,
                      )),
                    ]),
                  ]).animate().fadeIn(delay: 200.ms),
                ),

                const SizedBox(height: 20),

                // Quick actions
                _QuickActionsBar(context: context).animate().fadeIn(delay: 280.ms),
                const SizedBox(height: 20),

                // Today's call stats card
                callsAsync.when(
                  loading: () => const ShimmerCard(height: 100),
                  error: (_, __) => const SizedBox.shrink(),
                  data: (s) => _TodayCallsCard(stats: s).animate().fadeIn(delay: 350.ms),
                ),

                const SizedBox(height: 14),

                // Today's tasks — overdue follow-ups
                statsAsync.when(
                  loading: () => const SizedBox.shrink(),
                  error: (_, __) => const SizedBox.shrink(),
                  data: (stats) {
                    if (stats.overdueFollowups == 0 && stats.followupsDue == 0) {
                      return const SizedBox.shrink();
                    }
                    return _TasksCard(stats: stats).animate().fadeIn(delay: 380.ms);
                  },
                ),

                const SizedBox(height: 20),

                // Pipeline mini-chart
                statsAsync.when(
                  loading: () => const ShimmerCard(height: 160),
                  error: (_, __) => const SizedBox.shrink(),
                  data: (stats) => _PipelineCard(stats: stats).animate().fadeIn(delay: 420.ms),
                ),

                const SizedBox(height: 20),

                // Recent leads
                SectionHeader(
                  title: 'Recent Leads',
                  icon: Icons.history,
                  action: TextButton(
                    onPressed: () => context.go('/leads'),
                    child: const Text('All →', style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 12, color: AppColors.black)),
                  ),
                ),
                const SizedBox(height: 10),
                leadsAsync.when(
                  loading: () => Column(children: List.generate(3, (_) =>
                    const Padding(padding: EdgeInsets.only(bottom: 10), child: ShimmerCard(height: 80)),
                  )),
                  error: (_, __) => const SizedBox.shrink(),
                  data: (res) => res.results.isEmpty
                      ? const EmptyStateView(icon: Icons.people_outline, title: 'No leads yet')
                      : Column(children: res.results.asMap().entries.map((e) => Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: _RecentLeadTile(lead: e.value)
                              .animate().fadeIn(delay: Duration(milliseconds: 500 + e.key * 60))
                              .slideX(begin: 0.04, end: 0),
                        )).toList()),
                ),
                const SizedBox(height: 80),
              ])),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Greeting ───────────────────────────────────────────────
class _Greeting extends StatelessWidget {
  final Agent? agent;
  const _Greeting({this.agent});

  @override
  Widget build(BuildContext context) {
    final hour = DateTime.now().hour;
    final greet = hour < 12 ? 'Good Morning' : hour < 17 ? 'Good Afternoon' : 'Good Evening';
    final emoji = hour < 12 ? '☀️' : hour < 17 ? '🌤️' : '🌙';
    return BrutalCard(
      padding: const EdgeInsets.all(16),
      color: AppColors.dark,
      child: Row(children: [
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('$greet, ${agent?.name.split(' ').first ?? 'Agent'}! $emoji',
              style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 18, color: AppColors.yellow)),
          const SizedBox(height: 3),
          Text(Fmt.date(DateTime.now().toIso8601String()),
              style: const TextStyle(fontFamily: 'DMSans', fontSize: 12, color: AppColors.muted)),
        ])),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
          decoration: BoxDecoration(border: Border.all(color: AppColors.yellow, width: 1.5)),
          child: Text((agent?.role ?? 'agent').toUpperCase(),
              style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10, color: AppColors.yellow, letterSpacing: 0.5)),
        ),
      ]),
    );
  }
}

// ─── Auto-Dialer CTA (the big one) ──────────────────────────
class _AutoDialerCTA extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return BrutalCard(
      padding: EdgeInsets.zero,
      color: AppColors.yellow,
      shadowOffset: 6,
      onTap: () => context.push('/dialer/queue'),
      child: Stack(children: [
        Container(
          padding: const EdgeInsets.all(18),
          decoration: const BoxDecoration(gradient: AppColors.yellowGradient),
          child: Row(children: [
            Container(
              width: 56, height: 56,
              decoration: BoxDecoration(
                color: AppColors.black,
                border: Border.all(color: AppColors.black, width: 2),
              ),
              child: const Icon(Icons.flash_on, color: AppColors.yellow, size: 30),
            ),
            const SizedBox(width: 14),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: const [
              Text('Auto-Dialer Queue',
                  style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 16, color: AppColors.black)),
              SizedBox(height: 2),
              Text('Dial leads one-by-one. No tap needed.',
                  style: TextStyle(fontFamily: 'DMSans', fontSize: 12, color: AppColors.dark)),
            ])),
            const Icon(Icons.arrow_forward, color: AppColors.black),
          ]),
        ),
      ]),
    );
  }
}

// ─── Quick Actions Bar ──────────────────────────────────────
class _QuickActionsBar extends StatelessWidget {
  final BuildContext context;
  const _QuickActionsBar({required this.context});

  @override
  Widget build(BuildContext _) {
    return Row(children: [
      Expanded(child: ActionButton(
        icon: Icons.call, label: 'CALL', color: AppColors.success, iconColor: AppColors.white,
        onTap: () => context.go('/leads'),
      )),
      Expanded(child: ActionButton(
        icon: Icons.chat, label: 'WHATSAPP', color: AppColors.tealBg, iconColor: AppColors.teal,
        onTap: () => context.go('/leads'),
      )),
      Expanded(child: ActionButton(
        icon: Icons.person_add, label: 'NEW LEAD', color: AppColors.purpleBg, iconColor: AppColors.purple,
        onTap: () => context.push('/leads/new'),
      )),
      Expanded(child: ActionButton(
        icon: Icons.upload_file, label: 'IMPORT', color: AppColors.infoBg, iconColor: AppColors.info,
        onTap: () => context.push('/leads/import'),
      )),
    ]);
  }
}

// ─── Today's Calls Card ─────────────────────────────────────
class _TodayCallsCard extends StatelessWidget {
  final Map<String, dynamic> stats;
  const _TodayCallsCard({required this.stats});

  @override
  Widget build(BuildContext context) {
    final today = stats['today'] as Map<String, dynamic>? ?? {};
    final period = stats['period'] as Map<String, dynamic>? ?? {};
    return BrutalCard(
      padding: const EdgeInsets.all(16),
      color: AppColors.dark,
      child: Row(children: [
        Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: AppColors.yellow,
            border: Border.all(color: AppColors.black, width: 1.5),
          ),
          child: const Icon(Icons.phone_in_talk, color: AppColors.black, size: 22),
        ),
        const SizedBox(width: 12),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('TODAY\'S CALLS',
              style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10, color: AppColors.muted, letterSpacing: 0.6)),
          const SizedBox(height: 3),
          Text('${today['total'] ?? 0} total · ${today['connected'] ?? 0} connected',
              style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 15, color: AppColors.yellow)),
        ])),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
          decoration: BoxDecoration(
            color: AppColors.yellow,
            border: Border.all(color: AppColors.black, width: 1.5),
          ),
          child: Text('${period['connection_rate'] ?? 0}%',
              style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 13)),
        ),
      ]),
    );
  }
}

// ─── Pipeline Card ──────────────────────────────────────────
class _PipelineCard extends StatelessWidget {
  final LeadStats stats;
  const _PipelineCard({required this.stats});

  @override
  Widget build(BuildContext context) {
    final entries = [
      ('New', stats.byStatus['new'] ?? 0, AppColors.info),
      ('Interested', stats.byStatus['interested'] ?? 0, AppColors.success),
      ('Negotiation', stats.byStatus['negotiation'] ?? 0, AppColors.warning),
      ('Converted', stats.byStatus['converted'] ?? 0, AppColors.teal),
    ];
    final total = entries.fold<int>(0, (s, e) => s + e.$2);
    return BrutalCard(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const SectionHeader(title: 'Pipeline Snapshot', icon: Icons.donut_large),
        const SizedBox(height: 14),
        ...entries.map((e) => Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(children: [
            SizedBox(width: 90, child: Text(e.$1, style: AppTextStyles.body)),
            Expanded(child: Stack(children: [
              Container(height: 12, decoration: BoxDecoration(color: AppColors.greyLight, border: Border.all(color: AppColors.black, width: 1.5))),
              if (total > 0) FractionallySizedBox(
                widthFactor: e.$2 / total,
                child: Container(height: 12, decoration: BoxDecoration(color: e.$3, border: Border.all(color: AppColors.black, width: 1.5))),
              ),
            ])),
            const SizedBox(width: 8),
            SizedBox(width: 28, child: Text('${e.$2}', textAlign: TextAlign.right, style: AppTextStyles.h5)),
          ]),
        )),
      ]),
    );
  }
}

// ─── Recent Lead Tile ───────────────────────────────────────
class _RecentLeadTile extends StatelessWidget {
  final Lead lead;
  const _RecentLeadTile({required this.lead});

  @override
  Widget build(BuildContext context) {
    final statusColor = AppColors.leadStatusColors[lead.status]?.border ?? AppColors.grey;
    return BrutalCard(
      onTap: () => context.push('/leads/${lead.id}'),
      padding: EdgeInsets.zero,
      child: Row(children: [
        Container(width: 4, height: 72, color: statusColor),
        Padding(
          padding: const EdgeInsets.all(10),
          child: BrutalAvatar(name: lead.name, size: 44),
        ),
        Expanded(child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 10),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.center, children: [
            Row(children: [
              Expanded(child: Text(lead.name, style: AppTextStyles.h5, overflow: TextOverflow.ellipsis)),
              const SizedBox(width: 6),
              StatusBadge(status: lead.status, label: lead.statusDisplay),
            ]),
            const SizedBox(height: 3),
            Row(children: [
              Text(Fmt.displayPhone(lead.phone), style: AppTextStyles.mono),
              if (lead.city.isNotEmpty) Text(' · ${lead.city}', style: AppTextStyles.caption),
            ]),
            const SizedBox(height: 5),
            Row(children: [
              TagChip(label: lead.sourceDisplay, backgroundColor: AppColors.greyLight),
              const SizedBox(width: 6),
              PriorityBadge(priority: lead.priority),
              const Spacer(),
              ScoreBar(score: lead.score),
            ]),
          ]),
        )),
        const Padding(
          padding: EdgeInsets.only(right: 10),
          child: Icon(Icons.chevron_right, size: 18, color: AppColors.grey),
        ),
      ]),
    );
  }
}

// ─── Tasks / Follow-ups Card ────────────────────────────────
class _TasksCard extends StatelessWidget {
  final LeadStats stats;
  const _TasksCard({required this.stats});

  @override
  Widget build(BuildContext context) {
    final hasOverdue = stats.overdueFollowups > 0;
    return BrutalCard(
      padding: const EdgeInsets.all(14),
      color: hasOverdue ? AppColors.errorBg : AppColors.warningBg,
      borderColor: hasOverdue ? AppColors.error : AppColors.warning,
      onTap: () => context.push('/followups'),
      child: Row(children: [
        Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: hasOverdue ? AppColors.error : AppColors.warning,
            border: Border.all(color: AppColors.black, width: 1.5),
          ),
          child: Icon(
            hasOverdue ? Icons.warning_amber_rounded : Icons.event_available,
            color: AppColors.white, size: 22,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(
            hasOverdue ? '${stats.overdueFollowups} OVERDUE!' : "TODAY'S TASKS",
            style: const TextStyle(
              fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700,
              fontSize: 11, color: AppColors.black, letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 3),
          Text(
            hasOverdue
              ? 'View & call ${stats.overdueFollowups} overdue lead${stats.overdueFollowups == 1 ? '' : 's'}'
              : '${stats.followupsDue} follow-up${stats.followupsDue == 1 ? '' : 's'} scheduled',
            style: AppTextStyles.bodyMedium,
          ),
        ])),
        const Icon(Icons.chevron_right, color: AppColors.black, size: 20),
      ]),
    );
  }
}
