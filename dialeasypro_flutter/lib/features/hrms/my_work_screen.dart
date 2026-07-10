// ─────────────────────────────────────────────────────────────
// "My Work" — the agent's own HRMS records.
//
// Scope is deliberately narrow: a caller can see their own attendance, apply
// for leave, claim an expense, and read their own earnings and payslips.
// Approvals, payroll runs, and other people's records are manager surfaces —
// they live in the web admin, and the backend rejects them from an agent's
// token regardless of what this app shows.
// ─────────────────────────────────────────────────────────────
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../../data/models/addon_models.dart';
import '../../data/services/addon_services.dart';
import '../features_provider.dart';

// ─── Providers ──────────────────────────────────────────────
final _meProvider = FutureProvider.autoDispose((_) => HrmsService.instance.me());
final _attendanceProvider = FutureProvider.autoDispose((_) => HrmsService.instance.attendance());
final _balancesProvider = FutureProvider.autoDispose((_) => HrmsService.instance.leaveBalances());
final _leaveProvider = FutureProvider.autoDispose((_) => HrmsService.instance.leaveRequests());
final _leaveTypesProvider = FutureProvider.autoDispose((_) => HrmsService.instance.leaveTypes());
final _expensesProvider = FutureProvider.autoDispose((_) => HrmsService.instance.expenses());
final _incentivesProvider = FutureProvider.autoDispose((_) => HrmsService.instance.incentives());
final _payslipsProvider = FutureProvider.autoDispose((_) => HrmsService.instance.payslips());

const _statusColors = {
  'present': AppColors.successBg, 'absent': AppColors.errorBg,
  'half_day': AppColors.warningBg, 'on_leave': AppColors.infoBg,
  'holiday': AppColors.greyLight, 'week_off': AppColors.greyLight,
  'pending': AppColors.warningBg, 'approved': AppColors.successBg,
  'rejected': AppColors.errorBg, 'cancelled': AppColors.greyLight,
  'reimbursed': AppColors.infoBg, 'paid': AppColors.successBg,
  'draft': AppColors.greyLight, 'finalized': AppColors.infoBg,
};

const _expenseCategories = ['travel', 'food', 'accommodation', 'communication', 'other'];

String _pretty(String s) => s.replaceAll('_', ' ').toUpperCase();

Widget _pill(String value) => Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: _statusColors[value] ?? AppColors.greyLight,
        border: Border.all(color: AppColors.black, width: 1.5),
      ),
      child: Text(_pretty(value), style: AppTextStyles.h5.copyWith(fontSize: 9)),
    );

String _month(DateTime d) => Fmt.date(d.toIso8601String()).substring(3);

// ─── Screen ─────────────────────────────────────────────────
class MyWorkScreen extends ConsumerStatefulWidget {
  const MyWorkScreen({super.key});

  @override
  ConsumerState<MyWorkScreen> createState() => _MyWorkScreenState();
}

class _MyWorkScreenState extends ConsumerState<MyWorkScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 4, vsync: this);

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final meAsync = ref.watch(_meProvider);

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('My Work'),
        bottom: TabBar(
          controller: _tabs,
          isScrollable: true,
          tabAlignment: TabAlignment.start,
          tabs: const [
            Tab(text: 'Attendance'),
            Tab(text: 'Leave'),
            Tab(text: 'Expenses'),
            Tab(text: 'Earnings'),
          ],
        ),
      ),
      body: meAsync.when(
        loading: () => const Center(child: CircularProgressIndicator(color: AppColors.black)),
        error: (_, __) => const EmptyStateView(
          icon: Icons.cloud_off,
          title: 'Could not load',
          message: 'Check your connection and pull to refresh.',
        ),
        // An agent can exist without an Employee record — HR hasn't enrolled
        // them yet. Every tab below would 404, so say so once, here.
        data: (me) => me['enrolled'] == false
            ? const EmptyStateView(
                icon: Icons.badge_outlined,
                title: 'Not enrolled yet',
                message: 'Your HR team has not created your employee record. '
                    'Once they do, your attendance and payslips appear here.',
              )
            : TabBarView(
                controller: _tabs,
                children: const [
                  _AttendanceTab(),
                  _LeaveTab(),
                  _ExpensesTab(),
                  _EarningsTab(),
                ],
              ),
      ),
    );
  }
}

// ─── Attendance ─────────────────────────────────────────────
class _AttendanceTab extends ConsumerWidget {
  const _AttendanceTab();

