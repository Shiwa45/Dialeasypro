import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../../data/models/models.dart';
import '../../data/services/services.dart';
import '../dialer/dialer_state.dart';

// ─── Filter state ───────────────────────────────────────────
class LeadsFilter {
  final String search, status, priority, source;
  final bool overdue;
  final int page;

  const LeadsFilter({
    this.search = '', this.status = '', this.priority = '', this.source = '',
    this.overdue = false, this.page = 1,
  });

  LeadsFilter copyWith({String? search, String? status, String? priority, String? source, bool? overdue, int? page}) =>
      LeadsFilter(
        search: search ?? this.search, status: status ?? this.status,
        priority: priority ?? this.priority, source: source ?? this.source,
        overdue: overdue ?? this.overdue, page: page ?? this.page,
      );

  bool get hasActive => search.isNotEmpty || status.isNotEmpty || priority.isNotEmpty || source.isNotEmpty || overdue;
}

final leadsFilterProvider = StateProvider.autoDispose((_) => const LeadsFilter());
final leadsListProvider = FutureProvider.autoDispose.family<PaginatedResponse<Lead>, LeadsFilter>(
  (ref, f) => LeadsService.instance.listLeads(
    page: f.page,
    search: f.search.isEmpty ? null : f.search,
    status: f.status.isEmpty ? null : f.status,
    priority: f.priority.isEmpty ? null : f.priority,
    source: f.source.isEmpty ? null : f.source,
    overdue: f.overdue ? true : null,
  ),
);

class LeadsListScreen extends ConsumerStatefulWidget {
  final bool selectMode;
  const LeadsListScreen({super.key, this.selectMode = false});

  @override
  ConsumerState<LeadsListScreen> createState() => _LeadsListScreenState();
}

class _LeadsListScreenState extends ConsumerState<LeadsListScreen> {
  final _searchCtrl = TextEditingController();
  bool _showSearch = false;
  bool _selectMode = false;
  final Set<int> _selectedIds = {};
  final Map<int, Lead> _selectedLeads = {};

