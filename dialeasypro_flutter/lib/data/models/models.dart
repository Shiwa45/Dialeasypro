// ============================================================
// DialEasypro — Data Models
// ============================================================

class Agent {
  final int id;
  final String email, name, phone, employeeId, role, roleDisplay;
  final bool isTenantAdmin, isActive, isOnline;
  final String? profilePhotoUrl, lastActiveAt, createdAt;
  final String timezone;
  final int totalLoginCount;

  const Agent({
    required this.id, required this.email, required this.name,
    this.phone = '', this.employeeId = '', required this.role,
    this.roleDisplay = '', this.isTenantAdmin = false, this.isActive = true,
    this.isOnline = false, this.profilePhotoUrl, this.lastActiveAt, this.createdAt,
    this.timezone = 'Asia/Kolkata', this.totalLoginCount = 0,
  });

  factory Agent.fromJson(Map<String, dynamic> j) => Agent(
    id: j['id'] as int,
    email: j['email'] as String? ?? '',
    name: j['name'] as String? ?? '',
    phone: j['phone'] as String? ?? '',
    employeeId: j['employee_id'] as String? ?? '',
    role: j['role'] as String? ?? 'agent',
    roleDisplay: j['role_display'] as String? ?? '',
    isTenantAdmin: j['is_tenant_admin'] as bool? ?? false,
    isActive: j['is_active'] as bool? ?? true,
    isOnline: j['is_online'] as bool? ?? false,
    profilePhotoUrl: j['profile_photo_url'] as String?,
    lastActiveAt: j['last_active_at'] as String?,
    createdAt: j['created_at'] as String?,
    timezone: j['timezone'] as String? ?? 'Asia/Kolkata',
    totalLoginCount: j['total_login_count'] as int? ?? 0,
  );

  String get initials => name.split(' ').map((n) => n.isNotEmpty ? n[0] : '').take(2).join().toUpperCase();
}

class Lead {
  final int id;
  final String name, phone, alternatePhone, email, city, state;
  final String source, sourceDisplay;
  final String status, statusDisplay;
  final String priority, priorityDisplay;
  final int score;
  final int? assignedTo;
  final String? assignedToName, budget, dealValue, nextFollowupAt, lastContactedAt;
  final String requirement;
  final bool followupOverdue, isDnd;
  final int contactCount;
  final List<String> tags;
  final String createdAt;

  const Lead({
    required this.id, required this.name, required this.phone,
    this.alternatePhone = '', this.email = '', this.city = '', this.state = '',
    this.source = 'manual', this.sourceDisplay = 'Manual',
    required this.status, this.statusDisplay = '',
    this.priority = 'medium', this.priorityDisplay = 'Medium',
    this.score = 0, this.assignedTo, this.assignedToName,
    this.budget, this.dealValue, this.nextFollowupAt, this.lastContactedAt,
    this.requirement = '', this.followupOverdue = false, this.isDnd = false,
    this.contactCount = 0, this.tags = const [], required this.createdAt,
  });

  factory Lead.fromJson(Map<String, dynamic> j) => Lead(
    id: j['id'] as int,
    name: j['name'] as String? ?? '',
    phone: j['phone'] as String? ?? '',
    alternatePhone: j['alternate_phone'] as String? ?? '',
    email: j['email'] as String? ?? '',
    city: j['city'] as String? ?? '',
    state: j['state'] as String? ?? '',
    source: j['source'] as String? ?? 'manual',
    sourceDisplay: j['source_display'] as String? ?? '',
    status: j['status'] as String? ?? 'new',
    statusDisplay: j['status_display'] as String? ?? '',
    priority: j['priority'] as String? ?? 'medium',
    priorityDisplay: j['priority_display'] as String? ?? '',
    score: j['score'] as int? ?? 0,
    assignedTo: j['assigned_to'] as int?,
    assignedToName: j['assigned_to_name'] as String?,
    budget: j['budget']?.toString(),
    dealValue: j['deal_value']?.toString(),
    nextFollowupAt: j['next_followup_at'] as String?,
    lastContactedAt: j['last_contacted_at'] as String?,
    requirement: j['requirement'] as String? ?? '',
    followupOverdue: j['followup_overdue'] as bool? ?? false,
    isDnd: j['is_dnd'] as bool? ?? false,
    contactCount: j['contact_count'] as int? ?? 0,
    tags: (j['tags'] as List?)?.cast<String>() ?? [],
    createdAt: j['created_at'] as String? ?? '',
  );

