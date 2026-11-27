// ============================================================
// DialSathi — API Layer
// Every backend endpoint mapped with correct URLs
// ============================================================
import apiClient, { clearAuth, setAuth } from './client';
import type {
  Agent, BillingOverview, BulkCampaign, CallDisposition, CallInsight, CallLog, CallStats,
  CustomField, DailyActivity, FollowUp, IntegrationConfig,
  Lead, LeadBatch, LeadImportJob, LeadNote, LeadStats, LoginResponse,
  PaginatedResponse, Plan, Team, WebhookLog, WhatsAppTemplate,
  AgentPerformanceReport, CallAnalyticsReport, ConversionFunnelReport, AgentOutcomeReport,
  // HRMS add-on
  Attendance, Employee, ExpenseClaim, Holiday, IncentiveEarning,
  IncentiveRuleConfig, LeaveBalance, LeaveRequest, LeaveTypeConfig,
  Payslip, SalaryStructureConfig,
  // ERP add-on
  ErpCustomer, ErpInvoice, ErpProduct, ErpQuotation, ErpSalesOrder,
  // Recruitment add-on
  Application, ApplicationActivity, Candidate, Interview, InterviewFeedback,
  JobOpening, Offer, PipelineStage,
} from '../types';

// ============================================================
// AUTH  /api/v1/auth/
// ============================================================
export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post<LoginResponse>('/auth/login/', { email, password }),

  logout: (refresh: string) =>
    apiClient.post('/auth/logout/', { refresh }),

  refresh: (refresh: string) =>
    apiClient.post<{ access: string; refresh: string }>('/auth/refresh/', { refresh }),

  me: () => apiClient.get<Agent>('/auth/me/'),

  // The tenant's own billing identity, for letterheads on invoices,
  // quotations and payslips. Separate from the public tenant-info endpoint,
  // which deliberately withholds the address, GSTIN and contact details.
  company: () => apiClient.get('/auth/company/'),
  /** Admin: the name, GSTIN, state and address printed on every document. */
  updateCompany: (data: { company_name?: string; gstin?: string; state?: string;
                          billing_address?: string; city?: string; pincode?: string }) =>
    apiClient.patch('/auth/company/', data),

  updateMe: (data: Partial<Agent>) => apiClient.patch<Agent>('/auth/me/', data),

  changePassword: (old_password: string, new_password: string, confirm_password: string) =>
    apiClient.post('/auth/change-password/', { old_password, new_password, confirm_password }),

  // Agents (Admin only)
  listAgents: (params?: Record<string, string | number>) =>
    apiClient.get<PaginatedResponse<Agent>>('/auth/agents/', { params }),

  createAgent: (data: Record<string, unknown>) =>
    apiClient.post<Agent>('/auth/agents/', data),

  getAgent: (id: number) => apiClient.get<Agent>(`/auth/agents/${id}/`),

  updateAgent: (id: number, data: Partial<Agent>) =>
    apiClient.patch<Agent>(`/auth/agents/${id}/`, data),

  deleteAgent: (id: number) => apiClient.delete(`/auth/agents/${id}/`),

  reactivateAgent: (id: number) => apiClient.post<Agent>(`/auth/agents/${id}/reactivate/`),

  setAgentPassword: (id: number, new_password: string, confirm_password: string, require_change_on_login = false) =>
    apiClient.post(`/auth/agents/${id}/set-password/`, { new_password, confirm_password, require_change_on_login }),

  // Teams
  listTeams: (params?: { include_inactive?: boolean }) =>
    apiClient.get<PaginatedResponse<Team>>('/auth/teams/', { params }),
  createTeam: (data: { name: string; description?: string }) =>
    apiClient.post<Team>('/auth/teams/', data),
  updateTeam: (id: number, data: { name?: string; description?: string; is_active?: boolean }) =>
    apiClient.patch<Team>(`/auth/teams/${id}/`, data),
  /** Disbands the team; memberships are kept so it can be brought back. */
  disbandTeam: (id: number) => apiClient.delete(`/auth/teams/${id}/`),
  /** Adds the agent, or updates their team-lead flag if already a member. */
  addTeamMember: (teamId: number, agent_id: number, is_team_lead = false) =>
    apiClient.post<Team>(`/auth/teams/${teamId}/members/`, { agent_id, is_team_lead }),
  removeTeamMember: (teamId: number, agentId: number) =>
    apiClient.delete<Team>(`/auth/teams/${teamId}/members/${agentId}/`),

  // ---- Notifications (always the calling agent's own) ----
  notifications: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<AppNotification>>('/auth/notifications/', { params }),

  unreadCount: () =>
    apiClient.get<{ unread: number }>('/auth/notifications/unread-count/'),

  markNotificationRead: (id: number) =>
    apiClient.post<AppNotification>(`/auth/notifications/${id}/read/`),

  markAllNotificationsRead: () =>
    apiClient.post<{ marked_read: number }>('/auth/notifications/read-all/'),

  /** Register (or, with an empty string, unregister) this device for push. */
  registerDevice: (fcm_token: string) =>
    apiClient.post<{ registered: boolean }>('/auth/notifications/device/', { fcm_token }),

  // Live agent monitoring
  liveAgents: () =>
    apiClient.get<{ agents: LiveAgent[]; server_time: string }>('/auth/live-agents/'),

  // Effective plan features + add-on modules (drives UI gating)
  features: () => apiClient.get<TenantFeatures>('/auth/features/'),

  /** Company setting: may agents and read-only users sign in on the web? (admin) */
  webAccess: () => apiClient.get<WebAccessSetting>('/auth/web-access/'),
  setWebAccess: (agent_web_access: boolean) =>
    apiClient.patch<WebAccessSetting>('/auth/web-access/', { agent_web_access }),

  // Just the role capability map. /auth/features/ already embeds it; this is
  // for refreshing permissions after a role change without re-fetching the
  // whole plan payload.
  capabilities: () =>
    apiClient.get<{ role: string | null; capabilities: Record<string, boolean> }>(
      '/auth/capabilities/',
    ),
};

/**
 * One notification. The same object arrives over the WebSocket and from the
 * REST endpoint — the server builds both from one serializer — so a live
 * frame and a page load parse identically.
 */
export interface AppNotification {
  id: number;
  kind: 'followup_scheduled' | 'followup_due' | 'followup_overdue'
      | 'lead_assigned' | 'system' | string;
  title: string;
  body: string;
  lead_id: number | null;
  followup_id: number | null;
  /** Client route to open, e.g. /leads/42. Empty when there is nowhere to go. */
  url: string;
  is_read: boolean;
  created_at: string;
}

/** Mirrors apps/core/capabilities.py :: Workspace. */
export type Workspace = 'full' | 'agent' | 'recruiter';

/** Phone call tracking: the company switch and who it covers. */
export interface CallTrackingSetting {
  enabled: boolean;
  agents: { id: number; name: string; role: string; call_tracking_enabled: boolean }[];
}

/** The tenant's agent web sign-in switch, and whether the plan includes it at all. */
export interface WebAccessSetting {
  agent_web_access: boolean;
  available_in_plan: boolean;
}

export interface TenantFeatures {
  features: Record<string, boolean>;
  modules: Record<string, boolean>;
  plan: {
    slug: string;
    name: string;
    limits: Record<string, number>;
  } | null;
  /** The signed-in agent's role, echoed so the client never has to guess. */
  role: string | null;
  /** Role capability map — see apps/core/capabilities.py and useCapabilities(). */
  capabilities: Record<string, boolean>;
  /** Which web experience this person gets. Server-decided — see useWorkspace(). */
  workspace?: Workspace;
  /** False → this person may not use the web app; the session signs out. */
  web_access_allowed?: boolean;
  /** Why web access was refused (plan downgraded, switch off) — shown on sign-out. */
  web_access_message?: string;
  /** What the upgrade screen shows for anything this plan does not include. */
  upgrade?: {
    features: Record<string, { label: string; plans: string[] }>;
    modules: Record<string, { label: string; plans: string[] }>;
    support: SupportContacts;
  };
}

/** Who to contact about plans and billing (platform settings; blanks are unset). */
export interface SupportContacts {
  platform_name: string;
  email: string;
  phone: string;
  whatsapp: string;
}

export interface LiveAgentTotals {
  available: number; on_call: number; wrap_up: number; break: number; online: number;
}
/** Calls, connected and talk time — counted the same on every screen
 *  (apps/calls/figures.py). Talk time is connected calls only. */
export interface AgentCallFigures {
  calls: number; connected: number; talk_seconds: number;
}
export interface LiveAgent {
  agent_id: number;
  name: string;
  email: string;
  role: string;
  status: 'offline' | 'available' | 'on_call' | 'wrap_up' | 'break';
  status_display: string;
  since: string | null;
  break_reason: string;
  last_seen: string | null;
  is_online: boolean;
  current_lead_id: number | null;
  session_started_at: string | null;
  totals: LiveAgentTotals;
  /** Today's calls, as the Calls page counts them. */
  calls?: AgentCallFigures;
}

