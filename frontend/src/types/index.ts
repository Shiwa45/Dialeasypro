// ============================================================
// DialEasypro — TypeScript Types
// Mirrors the Django backend models exactly
// ============================================================

// ---- Auth ----
export interface Agent {
  id: number;
  email: string;
  name: string;
  phone: string;
  employee_id: string;
  role: AgentRole;
  role_display: string;
  is_tenant_admin: boolean;
  is_active: boolean;
  profile_photo_url: string | null;
  timezone: string;
  language_preference: string;
  shift_start: string | null;
  shift_end: string | null;
  working_days: number[];
  is_online: boolean;
  last_active_at: string | null;
  last_login: string | null;
  total_login_count: number;
  teams: AgentTeamMembership[];
  created_at: string;
}

export type AgentRole = 'admin' | 'manager' | 'senior_agent' | 'agent' | 'trainee';

export interface AgentTeamMembership {
  team_id: number;
  team_name: string;
  is_team_lead: boolean;
}

export interface Team {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  member_count: number;
  created_at: string;
}

export interface LoginResponse {
  access: string;
  refresh: string;
  access_expires_in: number;
  token_type: string;
  agent: Agent;
  must_change_password: boolean;
}

// ---- Leads ----
export type LeadStatus =
  | 'new' | 'attempted' | 'contacted' | 'interested'
  | 'not_interested' | 'follow_up' | 'negotiation'
  | 'converted' | 'lost' | 'duplicate';

export type LeadPriority = 'hot' | 'high' | 'medium' | 'low';
export type LeadSource =
  | 'manual' | 'indiamart' | 'meta_facebook' | 'google_ads'
  | 'website' | 'referral' | 'csv_import' | 'webhook' | 'other';

export interface Lead {
  id: number;
  name: string;
  phone: string;
  alternate_phone: string;
  email: string;
  city: string;
  state: string;
  pincode: string;
  source: LeadSource;
  source_display: string;
  status: LeadStatus;
  status_display: string;
  priority: LeadPriority;
  priority_display: string;
  score: number;
  assigned_to: number | null;
  assigned_to_name: string | null;
  assigned_at: string | null;
  budget: string | null;
  requirement: string;
  deal_value: string | null;
  expected_close_date: string | null;
  pipeline_stage: number;
  next_followup_at: string | null;
  followup_overdue: boolean;
  last_contacted_at: string | null;
  days_since_last_contact: number | null;
  contact_count: number;
  is_dnd: boolean;
  campaign_name?: string;
  ad_name?: string;
  tags: string[];
  followups?: FollowUp[];
  notes?: LeadNote[];
  activities?: LeadActivity[];
  custom_field_values?: CustomFieldValue[];
  created_at: string;
  updated_at: string;
}

export interface FollowUp {
  id: number;
  lead: number;
  assigned_to: number;
  assigned_to_name: string;
  followup_type: string;
  followup_type_display: string;
  scheduled_at: string;
  notes: string;
  is_completed: boolean;
  completed_at: string | null;
  completion_notes: string;
  is_overdue: boolean;
  created_at: string;
}

export interface LeadNote {
  id: number;
  lead: number;
  agent: number | null;
  agent_name: string | null;
  agent_photo: string | null;
  content: string;
  is_pinned: boolean;
  attachment: string | null;
  created_at: string;
}

export interface LeadActivity {
  id: number;
  activity_type: string;
  description: string;
  performed_by: number | null;
  performed_by_name: string | null;
  meta: Record<string, unknown>;
  timestamp: string;
}

export interface CustomField {
  id: number;
  name: string;
  field_key: string;
  field_type: string;
  is_required: boolean;
  is_active: boolean;
  sort_order: number;
  options: string[];
  placeholder: string;
}

export interface CustomFieldValue {
  field: number;
  field_key: string;
  field_name: string;
  value: string;
}

export interface LeadImportJob {
  id: string;
  original_filename: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'partial';
  imported_by_name: string;
  total_rows: number;
  processed_rows: number;
  successful_rows: number;
  failed_rows: number;
  duplicate_rows: number;
  progress_percent: number;
  duplicate_action: string;
  created_at: string;
  completed_at: string | null;
}

export interface LeadStats {
  today: { new_leads: number; followups_due: number; overdue_followups: number; };
  total: { total_leads: number; active_leads: number; won: number; lost: number; conversion_rate: number; pipeline_value: number; };
  by_status: Record<string, number>;
}

export interface PipelineData {
  [status: string]: Array<{
    id: number; name: string; phone: string; city: string;
    priority: string; score: number; deal_value: string | null;
    next_followup_at: string | null; 'assigned_to__name': string; created_at: string;
  }>;
}

// ---- Calls ----
export interface CallLog {
  id: string;
  agent: number | null;
  agent_name: string | null;
  lead: number | null;
  lead_name: string | null;
  direction: 'outbound' | 'inbound';
  phone_number: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number;
  duration_display: string;
  is_connected: boolean;
  disposition: number | null;
  disposition_name: string | null;
  notes: string;
  provider: string;
  provider_call_id: string;
  call_cost_paise: number;
  recording: CallRecording | null;
  created_at: string;
}