  @override
  void initState() {
    super.initState();
    _selectMode = widget.selectMode;
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  void _toggleSelect(Lead lead) {
    setState(() {
      if (_selectedIds.contains(lead.id)) {
        _selectedIds.remove(lead.id);
        _selectedLeads.remove(lead.id);
      } else {
        _selectedIds.add(lead.id);
        _selectedLeads[lead.id] = lead;
      }
    });
  }

  void _startQueueDialer() {
    if (_selectedLeads.isEmpty) {
      AppToast.show(context, 'Select at least one lead', isError: true);
      return;
    }
    final leads = _selectedLeads.values.toList();
    ref.read(dialerProvider.notifier).startQueue(leads);
    context.push('/dialer');
  }

  @override
  Widget build(BuildContext context) {
    final filter = ref.watch(leadsFilterProvider);
    final leadsAsync = ref.watch(leadsListProvider(filter));

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        leading: _selectMode
            ? IconButton(
                icon: const Icon(Icons.close, color: AppColors.black),
                onPressed: () => setState(() {
                  _selectMode = false;
                  _selectedIds.clear();
                  _selectedLeads.clear();
                }),
              )
            : null,
        title: _showSearch
            ? TextField(
                controller: _searchCtrl,
                autofocus: true,
                style: const TextStyle(fontFamily: 'DMSans', fontSize: 14),
                decoration: const InputDecoration(
                  hintText: 'Search name, phone…', border: InputBorder.none,
                  hintStyle: TextStyle(color: AppColors.grey),
                ),
                onChanged: (v) => ref.read(leadsFilterProvider.notifier).update((s) => s.copyWith(search: v, page: 1)),
              )
            : _selectMode
                ? Text('${_selectedIds.length} selected', style: AppTextStyles.h3)
                : const Text('Leads'),
        actions: [
          if (!_selectMode) ...[
            IconButton(
              icon: Icon(_showSearch ? Icons.close : Icons.search, color: AppColors.black),
              onPressed: () {
                setState(() => _showSearch = !_showSearch);
                if (!_showSearch) {
                  _searchCtrl.clear();
                  ref.read(leadsFilterProvider.notifier).update((s) => s.copyWith(search: '', page: 1));
                }
              },
            ),
            IconButton(
              icon: Stack(children: [
                const Icon(Icons.filter_list, color: AppColors.black),
                if (filter.hasActive) Positioned(right: 0, top: 0, child: Container(
                  width: 8, height: 8,
                  decoration: BoxDecoration(color: AppColors.error, border: Border.all(color: AppColors.white), shape: BoxShape.circle),
                )),
              ]),
              onPressed: () => _showFilters(filter),
            ),
            IconButton(
              icon: const Icon(Icons.checklist, color: AppColors.black),
              tooltip: 'Select for Auto-Dialer',
              onPressed: () => setState(() => _selectMode = true),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
              child: BrutalButton.primary(
                label: '+ Lead',
                isFullWidth: false,
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                onPressed: () => context.push('/leads/new'),
              ),
            ),
          ] else
            TextButton(
              onPressed: () {
                leadsAsync.whenData((res) {
                  setState(() {
                    for (final l in res.results) {
                      _selectedIds.add(l.id);
                      _selectedLeads[l.id] = l;
                    }
                  });
                });
              },
              child: const Text('Select all on page',
                  style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 11)),
            ),
        ],
      ),
      body: Column(children: [
        if (filter.hasActive && !_selectMode) _ActiveFiltersBar(filter: filter),
        Expanded(child: leadsAsync.when(
          loading: () => ListView.builder(
            padding: const EdgeInsets.all(16), itemCount: 8,
            itemBuilder: (_, i) => Padding(padding: const EdgeInsets.only(bottom: 10), child: const ShimmerCard(height: 90)),
          ),
          error: (e, _) => EmptyStateView(
            icon: Icons.error_outline, title: 'Failed to load',
            message: ApiErrors.message(e), buttonLabel: 'Retry',
            onAction: () => ref.invalidate(leadsListProvider(filter)),
          ),
          data: (res) => res.results.isEmpty
              ? EmptyStateView(
                  icon: Icons.people_outline,
                  title: filter.hasActive ? 'No matches' : 'No leads yet',
                  message: filter.hasActive ? 'Try clearing filters' : 'Add your first lead to start',
                  buttonLabel: filter.hasActive ? 'Clear Filters' : '+ New Lead',
                  onAction: filter.hasActive
                      ? () => ref.read(leadsFilterProvider.notifier).state = const LeadsFilter()
                      : () => context.push('/leads/new'),
                )
              : BrutalRefreshIndicator(
                  onRefresh: () async => ref.invalidate(leadsListProvider(filter)),
                  child: ListView.builder(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 100),
                    itemCount: res.results.length + (res.totalPages > 1 ? 1 : 0),
                    itemBuilder: (_, i) {
                      if (i == res.results.length) {
                        return _Pagination(
                          page: filter.page, totalPages: res.totalPages,
                          onChange: (p) => ref.read(leadsFilterProvider.notifier).update((s) => s.copyWith(page: p)),
                        );
                      }
                      final lead = res.results[i];
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 10),
                        child: _LeadTile(
                          lead: lead,
                          selectMode: _selectMode,
                          selected: _selectedIds.contains(lead.id),
                          onSelect: () => _toggleSelect(lead),
                        ).animate().fadeIn(delay: Duration(milliseconds: i * 40)).slideX(begin: 0.03, end: 0),
                      );
                    },
                  ),
                ),
        )),
      ]),

      // Bottom dialer action bar when in select mode
      bottomNavigationBar: _selectMode
          ? Container(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
              decoration: const BoxDecoration(
                color: AppColors.dark,
                border: Border(top: BorderSide(color: AppColors.black, width: 2)),
              ),
              child: SafeArea(
                child: Row(children: [
                  Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
                    Text('${_selectedIds.length} leads',
                        style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 16, color: AppColors.yellow)),
                    const Text('selected for queue',
                        style: TextStyle(fontFamily: 'DMSans', fontSize: 11, color: AppColors.muted)),
                  ])),
                  BrutalButton(
                    label: 'START DIALING →',
                    iconData: Icons.flash_on,
                    backgroundColor: AppColors.yellow,
                    textColor: AppColors.black,
                    onPressed: _selectedIds.isEmpty ? null : _startQueueDialer,
                  ),
                ]),
              ),
            )
          : null,
    );
  }

  void _showFilters(LeadsFilter current) {
    showBrutalBottomSheet(
      context: context,
      builder: (ctx) => _FilterSheet(
        current: current,
        onApply: (f) {
          ref.read(leadsFilterProvider.notifier).state = f;
          Navigator.pop(ctx);
        },
      ),
    );
  }
}

