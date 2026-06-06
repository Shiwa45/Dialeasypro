// ============================================================
// DialEasypro — API Layer
// Every backend endpoint mapped with correct URLs
// ============================================================
import apiClient, { clearAuth, setAuth } from './client';
import type {
  Agent, BulkCampaign, CallDisposition, CallLog, CallStats,
  CustomField, DailyActivity, FollowUp, IntegrationConfig,
  Lead, LeadImportJob, LeadNote, LeadStats, LoginResponse,
  PaginatedResponse, Plan, Team, WebhookLog, WhatsAppTemplate,
  AgentPerformanceReport, CallAnalyticsReport, ConversionFunnelReport,
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

  setAgentPassword: (id: number, new_password: string, confirm_password: string, require_change_on_login = false) =>
    apiClient.post(`/auth/agents/${id}/set-password/`, { new_password, confirm_password, require_change_on_login }),

  // Teams
  listTeams: () => apiClient.get<PaginatedResponse<Team>>('/auth/teams/'),
  createTeam: (data: Partial<Team>) => apiClient.post<Team>('/auth/teams/', data),
};

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

  updateStatus: (id: number, status: string) =>
    apiClient.patch<{ id: number; status: string }>(`/leads/${id}/status/`, { status }),

  bulkAssign: (lead_ids: number[], assigned_to: number) =>
    apiClient.post('/leads/bulk-assign/', { lead_ids, assigned_to }),

  distribute: (data: {
    agent_ids: number[];
    only_unassigned?: boolean;
    statuses?: string[];
    priorities?: string[];
    sources?: string[];
    search?: string;
    limit?: number | null;
  }) => apiClient.post<{ distributed: number; per_agent: Record<string, number>; message?: string }>(
    '/leads/distribute/', data
  ),

  flush: (confirm: string) =>
    apiClient.post<{ deleted: number }>('/leads/flush/', { confirm }),

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

  // Custom fields
  listCustomFields: () =>
    apiClient.get<CustomField[]>('/leads/custom-fields/'),

  createCustomField: (data: Partial<CustomField>) =>
    apiClient.post<CustomField>('/leads/custom-fields/', data),
};

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

  dispositions: () => apiClient.get<CallDisposition[]>('/calls/dispositions/'),

  stats: (params?: { date_from?: string; date_to?: string; agent?: string }) =>
    apiClient.get<CallStats>('/calls/stats/', { params }),
};

// ============================================================
// COMMUNICATIONS  /api/v1/comms/
// ============================================================
export const commsApi = {
  // WhatsApp templates
  listTemplates: (approvedOnly?: boolean) =>
    apiClient.get<WhatsAppTemplate[]>('/comms/whatsapp/templates/', {
      params: approvedOnly ? { approved_only: true } : undefined,
    }),

  createTemplate: (data: Partial<WhatsAppTemplate>) =>
    apiClient.post<WhatsAppTemplate>('/comms/whatsapp/templates/', data),

  uploadTemplateMedia: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return apiClient.post<{ url: string; public_id: string }>('/comms/template-media/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  // WhatsApp messages thread
  listMessages: (leadId: number) =>
    apiClient.get<PaginatedResponse<unknown>>('/comms/whatsapp/messages/', {
      params: { lead: leadId },
    }),

  // Send single WhatsApp
  sendWhatsApp: (lead_id: number, message: string, template_id?: number) =>
    apiClient.post('/comms/whatsapp/send/', { lead_id, message, template_id }),

  // Send single SMS
  sendSMS: (lead_id: number, message: string, sender_id?: string) =>
    apiClient.post('/comms/sms/send/', { lead_id, message, sender_id }),

  // Campaigns
  listCampaigns: (params?: Record<string, string>) =>
    apiClient.get<PaginatedResponse<BulkCampaign>>('/comms/campaigns/', { params }),

  createCampaign: (data: Record<string, unknown>) =>
    apiClient.post<BulkCampaign>('/comms/campaigns/', data),

  getCampaign: (id: string) => apiClient.get<BulkCampaign>(`/comms/campaigns/${id}/`),

  launchCampaign: (id: string) =>
    apiClient.post<{ message: string; id: string }>(`/comms/campaigns/${id}/launch/`),

  pauseCampaign: (id: string) =>
    apiClient.post<{ message: string }>(`/comms/campaigns/${id}/pause/`),
};

// ============================================================
// REPORTS  /api/v1/reports/
// ============================================================
export const reportsApi = {
  agentPerformance: (params?: { date_from?: string; date_to?: string; agent_id?: string }) =>
    apiClient.get<AgentPerformanceReport>('/reports/agent-performance/', { params }),

  leadSources: (params?: { date_from?: string; date_to?: string }) =>
    apiClient.get<{ period: unknown; by_source: unknown[] }>('/reports/lead-sources/', { params }),

  callAnalytics: (params?: { date_from?: string; date_to?: string }) =>
    apiClient.get<CallAnalyticsReport>('/reports/call-analytics/', { params }),

  conversionFunnel: (params?: { date_from?: string; date_to?: string }) =>
    apiClient.get<ConversionFunnelReport>('/reports/conversion-funnel/', { params }),

  dailyActivity: () => apiClient.get<DailyActivity>('/reports/daily-activity/'),
};

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

  metaForms: () =>
    apiClient.get<{ forms: Array<{ id: string; name: string; status: string; fields: Array<{ key: string; label: string }> }> }>(
      '/integrations/meta/forms/'
    ),
};

// ============================================================
// PUBLIC  /api/v1/public/
// ============================================================
export const publicApi = {
  listPlans: () => apiClient.get<Plan[]>('/public/plans/'),
  checkSubdomain: (name: string) =>
    apiClient.get<{ available: boolean; slug: string; url: string }>('/public/check-subdomain/', {
      params: { name },
    }),
};

// ============================================================
// AUTH helpers (used in authStore)
// ============================================================
export { setAuth, clearAuth };
