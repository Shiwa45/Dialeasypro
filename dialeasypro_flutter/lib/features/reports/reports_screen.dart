import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/colors.dart';
import '../../core/widgets/widgets.dart';
import '../../data/services/services.dart';

final _reportsProvider = FutureProvider.autoDispose<Map<String, dynamic>>((_) async {
  final results = await Future.wait([
    ReportsService.instance.dailyActivity(),
    ReportsService.instance.conversionFunnel(),
    ReportsService.instance.callAnalytics(),
  ]);
  return {'daily': results[0], 'funnel': results[1], 'calls': results[2]};
});

class ReportsScreen extends ConsumerWidget {
  const ReportsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_reportsProvider);
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('Reports')),
      body: BrutalRefreshIndicator(
        onRefresh: () async => ref.invalidate(_reportsProvider),
        child: async.when(
          loading: () => ListView(padding: const EdgeInsets.all(16), children: List.generate(4, (_) =>
            const Padding(padding: EdgeInsets.only(bottom: 12), child: ShimmerCard(height: 120)),
          )),
          error: (e, _) => EmptyStateView(icon: Icons.error_outline, title: 'Failed', message: e.toString()),
          data: (data) {
            final daily = data['daily'] as Map<String, dynamic>? ?? {};
            final funnel = data['funnel'] as Map<String, dynamic>? ?? {};
            final calls = data['calls'] as Map<String, dynamic>? ?? {};
            final funnelList = (funnel['funnel'] as List?) ?? [];
            final callTrend = (calls['daily_trend'] as List?) ?? [];
            final summary = calls['summary'] as Map<String, dynamic>? ?? {};

            return ListView(padding: const EdgeInsets.all(16), children: [
              // Today's activity
              BrutalCard(padding: const EdgeInsets.all(16), color: AppColors.dark, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Row(children: [
                  Icon(Icons.today, size: 18, color: AppColors.yellow),
                  SizedBox(width: 8),
                  Text("Today's Activity", style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 14, color: AppColors.yellow)),
                ]),
                const SizedBox(height: 14),
                Row(children: [
                  _ReportStat(label: 'New Leads', value: '${(daily['leads'] as Map?)?['new_today'] ?? 0}', dark: true),
                  _ReportStat(label: 'Calls Made', value: '${(daily['calls'] as Map?)?['total'] ?? 0}', dark: true),
                  _ReportStat(label: 'F/U Due', value: '${(daily['followups'] as Map?)?['due_today'] ?? 0}', dark: true),
                ]),
              ])).animate().fadeIn(),

              const SizedBox(height: 12),

              // Funnel
              BrutalCard(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  const Expanded(child: SectionHeader(title: 'Pipeline Funnel', icon: Icons.donut_large)),
                  Text('${funnel['total'] ?? 0} leads', style: AppTextStyles.caption),
                ]),
                const SizedBox(height: 14),
                ...funnelList.map((s) {
                  final stage = s as Map<String, dynamic>;
                  final pct = (stage['pct_of_total'] as num?)?.toDouble() ?? 0;
                  return Padding(padding: const EdgeInsets.only(bottom: 10), child: Row(children: [
                    SizedBox(width: 86, child: Text(stage['label'] as String? ?? '', style: AppTextStyles.body)),
                    Expanded(child: Stack(children: [
                      Container(height: 12, decoration: BoxDecoration(color: AppColors.greyLight, border: Border.all(color: AppColors.black, width: 1.5))),
                      FractionallySizedBox(widthFactor: pct / 100,
                        child: Container(height: 12, decoration: BoxDecoration(color: AppColors.yellow, border: Border.all(color: AppColors.black, width: 1.5)))),
                    ])),
                    const SizedBox(width: 8),
                    SizedBox(width: 28, child: Text('${stage['count']}', style: AppTextStyles.h5, textAlign: TextAlign.right)),
                  ]));
                }),
              ])).animate().fadeIn(delay: 100.ms),

              const SizedBox(height: 12),

              // Call analytics with chart
              BrutalCard(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const SectionHeader(title: 'Call Analytics (30d)', icon: Icons.analytics),
                const SizedBox(height: 14),
                Row(children: [
                  _ReportStat(label: 'Total', value: '${summary['total_calls'] ?? 0}'),
                  _ReportStat(label: 'Connected', value: '${summary['connected_calls'] ?? 0}'),
                  _ReportStat(label: 'Rate', value: '${(summary['connection_rate'] as num?)?.toStringAsFixed(1) ?? 0}%'),
                ]),
                if (callTrend.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  SizedBox(height: 120, child: LineChart(LineChartData(
                    gridData: const FlGridData(show: false),
                    titlesData: const FlTitlesData(show: false),
                    borderData: FlBorderData(show: false),
                    lineBarsData: [
                      LineChartBarData(
                        spots: callTrend.asMap().entries.map((e) {
                          final d = e.value as Map<String, dynamic>;
                          return FlSpot(e.key.toDouble(), (d['total'] as num?)?.toDouble() ?? 0);
                        }).toList(),
                        color: AppColors.yellow, barWidth: 2.5, isCurved: true,
                        dotData: const FlDotData(show: false),
                        belowBarData: BarAreaData(show: true, color: AppColors.yellow.withOpacity(0.15)),
                      ),
                      LineChartBarData(
                        spots: callTrend.asMap().entries.map((e) {
                          final d = e.value as Map<String, dynamic>;
                          return FlSpot(e.key.toDouble(), (d['connected'] as num?)?.toDouble() ?? 0);
                        }).toList(),
                        color: AppColors.success, barWidth: 2, isCurved: true,
                        dotData: const FlDotData(show: false),
                      ),
                    ],
                  ))),
                ],
              ])).animate().fadeIn(delay: 150.ms),

              const SizedBox(height: 80),
            ]);
          },
        ),
      ),
    );
  }
}

class _ReportStat extends StatelessWidget {
  final String label, value;
  final bool dark;
  const _ReportStat({required this.label, required this.value, this.dark = false});

  @override
  Widget build(BuildContext context) => Expanded(child: Column(children: [
    Text(value, style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 22, color: dark ? AppColors.yellow : AppColors.black)),
    Text(label, style: TextStyle(fontFamily: 'DMSans', fontSize: 11, color: dark ? AppColors.muted : AppColors.grey)),
  ]));
}
