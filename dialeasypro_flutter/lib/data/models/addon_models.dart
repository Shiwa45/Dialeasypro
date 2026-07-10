// ─────────────────────────────────────────────────────────────
// Models for the add-on modules the AGENT app cares about.
//
// The mobile app is for callers. It carries the parts of HRMS an agent
// touches for themselves (their attendance, their leave, their claims, their
// pay) and the AI insight for calls they made. It deliberately carries none
// of ERP, no approvals, no payroll runs, and no colleague's records — those
// are manager surfaces and live in the web admin.
// ─────────────────────────────────────────────────────────────

/// Plan features + add-on modules the tenant has bought.
/// Hiding UI on `has`/`hasModule` is convenience only — every endpoint is
/// re-checked server-side and answers 402 when the plan doesn't cover it.
class TenantFeatures {
  final Map<String, bool> features;
  final Map<String, bool> modules;

  const TenantFeatures({required this.features, required this.modules});

  const TenantFeatures.empty() : features = const {}, modules = const {};

  factory TenantFeatures.fromJson(Map<String, dynamic> j) => TenantFeatures(
    features: ((j['features'] as Map?) ?? {}).map((k, v) => MapEntry('$k', v == true)),
    modules: ((j['modules'] as Map?) ?? {}).map((k, v) => MapEntry('$k', v == true)),
  );

  bool has(String key) => features[key] == true;
  bool hasModule(String key) => modules[key] == true;
}

/// Feature + module keys. These strings must match apps/core/constants.py
/// exactly — a typo here silently hides a feature the tenant paid for, and
/// nothing in either language will catch it.
class Feat {
  static const aiTranscription = 'ai_call_transcription';
  static const aiInsights = 'ai_call_insights';
  static const hrmsAttendance = 'hrms_attendance';
  static const hrmsLeave = 'hrms_leave';
  static const hrmsExpenses = 'hrms_expenses';
  static const hrmsPayroll = 'hrms_payroll';
  // Not `hrms_incentives` — the backend key predates the HRMS module.
  static const incentiveEngine = 'incentive_engine';
}

class Mod {
  static const aiSuite = 'ai_suite';
  static const hrms = 'hrms';
}

// ─── AI ─────────────────────────────────────────────────────
class CallTranscript {
  final String transcript, status, language;
  final DateTime? transcribedAt;

  const CallTranscript({
    required this.transcript,
    required this.status,
    required this.language,
    this.transcribedAt,
  });

  factory CallTranscript.fromJson(Map<String, dynamic> j) => CallTranscript(
    transcript: j['transcript'] as String? ?? '',
    status: j['transcript_status'] as String? ?? 'pending',
    language: j['transcript_language'] as String? ?? '',
    transcribedAt: DateTime.tryParse(j['transcribed_at'] as String? ?? ''),
  );

  bool get isReady => status == 'done' && transcript.isNotEmpty;
}

class CallInsight {
  final String status, summary, sentiment, nextAction, coachingNotes;
  final double? sentimentScore;
  final List<String> keyPoints, objections;
  final String? suggestedDispositionName;
  final DateTime? generatedAt;

  const CallInsight({
    required this.status,
    required this.summary,
    required this.sentiment,
    required this.nextAction,
    required this.coachingNotes,
    required this.keyPoints,
    required this.objections,
    this.sentimentScore,
    this.suggestedDispositionName,
    this.generatedAt,
  });

  static List<String> _strings(dynamic v) =>
      (v as List?)?.map((e) => '$e').where((s) => s.isNotEmpty).toList() ?? const [];

  factory CallInsight.fromJson(Map<String, dynamic> j) => CallInsight(
    status: j['status'] as String? ?? 'pending',
    summary: j['summary'] as String? ?? '',
    sentiment: j['sentiment'] as String? ?? '',
    sentimentScore: (j['sentiment_score'] as num?)?.toDouble(),
    keyPoints: _strings(j['key_points']),
    objections: _strings(j['objections']),
    nextAction: j['next_action'] as String? ?? '',
    suggestedDispositionName: j['suggested_disposition_name'] as String?,
    coachingNotes: j['coaching_notes'] as String? ?? '',
    generatedAt: DateTime.tryParse(j['generated_at'] as String? ?? ''),
  );

  bool get isReady => status == 'done';
}

// ─── HRMS (agent's own records only) ────────────────────────
class Attendance {
  final int id;
  final DateTime date;
  final String status, note;
  final double workedHours;
  final int breakSeconds;
  final DateTime? checkIn, checkOut;

  const Attendance({
    required this.id,
    required this.date,
    required this.status,
    required this.note,
    required this.workedHours,
    required this.breakSeconds,
    this.checkIn,
    this.checkOut,
  });