  Future<void> _punch(BuildContext context, WidgetRef ref, {required bool checkIn}) async {
    try {
      checkIn ? await HrmsService.instance.checkIn() : await HrmsService.instance.checkOut();
      ref.invalidate(_attendanceProvider);
      if (context.mounted) {
        AppToast.show(context, checkIn ? 'Checked in' : 'Checked out', isSuccess: true);
      }
    } catch (_) {
      if (context.mounted) AppToast.show(context, 'Could not record attendance', isError: true);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_attendanceProvider);

    return BrutalRefreshIndicator(
      onRefresh: () async => ref.invalidate(_attendanceProvider),
      child: ListView(padding: const EdgeInsets.all(16), children: [
        Row(children: [
          Expanded(child: BrutalButton(
            label: 'Check in',
            iconData: Icons.login,
            onPressed: () => _punch(context, ref, checkIn: true),
          )),
          const SizedBox(width: 10),
          Expanded(child: BrutalButton(
            label: 'Check out',
            iconData: Icons.logout,
            backgroundColor: AppColors.white,
            onPressed: () => _punch(context, ref, checkIn: false),
          )),
        ]),
        const SizedBox(height: 6),
        Text(
          'Your dialler sessions are counted automatically overnight. '
          'Use these only if you work off the dialler.',
          style: AppTextStyles.caption,
        ),
        const SizedBox(height: 16),
        ...async.when(
          loading: () => [const ShimmerCard(height: 70), const ShimmerCard(height: 70)],
          error: (_, __) => [const SizedBox.shrink()],
          data: (res) => res.results.isEmpty
              ? [const Padding(
                  padding: EdgeInsets.only(top: 40),
                  child: EmptyStateView(icon: Icons.event_busy, title: 'No attendance yet'),
                )]
              : res.results.map((a) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: BrutalCard(
                      padding: const EdgeInsets.all(14),
                      child: Row(children: [
                        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(Fmt.date(a.date.toIso8601String()), style: AppTextStyles.h5),
                          const SizedBox(height: 3),
                          Text('${a.workedHours.toStringAsFixed(2)} h worked',
                              style: AppTextStyles.mono),
                        ])),
                        _pill(a.status),
                      ]),
                    ),
                  )).toList(),
        ),
      ]),
    );
  }
}

// ─── Leave ──────────────────────────────────────────────────
class _LeaveTab extends ConsumerWidget {
  const _LeaveTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final balances = ref.watch(_balancesProvider);
    final requests = ref.watch(_leaveProvider);

    return BrutalRefreshIndicator(
      onRefresh: () async {
        ref.invalidate(_balancesProvider);
        ref.invalidate(_leaveProvider);
      },
      child: ListView(padding: const EdgeInsets.all(16), children: [
        BrutalButton(
          label: 'Apply for leave',
          iconData: Icons.add,
          isFullWidth: true,
          onPressed: () => _showApplyLeave(context, ref),
        ),
        const SizedBox(height: 16),

        ...balances.when(
          loading: () => [const ShimmerCard(height: 80)],
          error: (_, __) => [const SizedBox.shrink()],
          data: (list) => list.isEmpty
              ? [const SizedBox.shrink()]
              : [
                  const SectionHeader(title: 'Balance'),
                  const SizedBox(height: 8),
                  GridView.count(
                    crossAxisCount: 2,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    childAspectRatio: 1.7,
                    mainAxisSpacing: 10,
                    crossAxisSpacing: 10,
                    children: list
                        .map((b) => StatCard(
                              label: b.leaveTypeName,
                              value: b.remainingDays,
                              sub: '${b.usedDays} of ${b.allocatedDays} used',
                            ))
                        .toList(),
                  ),
                  const SizedBox(height: 20),
                ],
        ),

        const SectionHeader(title: 'My requests'),
        const SizedBox(height: 8),
        ...requests.when(
          loading: () => [const ShimmerCard(height: 70)],
          error: (_, __) => [const SizedBox.shrink()],
          data: (res) => res.results.isEmpty
              ? [const Padding(
                  padding: EdgeInsets.only(top: 30),
                  child: EmptyStateView(icon: Icons.event_available, title: 'No leave requests'),
                )]
              : res.results.map((l) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: BrutalCard(
                      padding: const EdgeInsets.all(14),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Row(children: [
                          Expanded(child: Text(l.leaveTypeName, style: AppTextStyles.h5)),
                          _pill(l.status),
                        ]),
                        const SizedBox(height: 4),
                        Text(
                          '${Fmt.date(l.startDate.toIso8601String())} → '
                          '${Fmt.date(l.endDate.toIso8601String())}  ·  ${l.days} day(s)',
                          style: AppTextStyles.caption,
                        ),
                        if (l.reason.isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Text(l.reason, style: AppTextStyles.body),
                        ],
                        if (l.status == 'pending') ...[
                          const SizedBox(height: 8),
                          BrutalButton(
                            label: 'Cancel request',
                            backgroundColor: AppColors.white,
                            fontSize: 11,
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            onPressed: () async {
                              try {
                                await HrmsService.instance.cancelLeave(l.id);
                                ref.invalidate(_leaveProvider);
                                ref.invalidate(_balancesProvider);
                                if (context.mounted) AppToast.show(context, 'Request cancelled', isSuccess: true);
                              } catch (_) {
                                if (context.mounted) AppToast.show(context, 'Could not cancel', isError: true);
                              }
                            },
                          ),
                        ],
                      ]),
                    ),
                  )).toList(),
        ),
      ]),
    );
  }
}