// ============================================================
// LEADS  /api/v1/leads/
// ============================================================
export const leadsApi = {
  list: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<Lead>>('/leads/', { params }),

  create: (data: Record<string, unknown>) => apiClient.post<Lead>('/leads/', data),

  get: (id: number) => apiClient.get<Lead>(`/leads/${id}/`),

  update: (id: number, data: Partial<Lead>) =>
    apiClient.patch<Lead>(`/leads/${id}/`, data),

  delete: (id: number) => apiClient.delete(`/leads/${id}/`),

  /** Lost and Invalid need a reason; so does Converted when an agent sets it. */
  updateStatus: (id: number, status: string, reason?: string) =>
    apiClient.patch<{ id: number; status: string; status_display?: string }>(
      `/leads/${id}/status/`, { status, ...(reason ? { reason } : {}) }),

  bulkAssign: (lead_ids: number[], assigned_to: number) =>
    apiClient.post('/leads/bulk-assign/', { lead_ids, assigned_to }),

  /** Soft-deletes the ticked leads (managers and admins). */
  bulkDelete: (lead_ids: number[]) =>
    apiClient.post<{ deleted: number }>('/leads/bulk-delete/', { lead_ids }),

  distribute: (data: {
    agent_ids: number[];
    only_unassigned?: boolean;
    /** Restrict to specific consignments. Combines with the other filters. */
    batch_ids?: number[];
    method?: DistributionMethod;
    max_per_agent?: number | null;
    statuses?: string[];
    priorities?: string[];
    sources?: string[];
    search?: string;
    limit?: number | null;
  }) => apiClient.post<DistributionResult>('/leads/distribute/', data),

  // ---- Lead batches ----
  batches: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<LeadBatch>>('/leads/batches/', { params }),

  /** Only `name` and `notes` are writable — everything else is system-set. */
  updateBatch: (id: number, data: { name?: string; notes?: string }) =>
    apiClient.patch<LeadBatch>(`/leads/batches/${id}/`, data),

  /** Removes the batch record; the leads themselves are kept and detached. */
  deleteBatch: (id: number) => apiClient.delete(`/leads/batches/${id}/`),

  setBatchStatus: (id: number, status: 'open' | 'closed') =>
    apiClient.post<LeadBatch>(`/leads/batches/${id}/status/`, { status }),

  batchStats: (id: number) => apiClient.get<LeadBatchStats>(`/leads/batches/${id}/stats/`),

  /** Takes the batch's leads back from every agent (admin), so it can be assigned again. */
  unassignBatch: (id: number, only_uncalled = false) =>
    apiClient.post<{ unassigned: number; per_agent: Record<string, number>; batch: LeadBatch }>(
      `/leads/batches/${id}/unassign/`, { only_uncalled }),

  distributeBatches: (data: {
    batch_ids: number[];
    agent_ids: number[];
    method?: DistributionMethod;
    only_unassigned?: boolean;
    max_per_agent?: number | null;
    limit?: number | null;
  }) => apiClient.post<DistributionResult>('/leads/batches/distribute/', data),

  flush: (confirm: string) =>
    apiClient.post<{ deleted: number }>('/leads/flush/', { confirm }),

  unassignByAgent: (agent_id: number) =>
    apiClient.post<{ unassigned: number; agent: string }>('/leads/unassign-by-agent/', { agent_id }),

  export: (params?: Record<string, string>) =>
    apiClient.get('/leads/export/', {
      params,
      responseType: 'blob',
      headers: { Accept: 'text/csv' },
    }),

  stats: () => apiClient.get<LeadStats>('/leads/stats/'),

  pipeline: () => apiClient.get<Record<string, unknown[]>>('/leads/pipeline/'),

  // Follow-ups
  listFollowups: (leadId: number) =>
    apiClient.get<PaginatedResponse<FollowUp>>(`/leads/${leadId}/followups/`),

  createFollowup: (leadId: number, data: Record<string, unknown>) =>
    apiClient.post<FollowUp>(`/leads/${leadId}/followups/`, data),

  completeFollowup: (followupId: number, notes: string) =>
    apiClient.post(`/leads/followups/${followupId}/complete/`, { notes }),

  // Notes
  listNotes: (leadId: number) =>
    apiClient.get<PaginatedResponse<LeadNote>>(`/leads/${leadId}/notes/`),

  createNote: (leadId: number, content: string, attachment?: File) => {
    const form = new FormData();
    form.append('content', content);
    if (attachment) form.append('attachment', attachment);
    return apiClient.post<LeadNote>(`/leads/${leadId}/notes/`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  // Activities
  listActivities: (leadId: number) =>
    apiClient.get<PaginatedResponse<unknown>>(`/leads/${leadId}/activities/`),

  // Import
  previewImport: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return apiClient.post<{
      headers: string[];
      sample_rows: Record<string, string>[];
      total_rows: number;
      auto_mapping: Record<string, string>;
      available_fields: { key: string; label: string; required?: boolean }[];
    }>('/leads/import/preview/', form, { headers: { 'Content-Type': 'multipart/form-data' } });
  },

  importLeads: (file: File, options: Record<string, string>) => {
    const form = new FormData();
    form.append('file', file);
    Object.entries(options).forEach(([k, v]) => form.append(k, v));
    return apiClient.post<{ import_job_id: string; message: string; status_url: string }>(
      '/leads/import/', form, { headers: { 'Content-Type': 'multipart/form-data' } }
    );
  },

  getImportJob: (jobId: string) =>
    apiClient.get<LeadImportJob>(`/leads/import/${jobId}/`),

  // Custom fields. Read-only: they are configured per client from the
  // platform panel (Tenants -> the tenant -> Import fields), so a create
  // method here would only ever get a 405.
  listCustomFields: (params?: { include_inactive?: boolean }) =>
    apiClient.get<CustomField[]>('/leads/custom-fields/',
      { params: params?.include_inactive ? { include_inactive: 1 } : undefined }),
  createCustomField: (data: Partial<Omit<CustomField, 'id'>>) =>
    apiClient.post<CustomField>('/leads/custom-fields/', data),
  updateCustomField: (id: number, data: Partial<Omit<CustomField, 'id' | 'field_key' | 'field_type'>>) =>
    apiClient.patch<CustomField>(`/leads/custom-fields/${id}/`, data),
  deleteCustomField: (id: number) =>
    apiClient.delete(`/leads/custom-fields/${id}/`),
};

/** Mirrors apps/leads/services/distribution.py :: Method. */
export type DistributionMethod = 'round_robin' | 'equal_split' | 'least_loaded';

export const DISTRIBUTION_METHODS: Array<{
  value: DistributionMethod; label: string; hint: string;
}> = [
  { value: 'round_robin',  label: 'Round robin',
    hint: 'One at a time, in the order you picked the agents. Even split.' },
  { value: 'equal_split',  label: 'Equal split',
    hint: 'Contiguous blocks — each agent gets one continuous slice of the batch.' },
  { value: 'least_loaded', label: 'Least loaded',
    hint: 'Agents with the fewest open leads get more, so the team self-balances.' },
];

export interface DistributionResult {
  distributed: number;
  /** Leads nobody could take because every agent hit the cap. */
  unassigned: number;
  method: DistributionMethod;
  per_agent: Record<string, number>;
  per_agent_id: Record<number, number>;
  batches?: string[];
  message?: string;
}

export interface LeadBatchStats {
  batch: LeadBatch;
  total: number;
  unassigned: number;
  by_agent: Array<{ agent_id: number; name: string; leads: number }>;
  by_status: Record<string, number>;
}

// ============================================================
// CALL QUEUES  /api/v1/leads/queues/
// ============================================================
export const queuesApi = {
  // Admin/manager CRUD
  list: () => apiClient.get<import('../types').CallQueue[]>('/leads/queues/'),

  create: (data: Record<string, unknown>) =>
    apiClient.post<import('../types').CallQueue>('/leads/queues/', data),

  update: (id: number, data: Record<string, unknown>) =>
    apiClient.patch<import('../types').CallQueue>(`/leads/queues/${id}/`, data),

  delete: (id: number) => apiClient.delete(`/leads/queues/${id}/`),

  // Agent
  available: () =>
    apiClient.get<{ id: number; name: string; description: string; mode: string; order_by: string; pending_count: number }[]>(
      '/leads/queues/available/'
    ),

  pullNext: (id: number) =>
    apiClient.post(`/leads/queues/${id}/pull/`),

  release: (lead_id: number, mark_dialed = false) =>
    apiClient.post('/leads/queues/release/', { lead_id, mark_dialed }),
};

// ============================================================
// CALLS  /api/v1/calls/
// ============================================================
export const callsApi = {
  list: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<CallLog>>('/calls/', { params }),

  get: (id: string) => apiClient.get<CallLog>(`/calls/${id}/`),

  create: (data: Record<string, unknown>) => apiClient.post<CallLog>('/calls/', data),

  clickToCall: (lead_id: number, phone_number?: string) =>
    apiClient.post('/calls/click-to-call/', { lead_id, phone_number }),

  // include_inactive is for the settings screen: agents must only ever be
  // offered outcomes that are switched on, but an admin has to see the ones
  // that are off to switch them back on.
  dispositions: (params?: { include_inactive?: boolean; category?: 'connected' | 'not_connected' }) =>
    apiClient.get<CallDisposition[]>('/calls/dispositions/', { params }),

  /** Phone call tracking: the company switch and each agent's own (admin). */
  tracking: () => apiClient.get<CallTrackingSetting>('/calls/tracking/'),
  setTracking: (data: { enabled?: boolean; agents?: Record<string, boolean> }) =>
    apiClient.patch<CallTrackingSetting>('/calls/tracking/', data),

  /** Set the outcome of a call saved without one (click-to-call, Call back). */
  setOutcome: (id: string, data: { disposition: number; is_connected?: boolean; duration_seconds?: number; notes?: string; followup_at?: string }) =>
    apiClient.patch<CallLog>(`/calls/${id}/outcome/`, data),

  createDisposition: (data: Partial<CallDisposition>) =>
    apiClient.post<CallDisposition>('/calls/dispositions/', data),

  updateDisposition: (id: number, data: Partial<CallDisposition>) =>
    apiClient.patch<CallDisposition>(`/calls/dispositions/${id}/`, data),

  // 204 when it was never used; 200 with {deactivated, detail} when calls
  // carry it and it was switched off instead, to keep their history.
  deleteDisposition: (id: number) =>
    apiClient.delete<{ deactivated?: boolean; detail?: string }>(`/calls/dispositions/${id}/`),

  // Takes the list's filters too, so the boxes describe the calls listed.
  stats: (params?: Record<string, string | undefined>) =>
    apiClient.get<CallStats>('/calls/stats/', { params }),
};

// ============================================================
// WORKFLOWS  /api/v1/automation/
// ============================================================
export type WorkflowTrigger =
  | 'lead_created' | 'lead_status_changed' | 'lead_assigned'
  | 'call_connected' | 'call_not_connected' | 'call_outcome'
  | 'whatsapp_received' | 'followup_missed' | 'lead_inactive';

export type WorkflowStepType =
  | 'wait' | 'send_whatsapp' | 'send_sms' | 'assign' | 'change_status'
  | 'create_followup' | 'add_note' | 'notify' | 'webhook';

/** One step. Which keys apply depends on `type` (validated server-side). */
export interface WorkflowStep {
  type: WorkflowStepType;
  // wait
  amount?: number; unit?: 'minutes' | 'hours' | 'days';
  // send_whatsapp
  template?: number | null; message?: string; account?: number | null;
  // send_sms
  sender_id?: string;
  // assign
  agents?: number[]; mode?: 'fixed' | 'round_robin'; only_if_unassigned?: boolean;
  // change_status
  status?: string;
  // create_followup
  in_hours?: number; note?: string; followup_type?: string;
  // add_note
  text?: string;
  // notify
  to?: 'owner' | 'agent'; agent?: number;
  // webhook
  url?: string;
  // guards
  only_if_no_reply?: boolean;
  only_if_status_in?: string[];
}

export interface WorkflowConditions {
  sources?: string[]; statuses?: string[]; batches?: number[];
  assigned_to?: number[]; cities?: string[]; tags?: string[];
}

export interface Workflow {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  trigger: WorkflowTrigger;
  trigger_label: string;
  trigger_config: Record<string, unknown>;
  conditions: WorkflowConditions;
  steps: WorkflowStep[];
  /** false = a lead goes through it once; true = every matching event. */
  repeat: boolean;
  quiet_hours_enabled: boolean;
  quiet_start: string;
  quiet_end: string;
  runs_count: number;
  last_run_at: string | null;
  open_runs: number;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export type WorkflowInput = Omit<Workflow,
  'id' | 'trigger_label' | 'runs_count' | 'last_run_at' | 'open_runs' | 'created_by_name' | 'created_at' | 'updated_at'>;

export interface WorkflowRunLogEntry {
  step: number; type: string;
  result: 'done' | 'skipped' | 'failed' | 'waiting';
  detail: string; at: string;
}

export interface WorkflowRun {
  id: number;
  workflow: number; workflow_name: string;
  lead: number; lead_name: string; lead_phone: string;
  trigger: string;
  context: Record<string, unknown>;
  status: 'pending' | 'waiting' | 'completed' | 'cancelled' | 'failed';
  current_step: number; total_steps: number;
  next_run_at: string | null; finished_at: string | null;
  log: WorkflowRunLogEntry[];
  has_errors: boolean; error: string;
  created_at: string;
}

export interface WorkflowOptions {
  triggers: Array<{ key: WorkflowTrigger; label: string; description: string; scanned: boolean }>;
  actions: Array<{ key: WorkflowStepType; label: string }>;
  statuses: Array<{ key: string; label: string }>;
  sources: Array<{ key: string; label: string }>;
  followup_types: Array<{ key: string; label: string }>;
  dispositions: Array<{ id: number; name: string; category: string }>;
  agents: Array<{ id: number; name: string; role: string }>;
  batches: Array<{ id: number; name: string }>;
  templates: Array<{ id: number; name: string; status: string; body_text: string;
                     account: number | null; account_label: string | null; unmapped: number[] }>;
  whatsapp_numbers: Array<{ id: number; label: string; display_phone: string; is_default: boolean; is_active: boolean }>;
  placeholders: string[];
}

export const automationApi = {
  list: () => apiClient.get<Workflow[]>('/automation/workflows/'),
  get: (id: number) => apiClient.get<Workflow>(`/automation/workflows/${id}/`),
  create: (data: Partial<WorkflowInput>) => apiClient.post<Workflow>('/automation/workflows/', data),
  update: (id: number, data: Partial<WorkflowInput>) =>
    apiClient.patch<Workflow>(`/automation/workflows/${id}/`, data),
  remove: (id: number) => apiClient.delete(`/automation/workflows/${id}/`),
  toggle: (id: number, is_active: boolean) =>
    apiClient.post<Workflow>(`/automation/workflows/${id}/toggle/`, { is_active }),
  duplicate: (id: number) => apiClient.post<Workflow>(`/automation/workflows/${id}/duplicate/`),
  /** Run the steps on one lead now (ignores trigger and conditions). */
  runOn: (id: number, lead_id: number) =>
    apiClient.post<WorkflowRun>(`/automation/workflows/${id}/run/`, { lead_id }),
  runs: (params: { workflow?: number; lead?: number; status?: string; errors?: boolean; page?: number }) =>
    apiClient.get<PaginatedResponse<WorkflowRun>>('/automation/runs/', { params }),
  cancelRun: (id: number) => apiClient.post<WorkflowRun>(`/automation/runs/${id}/cancel/`),
  options: () => apiClient.get<WorkflowOptions>('/automation/options/'),
};

// ============================================================
// BILLING  /api/v1/billing/
// ============================================================
export const billingApi = {
  /** The tenant's own plan, usage, invoices and support contacts (admin only). */
  overview: () => apiClient.get<BillingOverview>('/billing/'),
};

// ============================================================
// COMMUNICATIONS  /api/v1/comms/
// ============================================================
export const commsApi = {
  // WhatsApp provider connection (admin)
  getWhatsAppConfig: () => apiClient.get<WhatsAppConfig>('/comms/whatsapp/config/'),
  saveWhatsAppConfig: (data: WhatsAppConfigUpdate) =>
    apiClient.put<WhatsAppConfig>('/comms/whatsapp/config/', data),
  testWhatsAppConfig: (phone: string, message?: string) =>
    apiClient.post<WhatsAppConfigTestResult>('/comms/whatsapp/config/test/', { phone, message }),

  // ---- Inbound / Meta Click-to-WhatsApp ----
  // Mints a fresh webhook verify token and returns it ONCE. Rotating breaks
  // verification until Meta's webhook config is updated with the new value.
  rotateWebhookVerifyToken: () =>
    apiClient.post<WhatsAppVerifyTokenResult>('/comms/whatsapp/webhook-token/'),

  // ---- Several WhatsApp numbers (admin). The config methods above act on
  // the default one. ----
  listWhatsAppAccounts: () =>
    apiClient.get<WhatsAppAccountList>('/comms/whatsapp/accounts/'),
  getWhatsAppAccount: (id: number) =>
    apiClient.get<WhatsAppConfig>(`/comms/whatsapp/accounts/${id}/`),
  /** `copy_credentials_from`: another number of the same Meta WhatsApp
   *  Business Account — its token, app secret and webhook settings are
   *  reused, so only the new number's Phone number ID is needed. */
  createWhatsAppAccount: (data: WhatsAppConfigUpdate & { label: string; copy_credentials_from?: number }) =>
    apiClient.post<WhatsAppConfig>('/comms/whatsapp/accounts/', data),
  /** Every number in this number's Meta WhatsApp Business Account (read from Meta). */
  listMetaBusinessNumbers: (id: number) =>
    apiClient.get<{ business_account_id: string; numbers: MetaBusinessNumber[] }>(
      `/comms/whatsapp/accounts/${id}/meta-numbers/`),
  updateWhatsAppAccount: (id: number, data: WhatsAppConfigUpdate) =>
    apiClient.patch<WhatsAppConfig>(`/comms/whatsapp/accounts/${id}/`, data),
  deleteWhatsAppAccount: (id: number) =>
    apiClient.delete(`/comms/whatsapp/accounts/${id}/`),
  testWhatsAppAccount: (id: number, phone: string, message?: string) =>
    apiClient.post<WhatsAppConfigTestResult>(`/comms/whatsapp/accounts/${id}/test/`, { phone, message }),
  makeDefaultWhatsAppAccount: (id: number) =>
    apiClient.post<WhatsAppConfig>(`/comms/whatsapp/accounts/${id}/make-default/`),
  rotateAccountVerifyToken: (id: number) =>
    apiClient.post<WhatsAppVerifyTokenResult>(`/comms/whatsapp/accounts/${id}/webhook-token/`),
  /** Numbers any agent can send from (for "Send from" pickers). */
  listWhatsAppSenders: () =>
    apiClient.get<WhatsAppSender[]>('/comms/whatsapp/senders/'),

  // WhatsApp threads with their Meta ad attribution.
  listConversations: (params?: { lead?: number; ad_referred?: boolean; campaign_id?: string }) =>
    apiClient.get<PaginatedResponse<WhatsAppConversation>>('/comms/whatsapp/conversations/', { params }),

  // WhatsApp templates
  /** `account`: only templates that number can send (its own + shared ones). */
  listTemplates: (approvedOnly?: boolean, account?: number | null) =>
    apiClient.get<WhatsAppTemplate[]>('/comms/whatsapp/templates/', {
      params: {
        ...(approvedOnly ? { approved_only: true } : {}),
        ...(account ? { account } : {}),
      },
    }),

  createTemplate: (data: Partial<WhatsAppTemplate>) =>
    apiClient.post<WhatsAppTemplate>('/comms/whatsapp/templates/', data),

  /** Edit a template, or record the approval Meta gave it (admin only).
   *  Nothing else can move a template off "pending", and a bulk campaign
   *  only accepts approved templates. */
  updateTemplate: (id: number, data: Partial<WhatsAppTemplate>) =>
    apiClient.patch<WhatsAppTemplate>(`/comms/whatsapp/templates/${id}/`, data),

  /** Switches the template off; past campaigns keep pointing at it. */
  deleteTemplate: (id: number) => apiClient.delete(`/comms/whatsapp/templates/${id}/`),

  uploadTemplateMedia: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return apiClient.post<{ url: string; public_id: string }>('/comms/template-media/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  // ---- WhatsApp inbox: leads who have written in ----
  inbox: (params?: InboxFilters & { page?: number }) =>
    apiClient.get<PaginatedResponse<InboxConversation>>('/comms/whatsapp/inbox/', { params }),
  inboxSummary: () => apiClient.get<InboxSummary>('/comms/whatsapp/inbox/summary/'),
  inboxThread: (leadId: number) => apiClient.get<InboxThread>(`/comms/whatsapp/inbox/${leadId}/`),
  /** The thread is on screen: clears its unread messages for the whole team. */
  inboxMarkRead: (leadId: number) =>
    apiClient.post<InboxSummary & { cleared: number }>(`/comms/whatsapp/inbox/${leadId}/read/`),

  // WhatsApp messages thread
  listMessages: (leadId: number) =>
    apiClient.get<PaginatedResponse<unknown>>('/comms/whatsapp/messages/', {
      params: { lead: leadId },
    }),

  // (see WhatsApp config methods at top of commsApi)

  // Send single WhatsApp
  /** `account_id`: the number to send from; omitted → the template's number,
   *  the number the lead last wrote to, or the default. */
  sendWhatsApp: (lead_id: number, message: string, template_id?: number, account_id?: number | null) =>
    apiClient.post<{ message: string; lead: string; sent_from: string | null }>(
      '/comms/whatsapp/send/', { lead_id, message, template_id, account_id: account_id ?? undefined }),

  // Send single SMS
  sendSMS: (lead_id: number, message: string, sender_id?: string) =>
    apiClient.post('/comms/sms/send/', { lead_id, message, sender_id }),

  // Campaigns
  listCampaigns: (params?: Record<string, string>) =>
    apiClient.get<PaginatedResponse<BulkCampaign>>('/comms/campaigns/', { params }),

  createCampaign: (data: Record<string, unknown>) =>
    apiClient.post<BulkCampaign>('/comms/campaigns/', data),

  /** How many leads a set of filters reaches, before the campaign exists.
   *  Runs the same resolver the send uses, so the two cannot disagree. */
  previewAudience: (audience_filters: Record<string, unknown>) =>
    apiClient.post<{ count: number; with_phone: number; with_email: number; dnd?: number }>(
      '/comms/campaigns/preview-audience/', { audience_filters },
    ),

  getCampaign: (id: string) => apiClient.get<BulkCampaign>(`/comms/campaigns/${id}/`),

  /** Who a campaign went to and what happened to each message. */
  campaignRecipients: (id: string, params?: { status?: string; page?: number }) =>
    apiClient.get<PaginatedResponse<CampaignRecipientRow>>(`/comms/campaigns/${id}/recipients/`, { params }),

  launchCampaign: (id: string) =>
    apiClient.post<{ message: string; id: string }>(`/comms/campaigns/${id}/launch/`),

  pauseCampaign: (id: string) =>
    apiClient.post<{ message: string }>(`/comms/campaigns/${id}/pause/`),
};

// ============================================================
// REPORTS  /api/v1/reports/
// ============================================================
export const reportsApi = {
  /** The signed-in person's own numbers. Takes no agent id — it cannot be asked for anyone else's. */
  myPerformance: (days: 1 | 7 | 30 = 7) =>
    apiClient.get<MyPerformance>('/reports/my-performance/', { params: { days } }),

  agentPerformance: (params?: { date_from?: string; date_to?: string; agent_id?: string }) =>
    apiClient.get<AgentPerformanceReport>('/reports/agent-performance/', { params }),

  leadSources: (params?: { date_from?: string; date_to?: string }) =>
    apiClient.get<{ period: unknown; by_source: unknown[] }>('/reports/lead-sources/', { params }),

  callAnalytics: (params?: { date_from?: string; date_to?: string }) =>
    apiClient.get<CallAnalyticsReport>('/reports/call-analytics/', { params }),

  /** current: true → every lead where it stands now, ignoring dates. */
  conversionFunnel: (params?: { date_from?: string; date_to?: string; current?: boolean }) =>
    apiClient.get<ConversionFunnelReport>('/reports/conversion-funnel/', { params }),

  dailyActivity: () => apiClient.get<DailyActivity>('/reports/daily-activity/'),

  /** Each agent's calls by outcome — credited to the agent who called. */
  agentOutcomes: (params?: { date_from?: string; date_to?: string }) =>
    apiClient.get<AgentOutcomeReport>('/reports/agent-outcomes/', { params }),

  // Every agent's day: first online, last seen, and the time split.
  agentLogin: (params: { date_from: string; date_to: string }) =>
    apiClient.get<{ date_from: string; date_to: string; generated_at: string; rows: AgentLoginRow[] }>(
      '/reports/agent-login/', { params }),

  agentLoginCsv: (params: { date_from: string; date_to: string }) =>
    apiClient.get('/reports/agent-login/', {
      params: { ...params, format: 'csv' }, responseType: 'blob', headers: { Accept: 'text/csv' },
    }),
};

/** One agent's day in the login report (apps/reports/login_report.py). */
export interface AgentLoginRow {
  date: string;
  agent_id: number;
  name: string;
  role: string;
  /** False for an agent deactivated since — kept so their past days still show. */
  is_active?: boolean;
  /** First sign-in that day on any client (web or app). */
  first_sign_in?: string | null;
  status_now: string | null;
  online_now: boolean;
  first_online: string | null;
  last_seen: string | null;
  online_seconds: number;
  available_seconds: number;
  on_call_seconds: number;
  wrap_up_seconds: number;
  break_seconds: number;
  break_count: number;
  break_reasons: string;
  calls: number;
  connected_calls: number;
  /** Connected calls' durations — the Calls page's talk time. */
  talk_seconds: number;
  occupancy: number;
}

// ============================================================
// INTEGRATIONS  /api/v1/integrations/
// ============================================================
export const integrationsApi = {
  listConfigs: () =>
    apiClient.get<IntegrationConfig[]>('/integrations/configs/'),

  createConfig: (data: Partial<IntegrationConfig>) =>
    apiClient.post<IntegrationConfig>('/integrations/configs/', data),

  updateConfig: (id: number, data: Partial<IntegrationConfig>) =>
    apiClient.patch<IntegrationConfig>(`/integrations/configs/${id}/`, data),

  deleteConfig: (id: number) => apiClient.delete(`/integrations/configs/${id}/`),

  listLogs: (source?: string) =>
    apiClient.get<WebhookLog[]>('/integrations/logs/', {
      params: source ? { source } : undefined,
    }),

  metaForms: (configId: number) =>
    apiClient.get<{ forms: Array<{ id: string; name: string; status: string; fields: Array<{ key: string; label: string }> }> }>(
      '/integrations/meta/forms/',
      { params: { config_id: configId } },
    ),

  syncMeta: () =>
    apiClient.post<{ created: number; skipped: number; failed: number; seen: number; forms: number; message: string }>(
      '/integrations/meta/sync/'
    ),

  // ---- "Continue with Facebook" (Lead Ads through the platform's Meta app)
  metaConnectStatus: () =>
    apiClient.get<MetaConnectStatus>('/integrations/meta/connect/'),
  /** The Facebook login URL to open in a popup. */
  metaConnectStart: () =>
    apiClient.post<{ url: string }>('/integrations/meta/connect/start/'),
  metaPageAction: (pageId: string, action: 'connect' | 'disconnect' | 'refresh-forms') =>
    apiClient.post<MetaLeadPage>(`/integrations/meta/connect/pages/${pageId}/${action}/`),
  metaPageUpdate: (pageId: string, data: { auto_add_new_forms: boolean }) =>
    apiClient.patch<MetaLeadPage>(`/integrations/meta/connect/pages/${pageId}/`, data),
  metaFormUpdate: (formId: string, data: Partial<Pick<MetaLeadForm, 'enabled' | 'assign_mode' | 'assign_agent' | 'assign_team'>>) =>
    apiClient.patch<MetaLeadForm>(`/integrations/meta/connect/forms/${formId}/`, data),
  /** Import recent leads now (all connected Pages). */
  metaFetchNow: (days = 2) =>
    apiClient.post<{ created: number; duplicate: number; failed: number; message: string }>(
      '/integrations/meta/connect/fetch/', { days }),
};

export interface MetaLeadForm {
  form_id: string;
  name: string;
  status: string;
  enabled: boolean;
  assign_mode: 'default' | 'agent' | 'team';
  assign_agent: number | null;
  assign_agent_name: string | null;
  assign_team: number | null;
  assign_team_name: string | null;
  leads_received: number;
  last_lead_at: string | null;
}

export interface MetaLeadPage {
  page_id: string;
  name: string;
  picture_url: string;
  connected: boolean;
  /** Routed to a different workspace — cannot be connected here. */
  connected_elsewhere: boolean;
  has_token: boolean;
  auto_add_new_forms: boolean;
  leads_received: number;
  last_lead_at: string | null;
  last_polled_at: string | null;
  last_error: string;
  forms: MetaLeadForm[];
}

export interface MetaConnectStatus {
  /** The platform Meta app is configured on the server. */
  available: boolean;
  signed_in: boolean;
  signed_in_as: string;
  signed_in_at: string | null;
  missing_permissions: string[];
  integration_active: boolean;
  pages: MetaLeadPage[];
}

export type WhatsAppProviderSlug =
  | 'meta_cloud' | 'interakt' | 'aisensy' | 'wati' | 'gupshup' | 'twilio' | '360dialog';

export interface WhatsAppConfig {
  /** One WhatsApp account (number). A workspace can have several. */
  id: number;
  /** "Sales", "Support" — shown when choosing a sender. */
  label: string;
  /** The number customers see, e.g. +91 98765 43210. */
  display_phone: string;
  /** Meta's id for the number (copied from the credentials; not secret). */
  phone_number_id: string;
  /** The Meta WhatsApp Business Account it belongs to. Numbers in one
   *  account share its templates. */
  business_account_id: string;
  /** Sends from this number unless another is chosen. */
  is_default: boolean;
  provider: WhatsAppProviderSlug;
  is_active: boolean;
  default_language: string;
  /** Non-secret values verbatim; secrets shown as "••••••••" when set. */
  configured_fields: Record<string, string>;
  /** Credential keys this provider needs, in form order. */
  required_fields: string[];
  last_verified_at: string | null;
  last_error: string;
  updated_at: string;

  // ---- Inbound / Meta Click-to-WhatsApp ----
  /** Master switch for receiving. Separate from is_active, which is about sending. */
  inbound_enabled: boolean;
  create_leads_from_inbound: boolean;
  /** Only open leads for ad-referred conversations; ignore organic inbound. */
  ctwa_leads_only: boolean;
  inbound_assign_to: number | null;
  reopen_lead_on_inbound: boolean;
  /** Blank = use the platform default. */
  graph_api_version: string;

  // ---- Inbound health ----
  last_webhook_at: string | null;
  last_webhook_error: string;
  total_inbound_messages: number;

  webhook: WhatsAppWebhookInfo;

  /** Agents who send from this number. An agent given numbers can send only
   *  from those; an agent with none can use any. */
  agents: number[];
  agent_names: Array<{ id: number; name: string }>;
}

/** Everything needed to finish the Meta side. Contains no secret values. */
export interface WhatsAppWebhookInfo {
  /** Paste into Meta → WhatsApp → Configuration → Callback URL. */
  callback_url: string;
  /** Give to a BSP (Interakt, WATI, Gupshup…) for delivery statuses and replies. Carries the tenant's secret token. */
  status_url: string;
  https: boolean;
  verify_token_set: boolean;
  app_secret_set: boolean;
  access_token_set: boolean;
  ads_token_set: boolean;
  graph_api_version: string;
  /** Webhook fields to subscribe to in Meta. */
  subscribe_fields: string[];
  signature_enforced: boolean;
}

export interface WhatsAppConfigUpdate {
  provider?: WhatsAppProviderSlug;
  /** Agent ids who send from this number (replaces the list). */
  agents?: number[];
  label?: string;
  display_phone?: string;
  default_language?: string;
  /** Only the keys the admin actually typed; blanks/masked values are ignored server-side. */
  credentials?: Record<string, string>;
  inbound_enabled?: boolean;
  create_leads_from_inbound?: boolean;
  ctwa_leads_only?: boolean;
  inbound_assign_to?: number | null;
  reopen_lead_on_inbound?: boolean;
  graph_api_version?: string;
}

/** GET /comms/whatsapp/accounts/ — every connected number (admin). */
export interface WhatsAppAccountList {
  results: WhatsAppConfig[];
  /** False when another number needs the "Multiple WhatsApp numbers" plan feature. */
  can_add: boolean;
}

/** One phone number in a Meta WhatsApp Business Account, as Meta lists it. */
export interface MetaBusinessNumber {
  phone_number_id: string;
  display_phone: string;
  verified_name: string;
  quality_rating: string;
  status: string;
  /** The name it is connected under here, or null if it isn't yet. */
  connected_as: string | null;
}

/** A number an agent can send from — names only, never credentials. */
// ---- WhatsApp inbox ----
export interface InboxFilters {
  unread?: boolean; mine?: boolean; unassigned?: boolean;
  agent?: number; account?: number; q?: string;
}

/** Whether free text may still be sent (Meta's 24-hour customer window). */
export interface ReplyWindow { open: boolean; closes_at: string | null }

export interface InboxConversation {
  lead_id: number;
  lead_name: string;
  phone: string;
  status: string;
  owner_id: number | null;
  owner_name: string | null;
  unread: number;
  last_message: {
    text: string; direction: 'inbound' | 'outbound'; type: string; status: string;
    at: string; account_id: number | null; account_label: string | null;
  };
  last_inbound_at: string | null;
  window: ReplyWindow;
}

export interface InboxMessage {
  id: string;
  direction: 'inbound' | 'outbound';
  message_type: string;
  content: string;
  template_name: string | null;
  status: string;
  sent_by_name: string | null;
  sent_at: string | null;
  created_at: string;
  error_message: string;
  account: number | null;
  account_label: string | null;
  media_url: string;
}

export interface InboxThread {
  lead: { id: number; name: string; phone: string; status: string; source: string; city: string;
          owner_id: number | null; owner_name: string | null };
  window: ReplyWindow;
  unread: number;
  last_account_id: number | null;
  last_account_label: string | null;
  messages: InboxMessage[];
}

export interface InboxSummary { unread_conversations: number; unread_messages: number }

export interface WhatsAppSender {
  id: number;
  label: string;
  display_phone: string;
  is_default: boolean;
  is_active: boolean;
  provider: string;
  /** The number this user's picker starts on: their own number if an admin
   *  assigned them one, else the company default. */
  preferred?: boolean;
}

/** " (yours)" for the number an admin gave this agent, " (default)" for the
 *  company default, else nothing — the suffix shown in "Send from" pickers. */
export function senderSuffix(s: Pick<WhatsAppSender, 'is_default' | 'preferred'>): string {
  if (s.preferred && !s.is_default) return ' (yours)';
  return s.is_default ? ' (default)' : '';
}

/** "Sales (+91 98765 43210)" */
export function senderLabel(s: Pick<WhatsAppSender, 'label' | 'display_phone'>): string {
  return s.display_phone ? `${s.label} (${s.display_phone})` : s.label;
}

/** Returned exactly once by rotateVerifyToken — it is never readable again. */
export interface WhatsAppVerifyTokenResult {
  verify_token: string;
  rotated: boolean;
  message: string;
}

/**
 * Meta ad attribution for a Click-to-WhatsApp conversation.
 *
 * Every key is optional and that is load-bearing: Meta's webhook carries the
 * ad id but never the campaign/ad-set/ad NAMES — those need a Marketing API
 * lookup requiring `ads_read`. Keys the backend could not fill are OMITTED
 * rather than sent empty, so render what is present instead of destructuring
 * a fixed shape.
 */
export interface CtwaAttribution {
  source_type?: string;
  source_id?: string;
  source_url?: string;
  headline?: string;
  body?: string;
  media_type?: string;
  ctwa_clid?: string;
  ad_id?: string;
  ad_name?: string;
  adset_id?: string;
  adset_name?: string;
  campaign_id?: string;
  campaign_name?: string;
}

export interface WhatsAppConversation {
  id: string;
  lead: number;
  channel: string;
  status: 'open' | 'closed';
  status_display: string;
  contact_wa_id: string;
  contact_phone: string;
  whatsapp_profile_name: string;
  business_display_phone: string;
  business_phone_number_id: string;
  is_ad_referred: boolean;
  attribution: CtwaAttribution;
  first_message: string;
  first_message_at: string | null;
  last_message_at: string | null;
  message_count: number;
  created_at: string;
}

export interface WhatsAppConfigTestResult {
  ok: boolean;
  provider_message_id?: string;
  sent_to?: string;
  error?: string;
  message?: string;
}

// ============================================================
// AI SUITE  /api/v1/ai/     (add-on module: ai_suite)
// ============================================================
export const aiApi = {
  transcript: (callId: string) =>
    apiClient.get<CallTranscript>(`/ai/calls/${callId}/transcript/`),

  transcribe: (callId: string) => apiClient.post(`/ai/calls/${callId}/transcribe/`),

  insight: (callId: string) => apiClient.get<CallInsight>(`/ai/calls/${callId}/insight/`),

  analyse: (callId: string) => apiClient.post(`/ai/calls/${callId}/analyse/`),

  insights: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<CallInsight>>('/ai/insights/', { params }),

  backfill: (limit: number) => apiClient.post('/ai/backfill/', { limit }),

  usage: () => apiClient.get<AIUsage>('/ai/usage/'),
};

export interface CallTranscript {
  call: string;
  transcript: string;
  transcript_status: string;
  transcript_language: string;
  transcript_provider: string;
  transcript_error: string;
  transcribed_at: string | null;
  duration_seconds: number;
}

export interface AIUsage {
  calls_analysed: number;
  input_tokens: number;
  output_tokens: number;
  calls_transcribed: number;
  audio_seconds: number;
  failed_insights: number;
  /** Whether the server has GEMINI_API_KEY (nothing is summarised without it). */
  gemini_configured?: boolean;
  /** Recordings not transcribed yet (waiting, running or failed). */
  recordings_waiting?: number;
  transcripts_failed?: number;
}

// ============================================================
// HRMS  /api/v1/hrms/       (add-on module: hrms)
// ============================================================
export const hrmsApi = {
  me: () => apiClient.get<Employee>('/hrms/me/'),

  employees: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<Employee>>('/hrms/employees/', { params }),
  createEmployee: (data: Record<string, unknown>) =>
    apiClient.post<Employee>('/hrms/employees/', data),
  updateEmployee: (id: number, data: Record<string, unknown>) =>
    apiClient.patch<Employee>(`/hrms/employees/${id}/`, data),

  holidays: () => apiClient.get<Holiday[]>('/hrms/holidays/'),
  createHoliday: (data: { date: string; name: string }) =>
    apiClient.post<Holiday>('/hrms/holidays/', data),
  deleteHoliday: (id: number) => apiClient.delete(`/hrms/holidays/${id}/`),

  /** `includeInactive` (HR) also lists switched-off types so they can be switched back on. */
  leaveTypes: (includeInactive = false) =>
    apiClient.get<LeaveTypeConfig[]>('/hrms/leave-types/', {
      params: includeInactive ? { include_inactive: 1 } : undefined,
    }),
  createLeaveType: (data: Record<string, unknown>) =>
    apiClient.post<LeaveTypeConfig>('/hrms/leave-types/', data),
  updateLeaveType: (id: number, data: Record<string, unknown>) =>
    apiClient.patch<LeaveTypeConfig>(`/hrms/leave-types/${id}/`, data),
  deactivateLeaveType: (id: number) => apiClient.delete(`/hrms/leave-types/${id}/`),

  incentiveRules: () => apiClient.get<IncentiveRuleConfig[]>('/hrms/incentive-rules/'),
  createIncentiveRule: (data: Record<string, unknown>) =>
    apiClient.post<IncentiveRuleConfig>('/hrms/incentive-rules/', data),
  updateIncentiveRule: (id: number, data: Record<string, unknown>) =>
    apiClient.patch<IncentiveRuleConfig>(`/hrms/incentive-rules/${id}/`, data),
  deactivateIncentiveRule: (id: number) => apiClient.delete(`/hrms/incentive-rules/${id}/`),
  computeIncentives: (month: string) => apiClient.post('/hrms/incentives/compute/', { month }),

  salaryStructures: (employeeId?: number) =>
    apiClient.get<SalaryStructureConfig[]>('/hrms/salary-structures/', {
      params: employeeId ? { employee: employeeId } : undefined,
    }),
  createSalaryStructure: (data: Record<string, unknown>) =>
    apiClient.post<SalaryStructureConfig>('/hrms/salary-structures/', data),
  updateSalaryStructure: (id: number, data: Record<string, unknown>) =>
    apiClient.patch<SalaryStructureConfig>(`/hrms/salary-structures/${id}/`, data),
  deleteSalaryStructure: (id: number) => apiClient.delete(`/hrms/salary-structures/${id}/`),

  attendance: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<Attendance>>('/hrms/attendance/', { params }),
  updateAttendance: (id: number, data: Record<string, unknown>) =>
    apiClient.patch<Attendance>(`/hrms/attendance/${id}/`, data),
  /** HR adds a day that has no row (source = admin). */
  createAttendance: (data: Record<string, unknown>) =>
    apiClient.post<Attendance>('/hrms/attendance/', data),
  /** rows_written = rebuilt from the dialer; kept = left alone (corrected, checked in, on leave). */
  syncAttendance: (date: string) =>
    apiClient.post<{ date: string; rows_written: number; kept: number }>('/hrms/attendance/sync/', { date }),

  policy: () => apiClient.get<HrmsPolicy>('/hrms/policy/'),
  updatePolicy: (data: Partial<HrmsPolicy>) => apiClient.patch<HrmsPolicy>('/hrms/policy/', data),

  checkIn: () => apiClient.post('/hrms/attendance/check-in/'),
  checkOut: () => apiClient.post('/hrms/attendance/check-out/'),

  leave: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<LeaveRequest>>('/hrms/leave/', { params }),

  applyLeave: (data: Record<string, unknown>) => apiClient.post('/hrms/leave/', data),

  /** action: approve | reject | cancel */
  decideLeave: (id: number, action: string, note = '') =>
    apiClient.post(`/hrms/leave/${id}/${action}/`, { note }),

  leaveBalances: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<LeaveBalance[]>('/hrms/leave-balances/', { params }),
  allocateLeaveBalance: (data: Record<string, unknown>) =>
    apiClient.post<LeaveBalance>('/hrms/leave-balances/allocate/', data),
  updateLeaveBalance: (id: number, data: Record<string, unknown>) =>
    apiClient.patch<LeaveBalance>(`/hrms/leave-balances/${id}/`, data),
  deleteLeaveBalance: (id: number) => apiClient.delete(`/hrms/leave-balances/${id}/`),
  bulkAllocateLeave: (year: number) =>
    apiClient.post<{ created: number; topped_up: number; employees: number; carried_forward: number }>(
      '/hrms/leave-balances/bulk-allocate/', { year },
    ),

  expenses: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<ExpenseClaim>>('/hrms/expenses/', { params }),

  /** Multipart, because a claim may carry a receipt file. */
  createExpense: (data: FormData) =>
    apiClient.post<ExpenseClaim>('/hrms/expenses/', data, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),

  decideExpense: (id: number, action: 'approve' | 'reject', note = '') =>
    apiClient.post(`/hrms/expenses/${id}/${action}/`, { note }),

  incentives: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<IncentiveEarning>>('/hrms/incentives/', { params }),

  payslips: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<Payslip>>('/hrms/payslips/', { params }),

  payslip: (id: number) => apiClient.get<Payslip>(`/hrms/payslips/${id}/`),
  finalizePayslip: (id: number) => apiClient.post<Payslip>(`/hrms/payslips/${id}/finalize/`),
  markPayslipPaid: (id: number) => apiClient.post<Payslip>(`/hrms/payslips/${id}/mark-paid/`),
  /** Finalized → draft, to correct it. A paid slip can't be reopened. */
  reopenPayslip: (id: number) => apiClient.post<Payslip>(`/hrms/payslips/${id}/reopen/`),
  /** Drafts only; releases the slip's incentives and claims for the next run. */
  deletePayslip: (id: number) => apiClient.delete(`/hrms/payslips/${id}/`),

  /** `month` is 'YYYY-MM'. The backend parses that shape, not month/year ints. */
  runPayroll: (month: string) => apiClient.post<PayrollRunResult>('/hrms/payroll/run/', { month }),

  deleteEmployee: (id: number) => apiClient.delete(`/hrms/employees/${id}/`),

  dashboard: (month?: string) =>
    apiClient.get<HrmsDashboard>('/hrms/dashboard/', { params: month ? { month } : undefined }),
};

export interface HrmsDashboard {
  month: string;
  headcount: number;
  attendance_today: {
    present: number; absent: number; half_day: number;
    on_leave: number; not_marked: number;
  };
  pending: { leave: number; expenses: number };
  payroll: {
    payslips: number; gross: string; net: string; incentives: string;
    reimbursements?: string; deductions?: string;
  };
}

export interface HrmsPolicy {
  full_day_hours: string;
  half_day_hours: string;
  expense_max_amount: string;
  expense_receipt_above: string | null;
}

export interface PayrollRunResult {
  period: string;
  payslips: number;
  errors: string[];
  unrecorded: { employee_code: string; name: string; days: number }[];
  pending_leave: { employee_code: string; name: string; requests: number }[];
  missing_structure?: { employee_code: string; name: string; is_active: boolean }[];
  upcoming_days?: number;
}

// ============================================================
// ERP  /api/v1/erp/         (add-on module: erp_sales)
// ============================================================
export const erpApi = {
  customers: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<ErpCustomer>>('/erp/customers/', { params }),
  createCustomer: (data: Record<string, unknown>) =>
    apiClient.post<ErpCustomer>('/erp/customers/', data),
  updateCustomer: (id: number, data: Record<string, unknown>) =>
    apiClient.patch<ErpCustomer>(`/erp/customers/${id}/`, data),

  products: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<ErpProduct>>('/erp/products/', { params }),
  createProduct: (data: Record<string, unknown>) =>
    apiClient.post<ErpProduct>('/erp/products/', data),
  updateProduct: (id: number, data: Record<string, unknown>) =>
    apiClient.patch<ErpProduct>(`/erp/products/${id}/`, data),

  quotations: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<ErpQuotation>>('/erp/quotations/', { params }),
  quotation: (id: number) => apiClient.get<ErpQuotation>(`/erp/quotations/${id}/`),
  createQuotation: (data: { customer: number; quotation_date?: string; valid_until?: string; notes?: string }) =>
    apiClient.post<ErpQuotation>('/erp/quotations/', data),
  updateQuotation: (id: number, data: { notes?: string; valid_until?: string | null }) =>
    apiClient.patch<ErpQuotation>(`/erp/quotations/${id}/`, data),
  deleteQuotation: (id: number) => apiClient.delete(`/erp/quotations/${id}/`),
  setQuotationStatus: (id: number, status: 'draft' | 'sent' | 'accepted' | 'rejected') =>
    apiClient.post<ErpQuotation>(`/erp/quotations/${id}/status/`, { status }),
  addQuotationItem: (id: number, data: ErpLineItemInput) =>
    apiClient.post<ErpQuotation>(`/erp/quotations/${id}/items/`, data),
  updateQuotationItem: (id: number, itemId: number, data: Partial<ErpLineItemInput>) =>
    apiClient.patch<ErpQuotation>(`/erp/quotations/${id}/items/${itemId}/`, data),
  deleteQuotationItem: (id: number, itemId: number) =>
    apiClient.delete<ErpQuotation>(`/erp/quotations/${id}/items/${itemId}/`),
  convertQuotation: (id: number) => apiClient.post(`/erp/quotations/${id}/convert/`),

  orders: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<ErpSalesOrder>>('/erp/orders/', { params }),
  order: (id: number) => apiClient.get<ErpSalesOrder>(`/erp/orders/${id}/`),
  invoiceOrder: (id: number, data?: { due_date?: string | null }) =>
    apiClient.post<ErpInvoice>(`/erp/orders/${id}/invoice/`, data ?? {}),
  cancelOrder: (id: number, reason: string) =>
    apiClient.post<ErpSalesOrder>(`/erp/orders/${id}/cancel/`, { reason }),

  invoices: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<ErpInvoice>>('/erp/invoices/', { params }),
  invoice: (id: number) => apiClient.get<ErpInvoice>(`/erp/invoices/${id}/`),
  /** Raise a DRAFT invoice with no sales order behind it. Lines are added after. */
  createInvoice: (data: { customer: number; invoice_date?: string; due_date?: string | null; notes?: string }) =>
    apiClient.post<ErpInvoice>('/erp/invoices/', data),
  updateInvoice: (id: number, data: { notes?: string; due_date?: string | null; invoice_date?: string }) =>
    apiClient.patch<ErpInvoice>(`/erp/invoices/${id}/`, data),
  deleteInvoice: (id: number) => apiClient.delete(`/erp/invoices/${id}/`),
  updateInvoiceItem: (id: number, itemId: number, data: Partial<ErpLineItemInput>) =>
    apiClient.patch<ErpInvoice>(`/erp/invoices/${id}/items/${itemId}/`, data),
  issueInvoice: (id: number) => apiClient.post(`/erp/invoices/${id}/issue/`),
  cancelInvoice: (id: number, reason: string) =>
    apiClient.post(`/erp/invoices/${id}/cancel/`, { reason }),
  addInvoiceItem: (id: number, data: ErpLineItemInput) =>
    apiClient.post<ErpInvoice>(`/erp/invoices/${id}/items/`, data),
  deleteInvoiceItem: (id: number, itemId: number) =>
    apiClient.delete<ErpInvoice>(`/erp/invoices/${id}/items/${itemId}/`),
  addPayment: (id: number, data: Record<string, unknown>) =>
    apiClient.post(`/erp/invoices/${id}/payments/`, data),

  deleteCustomer: (id: number) => apiClient.delete(`/erp/customers/${id}/`),
  deleteProduct: (id: number) => apiClient.delete(`/erp/products/${id}/`),

  payments: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<ErpPayment>>('/erp/payments/', { params }),
  /** Reverse a payment recorded by mistake — the invoice's balance reopens. */
  deletePayment: (id: number) => apiClient.delete(`/erp/payments/${id}/`),

  dashboard: (month?: string) =>
    apiClient.get<ErpDashboard>('/erp/dashboard/', { params: month ? { month } : undefined }),

  gstSummary: (month: string) =>
    apiClient.get<GstSummary>('/erp/reports/gst-summary/', { params: { month } }),

  /** Streams a CSV — the caller turns the blob into a download. */
  tallyExport: (params?: Record<string, string | undefined>) =>
    apiClient.get('/erp/export/tally/', { params, responseType: 'blob' }),
};

export interface ErpPayment {
  id: number;
  invoice: number;
  invoice_number?: string;
  customer_name?: string;
  amount: string;
  paid_on: string;
  mode: string;
  reference: string;
  recorded_by: number | null;
  created_at?: string;
}

export interface ErpDashboard {
  month: string;
  revenue: { total: string; taxable: string; tax: string; invoices: number };
  collected_this_month: string;
  outstanding: string;
  ageing: { current: string; '1_30': string; '31_60': string; '61_90': string; '90_plus': string };
  open_invoices: number;
  top_customers: Array<{ id: number; name: string; total: string; invoices: number }>;
  counts: { customers: number; products: number; draft_invoices: number; open_quotations: number };
}

export interface GstSummaryRow {
  gst_rate: string;
  taxable: string; cgst: string; sgst: string; igst: string; total_tax: string;
  invoices: number;
}

export interface GstSummary {
  month: string;
  b2b: GstSummaryRow[];
  b2c: GstSummaryRow[];
  invoice_count: number;
  note: string;
}

export interface ErpLineItemInput {
  product?: number | null;
  description: string;
  hsn_sac?: string;
  quantity: string;
  unit_price: string;
  discount_percent?: string;
  gst_rate: string;
}

// ============================================================
// AUTH helpers (used in authStore)
// ============================================================
export { setAuth, clearAuth };


// ============================================================
// RECRUITMENT / ATS  /api/v1/recruitment/   (module: recruitment)
// ============================================================
export const atsApi = {
  dashboard: () => apiClient.get<AtsDashboard>('/recruitment/dashboard/'),

  // ---- Job openings ----
  openings: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<JobOpening>>('/recruitment/openings/', { params }),
  opening: (id: number) => apiClient.get<JobOpening>(`/recruitment/openings/${id}/`),
  createOpening: (data: Record<string, unknown>) =>
    apiClient.post<JobOpening>('/recruitment/openings/', data),
  updateOpening: (id: number, data: Record<string, unknown>) =>
    apiClient.patch<JobOpening>(`/recruitment/openings/${id}/`, data),
  deleteOpening: (id: number) => apiClient.delete(`/recruitment/openings/${id}/`),
  setOpeningStatus: (id: number, status: string) =>
    apiClient.post<JobOpening>(`/recruitment/openings/${id}/status/`, { status }),

  // ---- Pipeline stages ----
  stages: () => apiClient.get<PipelineStage[]>('/recruitment/stages/'),
  createStage: (data: Record<string, unknown>) =>
    apiClient.post<PipelineStage>('/recruitment/stages/', data),
  updateStage: (id: number, data: Record<string, unknown>) =>
    apiClient.patch<PipelineStage>(`/recruitment/stages/${id}/`, data),
  deleteStage: (id: number) => apiClient.delete(`/recruitment/stages/${id}/`),
  reorderStages: (order: number[]) =>
    apiClient.post<PipelineStage[]>('/recruitment/stages/reorder/', { order }),

  // ---- Candidates ----
  candidates: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<Candidate>>('/recruitment/candidates/', { params }),
  candidate: (id: number) => apiClient.get<Candidate>(`/recruitment/candidates/${id}/`),
  /** Multipart, because a candidate may arrive with a resume attached. */
  createCandidate: (data: FormData) =>
    apiClient.post<Candidate>('/recruitment/candidates/', data, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  updateCandidate: (id: number, data: FormData | Record<string, unknown>) =>
    apiClient.patch<Candidate>(`/recruitment/candidates/${id}/`, data,
      data instanceof FormData
        ? { headers: { 'Content-Type': 'multipart/form-data' } }
        : undefined),
  archiveCandidate: (id: number) => apiClient.delete(`/recruitment/candidates/${id}/`),
  checkDuplicate: (email?: string, phone?: string, exclude?: number) =>
    apiClient.get<{ count: number; matches: Candidate[] }>(
      '/recruitment/candidates/check-duplicate/',
      { params: { email, phone, exclude } },
    ),

  // ---- Applications ----
  applications: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<Application>>('/recruitment/applications/', { params }),
  application: (id: number) => apiClient.get<Application>(`/recruitment/applications/${id}/`),
  createApplication: (candidate: number, opening: number) =>
    apiClient.post<Application>('/recruitment/applications/', { candidate, opening }),
  updateApplication: (id: number, data: Record<string, unknown>) =>
    apiClient.patch<Application>(`/recruitment/applications/${id}/`, data),
  moveApplication: (id: number, stage: number, note = '') =>
    apiClient.post<Application>(`/recruitment/applications/${id}/move/`, { stage, note }),
  bulkMove: (applications: number[], stage: number, note = '') =>
    apiClient.post<{ moved: number; errors: Array<{ application: number; message: string }>; stage: string }>(
      '/recruitment/applications/bulk-move/', { applications, stage, note },
    ),
  setApplicationStatus: (id: number, status: string, note = '') =>
    apiClient.post<Application>(`/recruitment/applications/${id}/status/`, { status, note }),
  activity: (id: number) =>
    apiClient.get<ApplicationActivity[]>(`/recruitment/applications/${id}/activity/`),
  addNote: (id: number, note: string) =>
    apiClient.post<ApplicationActivity>(`/recruitment/applications/${id}/activity/`, { note }),

  // ---- Interviews ----
  interviews: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<Interview>>('/recruitment/interviews/', { params }),
  createInterview: (data: Record<string, unknown>) =>
    apiClient.post<Interview>('/recruitment/interviews/', data),
  updateInterview: (id: number, data: Record<string, unknown>) =>
    apiClient.patch<Interview>(`/recruitment/interviews/${id}/`, data),
  cancelInterview: (id: number) => apiClient.delete(`/recruitment/interviews/${id}/`),
  submitFeedback: (id: number, data: Record<string, unknown>) =>
    apiClient.post<InterviewFeedback>(`/recruitment/interviews/${id}/feedback/`, data),

  // ---- Offers ----
  offers: (params?: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<Offer>>('/recruitment/offers/', { params }),
  createOffer: (data: Record<string, unknown>) =>
    apiClient.post<Offer>('/recruitment/offers/', data),
  updateOffer: (id: number, data: Record<string, unknown>) =>
    apiClient.patch<Offer>(`/recruitment/offers/${id}/`, data),
  deleteOffer: (id: number) => apiClient.delete(`/recruitment/offers/${id}/`),
  setOfferStatus: (id: number, status: string) =>
    apiClient.post<Offer>(`/recruitment/offers/${id}/status/`, { status }),
  convertToEmployee: (id: number, employee_code?: string) =>
    apiClient.post<{ employee: Employee; offer: Offer }>(
      `/recruitment/offers/${id}/convert-to-employee/`, { employee_code },
    ),
  suggestEmployeeCode: () =>
    apiClient.get<{ employee_code: string }>('/recruitment/suggest-employee-code/'),

  /** Active agents for interview panels / hiring manager. Open to ats.view —
      /auth/agents/ is manager-only and refused HR and recruiters. */
  people: () =>
    apiClient.get<Array<{ id: number; name: string; role: string }>>('/recruitment/people/'),

  /** Active employees for an offer's "Reports to". No HRMS capability needed. */
  reportingOptions: () =>
    apiClient.get<Array<{ id: number; name: string; designation: string }>>(
      '/recruitment/reporting-options/',
    ),
};

export interface AtsDashboard {
  openings: { open: number; positions: number; on_hold: number; closed: number };
  candidates: { total: number; applications_open: number; applied_this_month: number };
  by_stage: Array<{ id: number; name: string; count: number; is_terminal: boolean }>;
  interviews: { upcoming_7_days: number; awaiting_feedback: number };
  offers: { sent: number; accepted: number; pending_conversion: number };
  avg_time_to_hire_days: number | null;
}


export interface MyPerformance {
  period: { days: number; date_from: string; date_to: string };
  calls: {
    total: number; connected: number; connection_rate: number;
    talk_seconds: number; avg_talk_seconds: number;
    outbound: number; inbound: number; missed: number;
  };
  calls_by_day: Array<{ date: string; calls: number; connected: number; talk_seconds: number }>;
  today: { calls: number; first_call_at: string | null; last_call_at: string | null };
  leads: {
    assigned_total: number;
    by_status: Record<string, number>;
    new_in_period: number;
    converted_in_period: number;
    converted_total: number;
    conversion_rate: number;
  };
  followups: {
    overdue: number; due_today: number; upcoming_7d: number; completed_in_period: number;
    next: Array<{
      id: number; lead_id: number; lead_name: string;
      scheduled_at: string; type: string; overdue: boolean;
    }>;
  };
}

export interface CampaignRecipientRow {
  id: number;
  lead_id: number;
  lead_name: string;
  phone: string;
  status: string;
  error_message: string;
  sent_at: string | null;
}