// ─── Lead Tile ──────────────────────────────────────────────
class _LeadTile extends StatelessWidget {
  final Lead lead;
  final bool selectMode;
  final bool selected;
  final VoidCallback onSelect;

  const _LeadTile({required this.lead, this.selectMode = false, this.selected = false, required this.onSelect});

  @override
  Widget build(BuildContext context) {
    final statusColor = AppColors.leadStatusColors[lead.status]?.border ?? AppColors.grey;
    return BrutalCard(
      onTap: selectMode ? onSelect : () => context.push('/leads/${lead.id}'),
      padding: EdgeInsets.zero,
      color: selected ? AppColors.yellow.withOpacity(0.4) : AppColors.white,
      shadowOffset: selected ? 2 : 4,
      child: Row(children: [
        if (selectMode) Container(
          width: 40, height: 92,
          decoration: BoxDecoration(
            color: selected ? AppColors.yellow : AppColors.white,
            border: const Border(right: BorderSide(color: AppColors.black, width: 1.5)),
          ),
          child: Center(
            child: Container(
              width: 22, height: 22,
              decoration: BoxDecoration(
                color: selected ? AppColors.black : AppColors.white,
                border: Border.all(color: AppColors.black, width: 1.5),
              ),
              child: selected ? const Icon(Icons.check, color: AppColors.white, size: 14) : null,
            ),
          ),
        ) else Container(width: 4, height: 92, color: statusColor),

        // Avatar
        Container(
          width: 50, height: 92,
          decoration: const BoxDecoration(border: Border(right: BorderSide(color: AppColors.black, width: 1.5))),
          child: Center(child: BrutalAvatar(name: lead.name, size: 38)),
        ),
        Expanded(child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
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
              if (lead.isDnd) ...[
                const SizedBox(width: 6),
                const TagChip(label: 'DND', backgroundColor: AppColors.error, textColor: AppColors.white),
              ],
              const Spacer(),
              ScoreBar(score: lead.score),
            ]),
            if (lead.nextFollowupAt != null) Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Row(children: [
                Icon(
                  lead.followupOverdue ? Icons.warning_amber_rounded : Icons.access_time,
                  size: 11,
                  color: lead.followupOverdue ? AppColors.error : AppColors.grey,
                ),
                const SizedBox(width: 3),
                Text(
                  Fmt.relative(lead.nextFollowupAt),
                  style: TextStyle(
                    fontFamily: 'DMSans', fontSize: 10,
                    color: lead.followupOverdue ? AppColors.error : AppColors.grey,
                    fontWeight: lead.followupOverdue ? FontWeight.w600 : FontWeight.w400,
                  ),
                ),
              ]),
            ),
          ]),
        )),
        if (!selectMode) const Padding(
          padding: EdgeInsets.only(right: 10),
          child: Icon(Icons.chevron_right, size: 16, color: AppColors.grey),
        ),
      ]),
    );
  }
}

// ─── Filter Sheet ───────────────────────────────────────────
class _FilterSheet extends StatefulWidget {
  final LeadsFilter current;
  final ValueChanged<LeadsFilter> onApply;
  const _FilterSheet({required this.current, required this.onApply});

  @override
  State<_FilterSheet> createState() => _FilterSheetState();
}

class _FilterSheetState extends State<_FilterSheet> {
  late LeadsFilter _f;

  @override
  void initState() {
    super.initState();
    _f = widget.current;
  }

