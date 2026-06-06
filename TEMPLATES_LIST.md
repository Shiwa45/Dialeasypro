# TeleCRM — HTML Templates to Build
All templates live under `templates/` in the project root (configured in settings.py).
Base templates use Tailwind CSS + HTMX. No React/SPA — server-rendered with HTMX for interactivity.

---

## 1. Tenant Admin Web UI  (`templates/tenant_admin/`)

### Auth
| File | View | Notes |
|------|------|-------|
| `tenant_admin/auth/login.html` | `TenantAdminLoginView` | Email + password form, company logo, "Forgot password?" link |
| `tenant_admin/auth/change_password.html` | _(password change view — Phase 2)_ | Shown on first login if `must_change_password=True` |
| `tenant_admin/auth/forgot_password.html` | _(Phase 2)_ | Email input to trigger reset |
| `tenant_admin/auth/reset_password.html` | _(Phase 2)_ | New password + confirm form |

### Layout & Base
| File | Used By | Notes |
|------|---------|-------|
| `tenant_admin/base.html` | All tenant admin templates | Sidebar nav, topbar, flash messages, HTMX CDN, Tailwind CDN |
| `tenant_admin/components/sidebar.html` | `base.html` include | Nav links: Dashboard, Leads, Calls, Agents, Reports, Settings, Billing |
| `tenant_admin/components/topbar.html` | `base.html` include | Tenant name, agent avatar, notifications bell, logout |
| `tenant_admin/components/breadcrumb.html` | Reusable include | `{% include %}` with `{% block breadcrumbs %}` |
| `tenant_admin/components/pagination.html` | All list views | Standard prev/next page controls |
| `tenant_admin/components/empty_state.html` | All list views | Illustration + CTA when list is empty |
| `tenant_admin/components/alert.html` | Flash message area | Success / error / warning / info cards |
| `tenant_admin/components/confirm_modal.html` | Delete actions | HTMX-powered confirmation dialog |
| `tenant_admin/components/loading_spinner.html` | HTMX requests | Shown via `hx-indicator` |

### Dashboard
| File | View | Notes |
|------|------|-------|
| `tenant_admin/dashboard/index.html` | `TenantAdminDashboardView` | KPI cards (leads today, calls made, follow-ups due, conversion rate), activity feed, agent status grid |
| `tenant_admin/dashboard/partials/kpi_cards.html` | HTMX partial | Auto-refreshes every 60s via `hx-trigger="every 60s"` |
| `tenant_admin/dashboard/partials/agent_status.html` | HTMX partial | Live grid of agent online/offline status |
| `tenant_admin/dashboard/partials/recent_activity.html` | HTMX partial | Latest 10 actions across the tenant |

### Agents
| File | View | Notes |
|------|------|-------|
| `tenant_admin/agents/list.html` | `AgentListView` | Table: name, role badge, status, last active, actions |
| `tenant_admin/agents/form.html` | `AgentCreateView` / `AgentUpdateView` | Shared create/edit form. `action` context var switches labels |
| `tenant_admin/agents/detail.html` | _(Phase 2)_ | Agent profile: stats, recent calls, leads assigned |
| `tenant_admin/agents/partials/agent_row.html` | HTMX | Single table row for live updates |

### Profile
| File | View | Notes |
|------|------|-------|
| `tenant_admin/profile/index.html` | `ProfileView` | Name, phone, photo upload, timezone, language |
| `tenant_admin/profile/change_password.html` | _(Phase 2)_ | Old/new/confirm password |

