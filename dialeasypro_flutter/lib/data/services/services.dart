import 'api_client.dart';
import '../models/models.dart';

final _dio = ApiClient.instance.dio;

// ─── AUTH ───────────────────────────────────────────────────
class AuthService {
  AuthService._();
  static final instance = AuthService._();

  Future<LoginResponse> login(String email, String password) async {
    final r = await _dio.post('/auth/login/', data: {'email': email, 'password': password});
    return LoginResponse.fromJson(r.data);
  }

  Future<void> logout(String refresh) async {
    await _dio.post('/auth/logout/', data: {'refresh': refresh});
  }

  Future<Agent> getProfile() async {
    final r = await _dio.get('/auth/me/');
    return Agent.fromJson(r.data);
  }

  Future<Agent> updateProfile(Map<String, dynamic> data) async {
    final r = await _dio.patch('/auth/me/', data: data);
    return Agent.fromJson(r.data);
  }

  Future<void> changePassword({required String oldPassword, required String newPassword, required String confirmPassword}) async {
    await _dio.post('/auth/change-password/', data: {
      'old_password': oldPassword, 'new_password': newPassword, 'confirm_password': confirmPassword,
    });
  }
}

// ─── LEADS ──────────────────────────────────────────────────
class LeadsService {
  LeadsService._();
  static final instance = LeadsService._();

  Future<PaginatedResponse<Lead>> listLeads({
    int page = 1, int pageSize = 20,
    String? status, String? priority, String? source,
    String? search, String? assignedTo, bool? overdue,
  }) async {
    final r = await _dio.get('/leads/', queryParameters: {
      'page': page, 'page_size': pageSize,
      if (status != null && status.isNotEmpty) 'status': status,
      if (priority != null && priority.isNotEmpty) 'priority': priority,
      if (source != null && source.isNotEmpty) 'source': source,
      if (search != null && search.isNotEmpty) 'search': search,
      if (assignedTo != null && assignedTo.isNotEmpty) 'assigned_to': assignedTo,
      if (overdue == true) 'overdue': 'true',
      'order_by': '-created_at',
    });
    return PaginatedResponse.fromJson(r.data, Lead.fromJson);
  }

  Future<Lead> getLead(int id) async => Lead.fromJson((await _dio.get('/leads/$id/')).data);
  Future<Lead> createLead(Map<String, dynamic> data) async => Lead.fromJson((await _dio.post('/leads/', data: data)).data);
  Future<Lead> updateLead(int id, Map<String, dynamic> data) async => Lead.fromJson((await _dio.patch('/leads/$id/', data: data)).data);
  Future<void> deleteLead(int id) async => await _dio.delete('/leads/$id/');
  Future<void> updateStatus(int id, String status) async => await _dio.patch('/leads/$id/status/', data: {'status': status});

  Future<LeadStats> getStats() async => LeadStats.fromJson((await _dio.get('/leads/stats/')).data);
  Future<Map<String, dynamic>> getPipeline() async => (await _dio.get('/leads/pipeline/')).data;

  Future<PaginatedResponse<FollowUp>> listFollowups(int leadId) async =>
      PaginatedResponse.fromJson((await _dio.get('/leads/$leadId/followups/')).data, FollowUp.fromJson);

  Future<FollowUp> createFollowup(int leadId, Map<String, dynamic> data) async =>
      FollowUp.fromJson((await _dio.post('/leads/$leadId/followups/', data: data)).data);

  Future<void> completeFollowup(int id, {String notes = ''}) async =>
      await _dio.post('/leads/followups/$id/complete/', data: {'notes': notes});

  Future<PaginatedResponse<LeadNote>> listNotes(int leadId) async =>
      PaginatedResponse.fromJson((await _dio.get('/leads/$leadId/notes/')).data, LeadNote.fromJson);

  Future<LeadNote> createNote(int leadId, String content, {String? attachmentUrl}) async =>
      LeadNote.fromJson((await _dio.post('/leads/$leadId/notes/', data: {
        'content': content, if (attachmentUrl != null) 'attachment_url': attachmentUrl,
      })).data);
}

// ─── CALLS ──────────────────────────────────────────────────
class CallsService {
  CallsService._();
  static final instance = CallsService._();