Future<void> _showApplyLeave(BuildContext context, WidgetRef ref) async {
  final types = await ref.read(_leaveTypesProvider.future);
  if (!context.mounted) return;
  if (types.isEmpty) {
    AppToast.show(context, 'No leave types configured. Ask your HR team.', isError: true);
    return;
  }

  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: _ApplyLeaveForm(types: types, onDone: () {
        ref.invalidate(_leaveProvider);
        ref.invalidate(_balancesProvider);
      }),
    ),
  );
}

class _ApplyLeaveForm extends StatefulWidget {
  final List<LeaveType> types;
  final VoidCallback onDone;
  const _ApplyLeaveForm({required this.types, required this.onDone});

  @override
  State<_ApplyLeaveForm> createState() => _ApplyLeaveFormState();
}

class _ApplyLeaveFormState extends State<_ApplyLeaveForm> {
  late int _type = widget.types.first.id;
  DateTime _start = DateTime.now();
  DateTime _end = DateTime.now();
  final _reason = TextEditingController();
  bool _saving = false;

  /// The backend rejects `days` greater than the span of the range, so derive
  /// it rather than letting the agent type a number that will be refused.
  String get _days => '${_end.difference(_start).inDays + 1}.0';

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  Future<void> _pick(bool isStart) async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: isStart ? _start : _end,
      firstDate: now.subtract(const Duration(days: 90)),
      lastDate: now.add(const Duration(days: 365)),
    );
    if (picked == null) return;
    setState(() {
      if (isStart) {
        _start = picked;
        if (_end.isBefore(_start)) _end = _start;
      } else {
        _end = picked.isBefore(_start) ? _start : picked;
      }
    });
  }

  Future<void> _submit() async {
    if (_reason.text.trim().isEmpty) {
      AppToast.show(context, 'Add a reason for the leave', isError: true);
      return;
    }
    setState(() => _saving = true);
    try {
      await HrmsService.instance.applyLeave(
        leaveType: _type,
        startDate: _start,
        endDate: _end,
        days: _days,
        reason: _reason.text.trim(),
      );
      widget.onDone();
      if (mounted) {
        Navigator.pop(context);
        AppToast.show(context, 'Leave requested', isSuccess: true);
      }
    } catch (_) {
      if (mounted) AppToast.show(context, 'Could not submit the request', isError: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: const BoxDecoration(
        color: AppColors.background,
        border: Border(top: BorderSide(color: AppColors.black, width: 2)),
      ),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Apply for leave', style: AppTextStyles.h3),
        const SizedBox(height: 16),
        DropdownButtonFormField<int>(
          initialValue: _type,
          decoration: const InputDecoration(labelText: 'Leave type'),
          items: widget.types
              .map((t) => DropdownMenuItem(value: t.id, child: Text(t.name)))
              .toList(),
          onChanged: (v) => setState(() => _type = v ?? _type),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: _DateField(label: 'From', value: _start, onTap: () => _pick(true))),
          const SizedBox(width: 10),
          Expanded(child: _DateField(label: 'To', value: _end, onTap: () => _pick(false))),
        ]),
        const SizedBox(height: 6),
        Text('$_days day(s)', style: AppTextStyles.mono),
        const SizedBox(height: 12),
        BrutalTextField(controller: _reason, label: 'Reason', maxLines: 3),
        const SizedBox(height: 18),
        BrutalButton(
          label: 'Submit request',
          isFullWidth: true,
          isLoading: _saving,
          onPressed: _saving ? null : _submit,
        ),
      ]),
    );
  }
}