### Leads (Phase 2 — list here for completeness)
| File | Notes |
|------|-------|
| `tenant_admin/leads/list.html` | Filterable lead table with Kanban toggle |
| `tenant_admin/leads/kanban.html` | Drag-and-drop pipeline view by stage |
| `tenant_admin/leads/detail.html` | Lead detail: contact info, call history, WhatsApp thread, notes, follow-ups |
| `tenant_admin/leads/form.html` | Add / edit lead |
| `tenant_admin/leads/import.html` | CSV / Excel import wizard (3 steps) |
| `tenant_admin/leads/import_result.html` | Shows rows imported, errors, duplicates |
| `tenant_admin/leads/partials/lead_card.html` | HTMX — single kanban card |
| `tenant_admin/leads/partials/lead_row.html` | HTMX — single list row |
| `tenant_admin/leads/partials/call_history.html` | HTMX partial on lead detail |
| `tenant_admin/leads/partials/notes.html` | HTMX partial — add/view notes inline |
| `tenant_admin/leads/partials/followup_form.html` | HTMX — add follow-up inline |
| `tenant_admin/leads/partials/whatsapp_thread.html` | WhatsApp chat-style message thread |
| `tenant_admin/leads/partials/quick_actions.html` | Call / WhatsApp / Email / SMS buttons |

### Calls (Phase 2)
| File | Notes |
|------|-------|
| `tenant_admin/calls/list.html` | Call log table with filters (date, agent, direction, outcome) |
| `tenant_admin/calls/detail.html` | Call detail with recording player |
| `tenant_admin/calls/partials/call_row.html` | HTMX row |

### Bulk Communication (Phase 3)
| File | Notes |
|------|-------|
| `tenant_admin/bulk/whatsapp.html` | Compose bulk WhatsApp: select audience, pick template, schedule |
| `tenant_admin/bulk/email.html` | Bulk email composer |
| `tenant_admin/bulk/sms.html` | Bulk SMS composer |
| `tenant_admin/bulk/campaign_list.html` | Past campaigns with delivery stats |
| `tenant_admin/bulk/campaign_detail.html` | Per-campaign stats: sent, delivered, failed, replied |

### Reports
| File | Notes |
|------|-------|
| `tenant_admin/reports/index.html` | Reports hub with report type selector |
| `tenant_admin/reports/agent_performance.html` | Per-agent: calls, leads, conversion %, avg call duration |
| `tenant_admin/reports/lead_sources.html` | Leads by source with trend chart |
| `tenant_admin/reports/call_analytics.html` | Call volume, duration, outcome breakdown |
| `tenant_admin/reports/funnel.html` | Lead-to-sale conversion funnel |
| `tenant_admin/reports/partials/chart_wrapper.html` | Chart.js wrapper partial |

### Settings
| File | Notes |
|------|-------|
| `tenant_admin/settings/index.html` | Settings hub |
| `tenant_admin/settings/company.html` | Company name, logo, GSTIN, address |
| `tenant_admin/settings/integrations.html` | Enable/configure: IndiaMART, Meta Ads, Google Ads, webhook |
| `tenant_admin/settings/whatsapp.html` | WhatsApp provider config (choose provider, enter API keys) |
| `tenant_admin/settings/call.html` | Calling integration config (Exotel, MCUBE, etc.) |
| `tenant_admin/settings/templates.html` | Manage WhatsApp / SMS / email templates |
| `tenant_admin/settings/custom_fields.html` | Add / remove custom lead fields |
| `tenant_admin/settings/teams.html` | Create / edit teams, assign members |

### Billing
| File | Notes |
|------|-------|
| `tenant_admin/billing/index.html` | Current plan, usage meters, upgrade CTA, invoice list |
| `tenant_admin/billing/upgrade.html` | Plan comparison table + Razorpay checkout |
| `tenant_admin/billing/invoice_detail.html` | GST-compliant invoice view with PDF download link |

### Onboarding (shown once on first login)
| File | Notes |
|------|-------|
| `tenant_admin/onboarding/step_1.html` | Company profile setup |
| `tenant_admin/onboarding/step_2.html` | Add first agent |
| `tenant_admin/onboarding/step_3.html` | Import first leads |
| `tenant_admin/onboarding/step_4.html` | Connect WhatsApp |
| `tenant_admin/onboarding/step_5.html` | Done — tour the dashboard |

---

## 2. Agent Monitoring (admin-only real-time view)

| File | Notes |
|------|-------|
| `tenant_admin/monitoring/live.html` | WebSocket-powered live view: agent status cards, call ticker, today's stats |

---

## 3. Super Admin UI  (`templates/super_admin/`)