  Future<PaginatedResponse<CallLog>> listCalls({
    int page = 1, String? leadId, String? direction, String? connected,
    String? dateFrom, String? dateTo,
  }) async {
    final r = await _dio.get('/calls/', queryParameters: {
      'page': page, 'page_size': 25,
      if (leadId != null) 'lead': leadId,
      if (direction != null && direction.isNotEmpty) 'direction': direction,
      if (connected != null && connected.isNotEmpty) 'connected': connected,
      if (dateFrom != null) 'date_from': dateFrom,
      if (dateTo != null) 'date_to': dateTo,
    });
    return PaginatedResponse.fromJson(r.data, CallLog.fromJson);
  }

  Future<CallLog> createCall(Map<String, dynamic> data) async =>
      CallLog.fromJson((await _dio.post('/calls/', data: data)).data);

  Future<Map<String, dynamic>> clickToCall(int leadId, {String? phoneNumber}) async {
    final r = await _dio.post('/calls/click-to-call/', data: {
      'lead_id': leadId, if (phoneNumber != null) 'phone_number': phoneNumber,
    });
    return r.data;
  }

  Future<List<CallDisposition>> getDispositions() async {
    final r = await _dio.get('/calls/dispositions/');
    return (r.data as List).map((e) => CallDisposition.fromJson(e)).toList();
  }

  Future<Map<String, dynamic>> getStats() async => (await _dio.get('/calls/stats/')).data;
}

// ─── COMMUNICATIONS ─────────────────────────────────────────
class CommsService {
  CommsService._();
  static final instance = CommsService._();

  Future<List<WhatsAppTemplate>> listTemplates({bool approvedOnly = true}) async {
    final r = await _dio.get('/comms/whatsapp/templates/',
        queryParameters: approvedOnly ? {'approved_only': true} : null);
    return (r.data as List).map((e) => WhatsAppTemplate.fromJson(e)).toList();
  }

  Future<void> sendWhatsApp(int leadId, String message, {int? templateId}) async {
    await _dio.post('/comms/whatsapp/send/', data: {
      'lead_id': leadId, 'message': message,
      if (templateId != null) 'template_id': templateId,
    });
  }

  Future<void> sendSMS(int leadId, String message, {String? senderId}) async {
    await _dio.post('/comms/sms/send/', data: {
      'lead_id': leadId, 'message': message,
      if (senderId != null) 'sender_id': senderId,
    });
  }
}

// ─── REPORTS ────────────────────────────────────────────────
class ReportsService {
  ReportsService._();
  static final instance = ReportsService._();

  Future<Map<String, dynamic>> dailyActivity() async => (await _dio.get('/reports/daily-activity/')).data;
  Future<Map<String, dynamic>> callAnalytics() async => (await _dio.get('/reports/call-analytics/')).data;
  Future<Map<String, dynamic>> conversionFunnel() async => (await _dio.get('/reports/conversion-funnel/')).data;
}

// ============================================================
// QUEUE SERVICE  /api/v1/leads/queues/
// Pull-based calling queues: leads are checked out one at a time and locked
// to this agent, so no lead is ever served to two agents or repeated.
// ============================================================
class QueueService {
  QueueService._();
  static final instance = QueueService._();

  /// Queues this agent is a member of, with live pending-lead counts.
  Future<List<Map<String, dynamic>>> available() async {
    final res = await _dio.get('/leads/queues/available/');
    return ((res.data as List?) ?? []).cast<Map<String, dynamic>>();
  }

  /// Atomically check out the next lead from a queue.
  /// Returns {lead, lock_expires_at, queue} or {empty: true}.
  Future<Map<String, dynamic>> pullNext(int queueId) async {
    final res = await _dio.post('/leads/queues/$queueId/pull/');
    return (res.data as Map).cast<String, dynamic>();
  }

  /// Release a checked-out lead (skip / end session). mark_dialed=true if it was dialed.
  Future<void> release(int leadId, {bool markDialed = false}) async {
    await _dio.post('/leads/queues/release/', data: {
      'lead_id': leadId,
      'mark_dialed': markDialed,
    });
  }
}