  Widget _option(String label, String value, String current, ValueChanged<String> onTap) {
    final sel = current == value;
    return GestureDetector(
      onTap: () => setState(() => onTap(sel ? '' : value)),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
        decoration: BoxDecoration(
          color: sel ? AppColors.black : AppColors.white,
          border: Border.all(color: AppColors.black, width: sel ? 2 : 1.5),
          boxShadow: sel ? const [BoxShadow(color: AppColors.black, offset: Offset(2, 2))] : null,
        ),
        child: Text(label, style: TextStyle(
          fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 11,
          color: sel ? AppColors.white : AppColors.black,
        )),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          const Expanded(child: Text('Filter Leads', style: AppTextStyles.h2)),
          TextButton(
            onPressed: () => setState(() => _f = const LeadsFilter()),
            child: const Text('Clear All', style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 12, color: AppColors.error)),
          ),
        ]),
        const SizedBox(height: 16),
        const Text('STATUS', style: AppTextStyles.label),
        const SizedBox(height: 8),
        Wrap(spacing: 6, runSpacing: 6, children: Fmt.leadStatusLabels.entries.map((e) =>
          _option(e.value, e.key, _f.status, (v) => _f = _f.copyWith(status: v))
        ).toList()),
        const SizedBox(height: 16),
        const Text('PRIORITY', style: AppTextStyles.label),
        const SizedBox(height: 8),
        Wrap(spacing: 6, children: [
          _option('🔥 Hot', 'hot', _f.priority, (v) => _f = _f.copyWith(priority: v)),
          _option('High', 'high', _f.priority, (v) => _f = _f.copyWith(priority: v)),
          _option('Medium', 'medium', _f.priority, (v) => _f = _f.copyWith(priority: v)),
          _option('Low', 'low', _f.priority, (v) => _f = _f.copyWith(priority: v)),
        ]),
        const SizedBox(height: 16),
        GestureDetector(
          onTap: () => setState(() => _f = _f.copyWith(overdue: !_f.overdue)),
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 14),
            decoration: BoxDecoration(
              color: _f.overdue ? AppColors.errorBg : AppColors.white,
              border: Border.all(color: AppColors.black, width: 2),
              boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(3, 3))],
            ),
            child: Row(children: [
              Icon(Icons.warning_amber_rounded, size: 18, color: _f.overdue ? AppColors.error : AppColors.grey),
              const SizedBox(width: 10),
              Text('Overdue Follow-ups Only',
                  style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 13, color: AppColors.black)),
              const Spacer(),
              if (_f.overdue) const Icon(Icons.check_box, color: AppColors.error) else const Icon(Icons.check_box_outline_blank, color: AppColors.grey),
            ]),
          ),
        ),
        const SizedBox(height: 24),
        BrutalButton.primary(label: 'APPLY FILTERS →', onPressed: () => widget.onApply(_f)),
      ]),
    );
  }
}

// ─── Active Filters Bar ─────────────────────────────────────
class _ActiveFiltersBar extends ConsumerWidget {
  final LeadsFilter filter;
  const _ActiveFiltersBar({required this.filter});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: const BoxDecoration(
        color: AppColors.yellow,
        border: Border(bottom: BorderSide(color: AppColors.black, width: 2)),
      ),
      child: Row(children: [
        const Text('FILTERS:', style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 0.5)),
        const SizedBox(width: 8),
        Expanded(child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(children: [
            if (filter.status.isNotEmpty) TagChip(
              label: Fmt.leadStatusLabels[filter.status] ?? filter.status,
              backgroundColor: AppColors.black, textColor: AppColors.white,
            ),
            if (filter.priority.isNotEmpty) Padding(
              padding: const EdgeInsets.only(left: 6),
              child: TagChip(label: filter.priority, backgroundColor: AppColors.black, textColor: AppColors.white),
            ),
            if (filter.overdue) const Padding(
              padding: EdgeInsets.only(left: 6),
              child: TagChip(label: 'OVERDUE', backgroundColor: AppColors.error, textColor: AppColors.white),
            ),
          ]),
        )),
        GestureDetector(
          onTap: () => ref.read(leadsFilterProvider.notifier).state = const LeadsFilter(),
          child: const Text('Clear ✕', style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 11)),
        ),
      ]),
    );
  }
}

// ─── Pagination ─────────────────────────────────────────────
class _Pagination extends StatelessWidget {
  final int page, totalPages;
  final ValueChanged<int> onChange;
  const _Pagination({required this.page, required this.totalPages, required this.onChange});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        BrutalButton.secondary(label: '← Prev', onPressed: page > 1 ? () => onChange(page - 1) : null,
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8)),
        Padding(padding: const EdgeInsets.symmetric(horizontal: 14),
            child: Text('$page / $totalPages', style: AppTextStyles.h5)),
        BrutalButton.secondary(label: 'Next →', onPressed: page < totalPages ? () => onChange(page + 1) : null,
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8)),
      ]),
    );
  }
}

class ApiErrors {
  static String message(Object e) => e.toString().contains('Connection') ? 'Cannot connect to server.' : 'Something went wrong.';
}