  String get initials => name.split(' ').map((n) => n.isNotEmpty ? n[0] : '').take(2).join().toUpperCase();
}

class FollowUp {
  final int id, lead, assignedTo;
  final String assignedToName, followupType, followupTypeDisplay;
  final String scheduledAt, notes, createdAt;
  final bool isCompleted, isOverdue;
  final String? completedAt;

  const FollowUp({
    required this.id, required this.lead, required this.assignedTo,
    this.assignedToName = '', required this.followupType, this.followupTypeDisplay = '',
    required this.scheduledAt, this.notes = '', required this.createdAt,
    this.isCompleted = false, this.isOverdue = false, this.completedAt,
  });

  factory FollowUp.fromJson(Map<String, dynamic> j) => FollowUp(
    id: j['id'] as int,
    lead: j['lead'] as int,
    assignedTo: j['assigned_to'] as int,
    assignedToName: j['assigned_to_name'] as String? ?? '',
    followupType: j['followup_type'] as String? ?? 'call',
    followupTypeDisplay: j['followup_type_display'] as String? ?? '',
    scheduledAt: j['scheduled_at'] as String? ?? '',
    notes: j['notes'] as String? ?? '',
    createdAt: j['created_at'] as String? ?? '',
    isCompleted: j['is_completed'] as bool? ?? false,
    isOverdue: j['is_overdue'] as bool? ?? false,
    completedAt: j['completed_at'] as String?,
  );
}

class LeadNote {
  final int id, lead;
  final int? agent;
  final String? agentName, attachment;
  final String content, createdAt;
  final bool isPinned;

  const LeadNote({
    required this.id, required this.lead, this.agent, this.agentName,
    required this.content, this.isPinned = false, this.attachment,
    required this.createdAt,
  });

  factory LeadNote.fromJson(Map<String, dynamic> j) => LeadNote(
    id: j['id'] as int,
    lead: j['lead'] as int,
    agent: j['agent'] as int?,
    agentName: j['agent_name'] as String?,
    content: j['content'] as String? ?? '',
    isPinned: j['is_pinned'] as bool? ?? false,
    attachment: j['attachment'] as String?,
    createdAt: j['created_at'] as String? ?? '',
  );
}

class CallLog {
  final String id;
  final int? agent, lead;
  final String? agentName, leadName, endedAt, dispositionName, recordingUrl;
  final String direction, phoneNumber, startedAt, notes, provider, durationDisplay;
  final int durationSeconds;
  final bool isConnected;
  final int? disposition;

  const CallLog({
    required this.id, this.agent, this.agentName, this.lead, this.leadName,
    required this.direction, required this.phoneNumber, required this.startedAt,
    this.endedAt, this.durationSeconds = 0, this.durationDisplay = '—',
    this.isConnected = false, this.disposition, this.dispositionName,
    this.notes = '', this.provider = '', this.recordingUrl,
  });

  factory CallLog.fromJson(Map<String, dynamic> j) => CallLog(
    id: j['id'] as String? ?? '',
    agent: j['agent'] as int?,
    agentName: j['agent_name'] as String?,
    lead: j['lead'] as int?,
    leadName: j['lead_name'] as String?,
    direction: j['direction'] as String? ?? 'outbound',
    phoneNumber: j['phone_number'] as String? ?? '',
    startedAt: j['started_at'] as String? ?? '',
    endedAt: j['ended_at'] as String?,
    durationSeconds: j['duration_seconds'] as int? ?? 0,
    durationDisplay: j['duration_display'] as String? ?? '—',
    isConnected: j['is_connected'] as bool? ?? false,
    disposition: j['disposition'] as int?,
    dispositionName: j['disposition_name'] as String?,
    notes: j['notes'] as String? ?? '',
    provider: j['provider'] as String? ?? '',
    recordingUrl: _extractRecordingUrl(j),
  );
}

String? _extractRecordingUrl(Map<String, dynamic> j) {
  final rec = j['recording'];
  if (rec is Map) {
    final url = rec['playback_url'];
    return url is String ? url : null;
  }
  return j['recording_url'] as String?;
}