These extend Django Unfold — minimal custom templates needed.

| File | View | Notes |
|------|------|-------|
| `super_admin/dashboard.html` | `SuperAdminDashboardView` | Unfold dashboard override with tenant stats widgets |

---

## 4. Email Templates  (`templates/emails/`)

All emails are plain-text with optional HTML versions.

| File | Sent By | Notes |
|------|---------|-------|
| `emails/welcome.html` | `send_tenant_welcome_email` | New tenant welcome — company name, login URL, trial info |
| `emails/welcome.txt` | Same | Plain-text version |
| `emails/trial_expiry_warning.html` | `send_trial_expiry_warning` | Upgrade CTA, days remaining, pricing table link |
| `emails/trial_expiry_warning.txt` | Same | Plain-text version |
| `emails/trial_expired.html` | `_send_trial_expired_email` | Account suspended, reactivation link |
| `emails/trial_expired.txt` | Same | |
| `emails/agent_welcome.html` | `send_agent_welcome_email` | New agent credentials and login URL |
| `emails/agent_welcome.txt` | Same | |
| `emails/invoice.html` | _(Phase 2)_ | GST invoice email with PDF attachment |
| `emails/invoice.txt` | Same | |
| `emails/payment_failed.html` | _(Phase 2)_ | Payment failure + retry link |
| `emails/followup_reminder.html` | _(Phase 2)_ | Daily follow-up digest for agent |
| `emails/daily_performance.html` | _(Phase 2)_ | Daily stats summary for manager |
| `emails/base_email.html` | All email templates | Base layout: logo, header, footer, unsubscribe |

---

## 5. Error Pages  (`templates/`)

| File | Notes |
|------|-------|
| `404.html` | Custom 404 — suggests going back to dashboard |
| `500.html` | Custom 500 — apologises, shows support email |
| `403.html` | Custom 403 — "Access denied" with role explanation |

---

## Template Context Available in All `tenant_admin/*` Templates

From `context_processors.py`:

```
{{ current_tenant.company_name }}
{{ current_tenant.schema_name }}
{{ is_public_schema }}
{{ current_agent.name }}
{{ current_agent.role }}
{{ features.bulk_whatsapp }}   ← feature flags
{{ features.advanced_reports }}
{{ plan.name }}
{{ subscription_status }}
```

---

## HTMX Patterns Used

```html
<!-- Auto-refresh partial every 60s -->
<div hx-get="/crm/dashboard/kpi/" hx-trigger="every 60s" hx-swap="innerHTML">
  {% include "tenant_admin/dashboard/partials/kpi_cards.html" %}
</div>

<!-- Delete with confirmation -->
<button hx-post="/crm/agents/5/delete/"
        hx-confirm="Deactivate this agent?"
        hx-target="#agent-5-row"
        hx-swap="outerHTML">
  Deactivate
</button>

<!-- Inline form submission -->
<form hx-post="/crm/leads/42/note/add/"
      hx-target="#notes-section"
      hx-swap="innerHTML">
  ...
</form>
```

---

## 6. Additions from Phase 2

### Calls (now in Phase 2, not just Phase 3)
| File | View | Notes |
|------|------|-------|
| `tenant_admin/calls/list.html` | `CallListMVTView` | Call log table: agent, lead, duration, disposition, recording player icon |
| `tenant_admin/calls/detail.html` | _(Phase 3)_ | Call detail with inline audio player and transcript |
| `tenant_admin/calls/partials/call_row.html` | HTMX | Single table row for live updates |

### Lead Import Additions
The `tenant_admin/leads/import_result.html` template should show:
- Progress bar (poll via HTMX `hx-trigger="every 2s"` until status != processing)
- Summary: total, succeeded, failed, duplicates
- Error table: row number, data preview, error message
- Download failures button (CSV of failed rows)

### New MVT URL namespace additions (update `apps/authentication/urls.py`)
The following URLs are now wired under `tenant_admin` namespace via include:
- `/crm/leads/*` → `apps.leads.urls`
- `/crm/calls/*` → `apps.calls.urls`