class _DateField extends StatelessWidget {
  final String label;
  final DateTime value;
  final VoidCallback onTap;
  const _DateField({required this.label, required this.value, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: InputDecorator(
        decoration: InputDecoration(labelText: label),
        child: Text(Fmt.date(value.toIso8601String()), style: AppTextStyles.body),
      ),
    );
  }
}

// ─── Expenses ───────────────────────────────────────────────
class _ExpensesTab extends ConsumerWidget {
  const _ExpensesTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_expensesProvider);

    return BrutalRefreshIndicator(
      onRefresh: () async => ref.invalidate(_expensesProvider),
      child: ListView(padding: const EdgeInsets.all(16), children: [
        BrutalButton(
          label: 'Claim an expense',
          iconData: Icons.add,
          isFullWidth: true,
          onPressed: () => showModalBottomSheet<void>(
            context: context,
            isScrollControlled: true,
            backgroundColor: Colors.transparent,
            builder: (_) => Padding(
              padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
              child: _ClaimExpenseForm(onDone: () => ref.invalidate(_expensesProvider)),
            ),
          ),
        ),
        const SizedBox(height: 6),
        Text('Attach the receipt from the web app — the mobile claim records the amount only.',
            style: AppTextStyles.caption),
        const SizedBox(height: 16),
        ...async.when(
          loading: () => [const ShimmerCard(height: 70)],
          error: (_, __) => [const SizedBox.shrink()],
          data: (res) => res.results.isEmpty
              ? [const Padding(
                  padding: EdgeInsets.only(top: 40),
                  child: EmptyStateView(icon: Icons.receipt_long, title: 'No claims yet'),
                )]
              : res.results.map((e) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: BrutalCard(
                      padding: const EdgeInsets.all(14),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Row(children: [
                          Expanded(child: Text(_pretty(e.category), style: AppTextStyles.h5)),
                          Text(Fmt.inr(e.amount), style: AppTextStyles.monoLg),
                        ]),
                        const SizedBox(height: 4),
                        Row(children: [
                          Text(Fmt.date(e.date.toIso8601String()), style: AppTextStyles.caption),
                          const Spacer(),
                          _pill(e.status),
                        ]),
                        if (e.description.isNotEmpty) ...[
                          const SizedBox(height: 6),
                          Text(e.description, style: AppTextStyles.body),
                        ],
                      ]),
                    ),
                  )).toList(),
        ),
      ]),
    );
  }
}

class _ClaimExpenseForm extends StatefulWidget {
  final VoidCallback onDone;
  const _ClaimExpenseForm({required this.onDone});

  @override
  State<_ClaimExpenseForm> createState() => _ClaimExpenseFormState();
}

class _ClaimExpenseFormState extends State<_ClaimExpenseForm> {
  String _category = _expenseCategories.first;
  DateTime _date = DateTime.now();
  final _amount = TextEditingController();
  final _description = TextEditingController();
  bool _saving = false;

  @override
  void dispose() {
    _amount.dispose();
    _description.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final amount = double.tryParse(_amount.text.trim());
    if (amount == null || amount <= 0) {
      AppToast.show(context, 'Enter a valid amount', isError: true);
      return;
    }
    setState(() => _saving = true);
    try {
      await HrmsService.instance.claimExpense(
        date: _date,
        category: _category,
        amount: amount.toStringAsFixed(2),
        description: _description.text.trim(),
      );
      widget.onDone();
      if (mounted) {
        Navigator.pop(context);
        AppToast.show(context, 'Claim submitted', isSuccess: true);
      }
    } catch (_) {
      if (mounted) AppToast.show(context, 'Could not submit the claim', isError: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: const BoxDecoration(
        color: AppColors.background,
        border: Border(top: BorderSide(color: AppColors.black, width: 2)),
      ),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Claim an expense', style: AppTextStyles.h3),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          initialValue: _category,
          decoration: const InputDecoration(labelText: 'Category'),
          items: _expenseCategories
              .map((c) => DropdownMenuItem(value: c, child: Text(_pretty(c))))
              .toList(),
          onChanged: (v) => setState(() => _category = v ?? _category),
        ),
        const SizedBox(height: 12),
        _DateField(
          label: 'Date',
          value: _date,
          onTap: () async {
            final now = DateTime.now();
            final picked = await showDatePicker(
              context: context,
              initialDate: _date,
              firstDate: now.subtract(const Duration(days: 180)),
              lastDate: now,
            );
            if (picked != null) setState(() => _date = picked);
          },
        ),
        const SizedBox(height: 12),
        BrutalTextField(
          controller: _amount,
          label: 'Amount (₹)',
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
        ),
        const SizedBox(height: 12),
        BrutalTextField(controller: _description, label: 'What was it for?', maxLines: 2),
        const SizedBox(height: 18),
        BrutalButton(
          label: 'Submit claim',
          isFullWidth: true,
          isLoading: _saving,
          onPressed: _saving ? null : _submit,
        ),
      ]),
    );
  }
}