export interface CallRecording {
  id: string;
  duration_seconds: number;
  format: string;
  transcript: string;
  transcript_status: string;
  playback_url: string | null;
}

export interface CallDisposition {
  id: number;
  name: string;
  slug: string;
  is_positive: boolean;
  auto_followup_hours: number | null;
}

export interface CallStats {
  today: { total: number; connected: number; total_duration_seconds: number; };
  period: { total_calls: number; connected_calls: number; connection_rate: number; total_duration_seconds: number; avg_duration_seconds: number; total_cost_rupees: number; };
  by_disposition: Array<{ disposition__name: string; disposition__is_positive: boolean; count: number }>;
}

// ---- Communications ----
export interface WhatsAppTemplate {
  id: number;
  name: string;
  category: string;
  language: string;
  header_text: string;
  body_text: string;
  footer_text: string;
  variable_mapping: Record<string, string>;
  provider: string;
  status: 'pending' | 'approved' | 'rejected' | 'paused';
  is_active: boolean;
  usage_count: number;
}

export interface BulkCampaign {
  id: string;
  name: string;
  channel: 'whatsapp' | 'email' | 'sms';
  created_by: number;
  created_by_name: string;
  audience_filters: Record<string, unknown>;
  estimated_recipients: number;
  template: number | null;
  email_subject: string;
  email_body: string;
  sms_text: string;
  sms_sender_id: string;
  status: 'draft' | 'scheduled' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  total_recipients: number;
  sent_count: number;
  delivered_count: number;
  failed_count: number;
  replied_count: number;
  delivery_rate: number;
  progress_percent: number;
  created_at: string;
}

// ---- Reports ----
export interface AgentPerformanceReport {
  period: { date_from: string; date_to: string };
  agents: AgentPerformanceRow[];
}

export interface AgentPerformanceRow {
  agent_id: number;
  agent_name: string;
  agent_role: string;
  leads: { total: number; new: number; interested: number; converted: number; lost: number; conversion_rate: number; avg_score: number };
  calls: { total: number; connected: number; connection_rate: number; total_duration_seconds: number };
}

export interface ConversionFunnelReport {
  period: { date_from: string; date_to: string };
  funnel: Array<{ status: string; label: string; count: number; pct_of_total: number }>;
  total: number;
  lost: number;
}

export interface CallAnalyticsReport {
  period: { date_from: string; date_to: string };
  summary: { total_calls: number; connected_calls: number; connection_rate: number; total_duration_seconds: number; avg_duration_seconds: number; total_cost_rupees: number };
  daily_trend: Array<{ date: string; total: number; connected: number; connection_rate: number }>;
  by_disposition: Array<{ disposition__name: string; disposition__is_positive: boolean; count: number }>;
}

// ---- Integrations ----
export interface IntegrationConfig {
  id: number;
  source: string;
  source_display: string;
  is_active: boolean;
  status: 'active' | 'inactive' | 'error';
  options: Record<string, unknown>;
  webhook_token: string;
  webhook_url: string;
  credentials_status: {
    verify_token: string;
    has_app_secret: boolean;
    has_access_token: boolean;
    has_api_key: boolean;
  };
  total_leads_received: number;
  last_received_at: string | null;
  error_message: string;
}

export interface WebhookLog {
  id: string;
  source: string;
  source_display: string;
  processed: boolean;
  leads_created: number;
  leads_updated: number;
  error: string;
  created_at: string;
}

// ---- Plans ----
export interface Plan {
  id: number;
  name: string;
  slug: string;
  description: string;
  price_monthly: string;
  price_yearly: string;
  yearly_savings_percent: number;
  max_agents: number;
  max_leads: number;
  max_leads_per_day: number;
  max_whatsapp_bulk_per_day: number;
  max_email_bulk_per_day: number;
  max_sms_per_day: number;
  storage_gb: number;
  custom_fields_limit: number;
  data_retention_days: number;
  features: Array<{ feature_key: string; feature_label: string; is_enabled: boolean }>;
}

// ---- Pagination ----
export interface PaginatedResponse<T> {
  count: number;
  total_pages: number;
  current_page: number;
  page_size: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ---- Daily Activity ----
export interface DailyActivity {
  date: string;
  leads: { new_today: number; overdue_followups: number };
  calls: { total: number; connected: number; total_duration_seconds: number };
  followups: { due_today: number; completed_today: number };
}

// ---- Call Queue ----
export type QueueOrderBy = 'priority' | 'oldest' | 'newest' | 'score' | 'followup_due';
export type QueueMode = 'manual' | 'auto';

export interface CallQueue {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  filter_statuses: string[];
  filter_priorities: string[];
  filter_sources: string[];
  filter_tags: string[];
  only_unworked: boolean;
  only_followup_due: boolean;
  exclude_dnd: boolean;
  order_by: QueueOrderBy;
  mode: QueueMode;
  redial_cooldown_hours: number;
  lock_ttl_minutes: number;
  agents: { id: number; name: string; role: string }[];
  created_by_name: string | null;
  created_at: string;
}
