// ─────────────────────────────────────────────────────────────
// Services for the add-on modules the AGENT app uses.
//
// Only agent-scoped reads and writes live here. The backend already restricts
// a plain agent to their own calls and their own employment record, so these
// take no employee id — "me" is implied by the JWT.
// ─────────────────────────────────────────────────────────────
import 'api_client.dart';
import '../models/addon_models.dart';
import '../models/models.dart';

final _dio = ApiClient.instance.dio;

// ─── Plan features / add-on modules ─────────────────────────
class FeaturesService {
  FeaturesService._();
  static final instance = FeaturesService._();

  Future<TenantFeatures> fetch() async =>
      TenantFeatures.fromJson((await _dio.get('/auth/features/')).data as Map<String, dynamic>);
}

// ─── AI Suite ───────────────────────────────────────────────
class AiService {
  AiService._();
  static final instance = AiService._();

  Future<CallTranscript> transcript(String callId) async =>
      CallTranscript.fromJson((await _dio.get('/ai/calls/$callId/transcript/')).data as Map<String, dynamic>);

  /// Returns null while the call hasn't been analysed yet — the endpoint
  /// answers 200 with `{status: pending}` rather than 404 in that case.
  Future<CallInsight?> insight(String callId) async {
    final data = (await _dio.get('/ai/calls/$callId/insight/')).data as Map<String, dynamic>;
    if (data['id'] == null) return null;
    return CallInsight.fromJson(data);
  }
}

// ─── HRMS (the agent's own records) ─────────────────────────
class HrmsService {
  HrmsService._();
  static final instance = HrmsService._();

  /// `{enrolled: false}` when the agent has no Employee record yet.
  Future<Map<String, dynamic>> me() async =>
      ((await _dio.get('/hrms/me/')).data as Map).cast<String, dynamic>();

  // Attendance
  Future<PaginatedResponse<Attendance>> attendance({int page = 1}) async =>
      PaginatedResponse.fromJson(
        (await _dio.get('/hrms/attendance/', queryParameters: {'page': page})).data,
        Attendance.fromJson,
      );

  Future<void> checkIn() async => await _dio.post('/hrms/attendance/check-in/');
  Future<void> checkOut() async => await _dio.post('/hrms/attendance/check-out/');

  // Leave
  Future<List<LeaveBalance>> leaveBalances() async {
    final res = await _dio.get('/hrms/leave-balances/');
    return ((res.data as List?) ?? [])
        .map((e) => LeaveBalance.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<LeaveType>> leaveTypes() async {
    final res = await _dio.get('/hrms/leave-types/');
    return ((res.data as List?) ?? [])
        .map((e) => LeaveType.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<PaginatedResponse<LeaveRequest>> leaveRequests({int page = 1}) async =>
      PaginatedResponse.fromJson(
        (await _dio.get('/hrms/leave/', queryParameters: {'page': page})).data,
        LeaveRequest.fromJson,
      );

  Future<void> applyLeave({
    required int leaveType,
    required DateTime startDate,
    required DateTime endDate,
    required String days,
    required String reason,
  }) async {
    await _dio.post('/hrms/leave/', data: {
      'leave_type': leaveType,
      'start_date': _date(startDate),
      'end_date': _date(endDate),
      'days': days,
      'reason': reason,
    });
  }

  /// An agent may cancel their own pending request; approve/reject are the
  /// manager's, and the backend rejects them from an agent's token.
  Future<void> cancelLeave(int id) async => await _dio.post('/hrms/leave/$id/cancel/');

  // Expenses
  Future<PaginatedResponse<ExpenseClaim>> expenses({int page = 1}) async =>
      PaginatedResponse.fromJson(
        (await _dio.get('/hrms/expenses/', queryParameters: {'page': page})).data,
        ExpenseClaim.fromJson,
      );

  Future<void> claimExpense({
    required DateTime date,
    required String category,
    required String amount,
    required String description,
  }) async {
    await _dio.post('/hrms/expenses/', data: {
      'date': _date(date),
      'category': category,
      'amount': amount,
      'description': description,
    });
  }

  // Earnings
  Future<PaginatedResponse<IncentiveEarning>> incentives({int page = 1}) async =>
      PaginatedResponse.fromJson(
        (await _dio.get('/hrms/incentives/', queryParameters: {'page': page})).data,
        IncentiveEarning.fromJson,
      );

  Future<PaginatedResponse<Payslip>> payslips({int page = 1}) async =>
      PaginatedResponse.fromJson(
        (await _dio.get('/hrms/payslips/', queryParameters: {'page': page})).data,
        Payslip.fromJson,
      );

  static String _date(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}