// ─── Earnings (incentives + payslips) ───────────────────────
class _EarningsTab extends ConsumerWidget {
  const _EarningsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final features = ref.features;
    final incentives = ref.watch(_incentivesProvider);
    final payslips = ref.watch(_payslipsProvider);

    return BrutalRefreshIndicator(
      onRefresh: () async {
        ref.invalidate(_incentivesProvider);
        ref.invalidate(_payslipsProvider);
      },
      child: ListView(padding: const EdgeInsets.all(16), children: [
        if (features.has(Feat.incentiveEngine)) ...[
          const SectionHeader(title: 'Incentives'),
          const SizedBox(height: 8),
          ...incentives.when(
            loading: () => [const ShimmerCard(height: 60)],
            error: (_, __) => [const SizedBox.shrink()],
            data: (res) => res.results.isEmpty
                ? [Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: Text('No incentives earned yet.', style: AppTextStyles.caption),
                  )]
                : res.results.map((i) => Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: BrutalCard(
                        padding: const EdgeInsets.all(14),
                        child: Row(children: [
                          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(i.ruleName, style: AppTextStyles.h5),
                            const SizedBox(height: 3),
                            Text('${_month(i.periodMonth)}  ·  ${i.units} ${_pretty(i.metric).toLowerCase()}',
                                style: AppTextStyles.caption),
                          ])),
                          Text(Fmt.inr(i.amount), style: AppTextStyles.monoLg),
                        ]),
                      ),
                    )).toList(),
          ),
          const SizedBox(height: 20),
        ],

        if (features.has(Feat.hrmsPayroll)) ...[
          const SectionHeader(title: 'Payslips'),
          const SizedBox(height: 8),
          ...payslips.when(
            loading: () => [const ShimmerCard(height: 90)],
            error: (_, __) => [const SizedBox.shrink()],
            data: (res) => res.results.isEmpty
                ? [Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: Text('No payslips yet.', style: AppTextStyles.caption),
                  )]
                : res.results.map((p) => Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: BrutalCard(
                        padding: const EdgeInsets.all(14),
                        child: Column(children: [
                          Row(children: [
                            Expanded(child: Text(_month(p.periodMonth), style: AppTextStyles.h5)),
                            _pill(p.status),
                          ]),
                          const Divider(height: 20),
                          InfoRow(label: 'Gross', value: Fmt.inr(p.grossEarnings)),
                          InfoRow(label: 'Incentives', value: Fmt.inr(p.incentivesAmount)),
                          InfoRow(label: 'Reimbursements', value: Fmt.inr(p.reimbursementsAmount)),
                          InfoRow(label: 'Deductions', value: '− ${Fmt.inr(p.totalDeductions)}'),
                          const Divider(height: 20),
                          Row(children: [
                            Expanded(child: Text('NET PAY',
                                style: AppTextStyles.h5.copyWith(fontSize: 11, letterSpacing: 1))),
                            Text(Fmt.inr(p.netPay), style: AppTextStyles.monoLg),
                          ]),
                        ]),
                      ),
                    )).toList(),
          ),
        ],

        if (!features.has(Feat.incentiveEngine) && !features.has(Feat.hrmsPayroll))
          const Padding(
            padding: EdgeInsets.only(top: 60),
            child: EmptyStateView(
              icon: Icons.payments_outlined,
              title: 'Not available',
              message: 'Your plan does not include incentives or payroll.',
            ),
          ),
      ]),
    );
  }
}
