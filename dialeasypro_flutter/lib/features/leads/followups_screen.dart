import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../../data/models/models.dart';
import '../../data/services/services.dart';

// ─── Providers ──────────────────────────────────────────────
final _overdueLeadsProvider = FutureProvider.autoDispose<PaginatedResponse<Lead>>(
  (_) => LeadsService.instance.listLeads(overdue: true, pageSize: 50),
);

final _dueTodayLeadsProvider = FutureProvider.autoDispose<PaginatedResponse<Lead>>(
  (_) => LeadsService.instance.listLeads(followupDueToday: true, pageSize: 50),
);

// ─── Screen ─────────────────────────────────────────────────
class FollowupsScreen extends ConsumerStatefulWidget {
  const FollowupsScreen({super.key});

  @override
  ConsumerState<FollowupsScreen> createState() => _FollowupsScreenState();
}

class _FollowupsScreenState extends ConsumerState<FollowupsScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  void _refresh() {
    ref.invalidate(_overdueLeadsProvider);
    ref.invalidate(_dueTodayLeadsProvider);
  }

  @override
  Widget build(BuildContext context) {
    final overdueAsync = ref.watch(_overdueLeadsProvider);
    final dueTodayAsync = ref.watch(_dueTodayLeadsProvider);

    final overdueCount = overdueAsync.value?.count ?? 0;
    final dueTodayCount = dueTodayAsync.value?.count ?? 0;

    return Scaffold(
      backgroundColor: AppColors.background,
      body: NestedScrollView(
        headerSliverBuilder: (context, innerBoxIsScrolled) => [
          SliverAppBar(
            pinned: true,
            backgroundColor: AppColors.white,
            elevation: 0,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back, color: AppColors.black),
              onPressed: () => context.pop(),
            ),
            title: const Text('Follow-ups', style: AppTextStyles.h3),
            actions: [
              IconButton(
                icon: const Icon(Icons.refresh, color: AppColors.black),
                onPressed: _refresh,
                tooltip: 'Refresh',
              ),
            ],
            bottom: PreferredSize(
              preferredSize: const Size.fromHeight(52),
              child: Column(
                children: [
                  const Divider(height: 1, thickness: 2, color: AppColors.black),
                  TabBar(
                    controller: _tabs,
                    labelColor: AppColors.black,
                    unselectedLabelColor: AppColors.grey,
                    labelStyle: const TextStyle(
                      fontFamily: 'SpaceGrotesk',
                      fontWeight: FontWeight.w700,
                      fontSize: 12,
                    ),
                    unselectedLabelStyle: const TextStyle(
                      fontFamily: 'DMSans',
                      fontSize: 12,
                    ),
                    indicatorColor: AppColors.yellow,
                    indicatorWeight: 3,
                    tabs: [
                      Tab(
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(Icons.warning_amber_rounded, size: 16,
                                color: AppColors.error),
                            const SizedBox(width: 5),
                            Text(
                              overdueCount > 0
                                  ? 'Overdue ($overdueCount)'
                                  : 'Overdue',
                            ),
                          ],
                        ),
                      ),
                      Tab(
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(Icons.today, size: 16,
                                color: AppColors.warning),
                            const SizedBox(width: 5),
                            Text(
                              dueTodayCount > 0
                                  ? 'Due Today ($dueTodayCount)'
                                  : 'Due Today',
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
        body: TabBarView(
          controller: _tabs,
          children: [
            // ── Overdue Tab ──────────────────────────────────
            BrutalRefreshIndicator(
              onRefresh: () async => ref.invalidate(_overdueLeadsProvider),
              child: overdueAsync.when(
                loading: () => _LoadingSkeleton(),
                error: (e, _) => _ErrorView(onRetry: _refresh),
                data: (res) => res.results.isEmpty
                    ? const _EmptyFollowups(
                        icon: Icons.check_circle_outline,
                        title: 'No Overdue Follow-ups',
                        subtitle: 'You\'re all caught up! 🎉',
                        color: AppColors.success,
                      )
                    : _FollowupLeadList(leads: res.results),
              ),
            ),

            // ── Due Today Tab ────────────────────────────────
            BrutalRefreshIndicator(
              onRefresh: () async => ref.invalidate(_dueTodayLeadsProvider),
              child: dueTodayAsync.when(
                loading: () => _LoadingSkeleton(),
                error: (e, _) => _ErrorView(onRetry: _refresh),
                data: (res) => res.results.isEmpty
                    ? const _EmptyFollowups(
                        icon: Icons.event_available_outlined,
                        title: 'No Follow-ups Due Today',
                        subtitle: 'Nothing scheduled for today.',
                        color: AppColors.info,
                      )
                    : _FollowupLeadList(leads: res.results),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Lead List ───────────────────────────────────────────────
class _FollowupLeadList extends StatelessWidget {
  final List<Lead> leads;
  const _FollowupLeadList({required this.leads});

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: leads.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (context, i) => _FollowupLeadTile(lead: leads[i])
          .animate()
          .fadeIn(delay: Duration(milliseconds: i * 50))
          .slideX(begin: 0.04, end: 0),
    );
  }
}

// ─── Lead Tile ───────────────────────────────────────────────
class _FollowupLeadTile extends StatelessWidget {
  final Lead lead;
  const _FollowupLeadTile({required this.lead});

  @override
  Widget build(BuildContext context) {
    final statusColor =
        AppColors.leadStatusColors[lead.status]?.border ?? AppColors.grey;
    final isOverdue = lead.followupOverdue;

    return BrutalCard(
      onTap: () => context.push('/leads/${lead.id}'),
      padding: EdgeInsets.zero,
      borderColor: isOverdue ? AppColors.error : AppColors.black,
      child: Row(
        children: [
          // Status stripe
          Container(width: 4, height: 80, color: statusColor),

          // Avatar
          Padding(
            padding: const EdgeInsets.all(10),
            child: BrutalAvatar(name: lead.name, size: 44),
          ),

          // Info
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(lead.name,
                            style: AppTextStyles.h5,
                            overflow: TextOverflow.ellipsis),
                      ),
                      const SizedBox(width: 6),
                      StatusBadge(
                          status: lead.status, label: lead.statusDisplay),
                    ],
                  ),
                  const SizedBox(height: 3),
                  Row(
                    children: [
                      Text(Fmt.displayPhone(lead.phone),
                          style: AppTextStyles.mono),
                      if (lead.city.isNotEmpty)
                        Text(' · ${lead.city}', style: AppTextStyles.caption),
                    ],
                  ),
                  const SizedBox(height: 5),
                  // Follow-up time row
                  if (lead.nextFollowupAt != null)
                    Row(
                      children: [
                        Icon(
                          isOverdue
                              ? Icons.warning_amber_rounded
                              : Icons.access_time,
                          size: 12,
                          color:
                              isOverdue ? AppColors.error : AppColors.warning,
                        ),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Text(
                            isOverdue
                                ? 'Overdue · ${Fmt.relative(lead.nextFollowupAt)}'
                                : 'Due ${Fmt.relative(lead.nextFollowupAt)}',
                            style: TextStyle(
                              fontFamily: 'DMSans',
                              fontSize: 11,
                              color: isOverdue
                                  ? AppColors.error
                                  : AppColors.warning,
                              fontWeight: isOverdue
                                  ? FontWeight.w600
                                  : FontWeight.w400,
                            ),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                ],
              ),
            ),
          ),

          // Chevron
          const Padding(
            padding: EdgeInsets.only(right: 10),
            child: Icon(Icons.chevron_right, size: 18, color: AppColors.grey),
          ),
        ],
      ),
    );
  }
}

// ─── Empty State ─────────────────────────────────────────────
class _EmptyFollowups extends StatelessWidget {
  final IconData icon;
  final String title, subtitle;
  final Color color;
  const _EmptyFollowups({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.1),
              border: Border.all(color: color, width: 2),
            ),
            child: Icon(icon, color: color, size: 48),
          ),
          const SizedBox(height: 16),
          Text(title, style: AppTextStyles.h4),
          const SizedBox(height: 6),
          Text(subtitle,
              style: AppTextStyles.body.copyWith(color: AppColors.muted)),
        ],
      ),
    );
  }
}

// ─── Loading Skeleton ────────────────────────────────────────
class _LoadingSkeleton extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: 6,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (_, __) => const ShimmerCard(height: 80),
    );
  }
}

// ─── Error View ──────────────────────────────────────────────
class _ErrorView extends StatelessWidget {
  final VoidCallback onRetry;
  const _ErrorView({required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, color: AppColors.error, size: 48),
          const SizedBox(height: 12),
          const Text('Failed to load follow-ups', style: AppTextStyles.h5),
          const SizedBox(height: 16),
          BrutalButton.primary(
            label: 'RETRY',
            iconData: Icons.refresh,
            onPressed: onRetry,
          ),
        ],
      ),
    );
  }
}