  factory Attendance.fromJson(Map<String, dynamic> j) => Attendance(
    id: j['id'] as int,
    date: DateTime.parse(j['date'] as String),
    status: j['status'] as String? ?? '',
    note: j['note'] as String? ?? '',
    workedHours: (j['worked_hours'] as num?)?.toDouble() ?? 0,
    breakSeconds: j['break_seconds'] as int? ?? 0,
    checkIn: DateTime.tryParse(j['check_in'] as String? ?? ''),
    checkOut: DateTime.tryParse(j['check_out'] as String? ?? ''),
  );
}

class LeaveBalance {
  final int id, leaveType;
  final String leaveTypeName;
  final String allocatedDays, usedDays, remainingDays;

  const LeaveBalance({
    required this.id,
    required this.leaveType,
    required this.leaveTypeName,
    required this.allocatedDays,
    required this.usedDays,
    required this.remainingDays,
  });

  factory LeaveBalance.fromJson(Map<String, dynamic> j) => LeaveBalance(
    id: j['id'] as int,
    leaveType: j['leave_type'] as int,
    leaveTypeName: j['leave_type_name'] as String? ?? '',
    allocatedDays: '${j['allocated_days'] ?? '0'}',
    usedDays: '${j['used_days'] ?? '0'}',
    remainingDays: '${j['remaining_days'] ?? '0'}',
  );
}

class LeaveRequest {
  final int id;
  final String leaveTypeName, reason, status, days;
  final DateTime startDate, endDate;

  const LeaveRequest({
    required this.id,
    required this.leaveTypeName,
    required this.reason,
    required this.status,
    required this.days,
    required this.startDate,
    required this.endDate,
  });

  factory LeaveRequest.fromJson(Map<String, dynamic> j) => LeaveRequest(
    id: j['id'] as int,
    leaveTypeName: j['leave_type_name'] as String? ?? '',
    reason: j['reason'] as String? ?? '',
    status: j['status'] as String? ?? 'pending',
    days: '${j['days'] ?? '0'}',
    startDate: DateTime.parse(j['start_date'] as String),
    endDate: DateTime.parse(j['end_date'] as String),
  );
}

class LeaveType {
  final int id;
  final String name;
  const LeaveType({required this.id, required this.name});

  factory LeaveType.fromJson(Map<String, dynamic> j) =>
      LeaveType(id: j['id'] as int, name: j['name'] as String? ?? '');
}

class ExpenseClaim {
  final int id;
  final DateTime date;
  final String category, amount, description, status;

  const ExpenseClaim({
    required this.id,
    required this.date,
    required this.category,
    required this.amount,
    required this.description,
    required this.status,
  });

  factory ExpenseClaim.fromJson(Map<String, dynamic> j) => ExpenseClaim(
    id: j['id'] as int,
    date: DateTime.parse(j['date'] as String),
    category: j['category'] as String? ?? 'other',
    amount: '${j['amount'] ?? '0'}',
    description: j['description'] as String? ?? '',
    status: j['status'] as String? ?? 'pending',
  );
}

class IncentiveEarning {
  final int id;
  final String ruleName, metric, units, amount;
  final DateTime periodMonth;

  const IncentiveEarning({
    required this.id,
    required this.ruleName,
    required this.metric,
    required this.units,
    required this.amount,
    required this.periodMonth,
  });

  factory IncentiveEarning.fromJson(Map<String, dynamic> j) => IncentiveEarning(
    id: j['id'] as int,
    ruleName: j['rule_name'] as String? ?? '',
    metric: j['metric'] as String? ?? '',
    units: '${j['units'] ?? '0'}',
    amount: '${j['amount'] ?? '0'}',
    periodMonth: DateTime.parse(j['period_month'] as String),
  );
}

class Payslip {
  final int id;
  final DateTime periodMonth;
  final String grossEarnings, incentivesAmount, reimbursementsAmount;
  final String totalDeductions, netPay, status;
  final String payableDays, totalDays;

  const Payslip({
    required this.id,
    required this.periodMonth,
    required this.grossEarnings,
    required this.incentivesAmount,
    required this.reimbursementsAmount,
    required this.totalDeductions,
    required this.netPay,
    required this.status,
    required this.payableDays,
    required this.totalDays,
  });

  factory Payslip.fromJson(Map<String, dynamic> j) => Payslip(
    id: j['id'] as int,
    periodMonth: DateTime.parse(j['period_month'] as String),
    grossEarnings: '${j['gross_earnings'] ?? '0'}',
    incentivesAmount: '${j['incentives_amount'] ?? '0'}',
    reimbursementsAmount: '${j['reimbursements_amount'] ?? '0'}',
    totalDeductions: '${j['total_deductions'] ?? '0'}',
    netPay: '${j['net_pay'] ?? '0'}',
    status: j['status'] as String? ?? 'draft',
    payableDays: '${j['payable_days'] ?? '0'}',
    totalDays: '${j['total_days'] ?? '0'}',
  );
}