class CallDisposition {
  final int id;
  final String name, slug;
  final bool isPositive;
  final int? autoFollowupHours;

  const CallDisposition({
    required this.id, required this.name, required this.slug,
    this.isPositive = false, this.autoFollowupHours,
  });

  factory CallDisposition.fromJson(Map<String, dynamic> j) => CallDisposition(
    id: j['id'] as int,
    name: j['name'] as String? ?? '',
    slug: j['slug'] as String? ?? '',
    isPositive: j['is_positive'] as bool? ?? false,
    autoFollowupHours: j['auto_followup_hours'] as int?,
  );
}

class WhatsAppTemplate {
  final int id;
  final String name, category, language, bodyText, headerText, status, provider;
  final int usageCount;

  const WhatsAppTemplate({
    required this.id, required this.name, this.category = 'utility',
    this.language = 'en', required this.bodyText, this.headerText = '',
    this.status = 'pending', this.provider = 'interakt', this.usageCount = 0,
  });

  factory WhatsAppTemplate.fromJson(Map<String, dynamic> j) => WhatsAppTemplate(
    id: j['id'] as int,
    name: j['name'] as String? ?? '',
    category: j['category'] as String? ?? 'utility',
    language: j['language'] as String? ?? 'en',
    bodyText: j['body_text'] as String? ?? '',
    headerText: j['header_text'] as String? ?? '',
    status: j['status'] as String? ?? 'pending',
    provider: j['provider'] as String? ?? 'interakt',
    usageCount: j['usage_count'] as int? ?? 0,
  );
}

class LeadStats {
  final int newLeadsToday, followupsDue, overdueFollowups;
  final int totalLeads, activeLeads, won, lost;
  final double conversionRate, pipelineValue;
  final Map<String, int> byStatus;

  const LeadStats({
    this.newLeadsToday = 0, this.followupsDue = 0, this.overdueFollowups = 0,
    this.totalLeads = 0, this.activeLeads = 0, this.won = 0, this.lost = 0,
    this.conversionRate = 0, this.pipelineValue = 0, this.byStatus = const {},
  });

  factory LeadStats.fromJson(Map<String, dynamic> j) {
    final today = j['today'] as Map<String, dynamic>? ?? {};
    final total = j['total'] as Map<String, dynamic>? ?? {};
    return LeadStats(
      newLeadsToday: today['new_leads'] as int? ?? 0,
      followupsDue: today['followups_due'] as int? ?? 0,
      overdueFollowups: today['overdue_followups'] as int? ?? 0,
      totalLeads: total['total_leads'] as int? ?? 0,
      activeLeads: total['active_leads'] as int? ?? 0,
      won: total['won'] as int? ?? 0,
      lost: total['lost'] as int? ?? 0,
      conversionRate: (total['conversion_rate'] as num?)?.toDouble() ?? 0,
      pipelineValue: (total['pipeline_value'] as num?)?.toDouble() ?? 0,
      byStatus: (j['by_status'] as Map<String, dynamic>?)?.map((k, v) => MapEntry(k, v as int)) ?? {},
    );
  }
}

class PaginatedResponse<T> {
  final int count, totalPages, currentPage;
  final List<T> results;

  const PaginatedResponse({
    required this.count, required this.totalPages,
    required this.currentPage, required this.results,
  });

  factory PaginatedResponse.fromJson(
    Map<String, dynamic> j, T Function(Map<String, dynamic>) fromJson,
  ) => PaginatedResponse<T>(
    count: j['count'] as int? ?? 0,
    totalPages: j['total_pages'] as int? ?? 1,
    currentPage: j['current_page'] as int? ?? 1,
    results: (j['results'] as List?)?.map((e) => fromJson(e as Map<String, dynamic>)).toList() ?? [],
  );
}

class LoginResponse {
  final String access, refresh;
  final Agent agent;
  final bool mustChangePassword;

  const LoginResponse({
    required this.access, required this.refresh,
    required this.agent, this.mustChangePassword = false,
  });

  factory LoginResponse.fromJson(Map<String, dynamic> j) => LoginResponse(
    access: j['access'] as String,
    refresh: j['refresh'] as String,
    agent: Agent.fromJson(j['agent'] as Map<String, dynamic>),
    mustChangePassword: j['must_change_password'] as bool? ?? false,
  );
}
