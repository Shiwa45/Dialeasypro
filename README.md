# TeleCRM Backend

A production-ready multi-tenant CRM backend for the Indian market — built to compete with NeoDove and GoDial.

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django 5.1 + Django REST Framework |
| Multi-tenancy | django-tenants (schema-per-tenant, PostgreSQL) |
| Database | PostgreSQL 16 |
| Cache / Broker | Redis 7 |
| Task Queue | Celery 5 + django-celery-beat |
| WebSocket | Django Channels 4 |
| Auth | Custom JWT (simplejwt infrastructure, Agent model) |
| Admin | Django Unfold |
| Payments | Razorpay (subscriptions + GST invoices) |
| Storage | AWS S3 (django-storages) |
| WhatsApp | Interakt / AiSensy / Wati / Gupshup |
| SMS | MSG91 / TextLocal |
| Mobile | Flutter (separate repo — consumes this API) |

---

## Architecture

```
Public Schema (shared across all tenants)
├── Tenant          ← one row per client company
├── Domain          ← subdomain routing
├── Plan / PlanFeature / Subscription / Invoice
├── AuditLog / GlobalSettings / SupportNote
└── Django auth.User (super admins only)

Per-Tenant Schema (one PostgreSQL schema per client)
├── Agent           ← CRM users (not Django auth.User)
├── Team / AgentTeam
├── AgentLoginSession
├── Lead / FollowUp / LeadNote / LeadActivity
├── CustomField / CustomFieldValue
├── LeadImportJob
├── CallLog / CallDisposition / CallRecording
├── WhatsAppTemplate / WhatsAppMessage
├── BulkCampaign / CampaignRecipient
├── EmailLog / SMSLog
├── LeadSourceConfig / WebhookLog
└── (reports — no DB tables, computed on demand)
```

---

## Phases Delivered

### Phase 1 — Foundation
- `apps/core` — base models, middleware, permissions, WebSockets, constants, storage, utilities
- `apps/tenants` — schema-per-tenant, Tenant + Domain models, management commands, registration API
- `apps/plans` — Plan/PlanFeature/Subscription/Invoice with full GST compliance, Razorpay integration
- `apps/superadmin` — AuditLog, GlobalSettings, Unfold admin panel, audit middleware
- `apps/authentication` — Agent model, JWT auth, DRF API + Django MVT web views

### Phase 2 — CRM Core
- `apps/leads` — Lead, FollowUp, LeadNote, LeadActivity, CustomField, LeadImportJob; kanban + list MVT views; CSV/XLSX import pipeline (column mapping, deduplication, progress tracking); lead export; lead scoring
- `apps/calls` — CallLog, CallDisposition, CallRecording; click-to-call; Exotel/MCUBE/Knowlarity webhook handlers; call recording download; manual log form; call analytics

### Phase 3 — Communications & Integrations
- `apps/communications` — WhatsApp (single + bulk), Email (bulk), SMS (bulk); pluggable provider architecture; campaign management with Celery fan-out; TRAI DND enforcement; delivery tracking via webhooks
- `apps/integrations` — IndiaMART, Meta Lead Ads, Meta Click-to-WhatsApp, Google Ads, generic token-based webhook; all with signature validation; `test_webhook` management command
  - **Meta Click-to-WhatsApp** turns an inbound WhatsApp conversation started from a Meta ad into a lead with its ad attribution — no Lead Form involved. Setup: [META_WHATSAPP_SETUP.md](META_WHATSAPP_SETUP.md) · [client guide](META_WHATSAPP_CLIENT_GUIDE.md) · [troubleshooting](META_WHATSAPP_TROUBLESHOOTING.md)
- `apps/reports` — Agent performance, lead source breakdown, call analytics, conversion funnel, daily activity ticker — all Redis-cached

### Phase 4 — Back-office suite (sellable add-on modules)
- `apps/hrms` — Employee, Attendance (derived nightly from dialer sessions, with manual check-in and admin correction), Leave (types, balances, requests, bulk annual allocation), Expense claims with receipts, the Incentive engine (the CRM → payroll bridge), Salary structures and Payroll runs producing draft → finalized → paid payslips
- `apps/erp` — Customers, Products, Quotation → Sales order → Invoice with server-side GST from HSN/SAC and place of supply, locked document numbering, payments ledger, receivables ageing, Tally/Zoho export and a GSTR-1-shaped GST summary
- `apps/recruitment` — Full ATS: JobOpening, configurable PipelineStage, Candidate database with duplicate detection, Application with an append-only activity trail, Interview scheduling with per-interviewer scorecards, and Offers that **convert into an HRMS Employee** — the bridge that makes this one company suite rather than three products sharing a login

### Access model — roles and capabilities
Two independent gates guard every module endpoint, and both must pass:

| Gate | Question | Failure |
|---|---|---|
| `HasFeatureAccess` | Did this tenant buy the module? | `402` + upsell payload |
| `HasCapability` | May this user perform the action? | `403` |

Capabilities live in one declarative table (`apps/core/capabilities.py`) and are served to the
web app at `GET /api/v1/auth/capabilities/`, so a hidden button and a refused request always
have the same cause. Two back-office roles sit deliberately **outside** the CRM hierarchy:

- **`hr`** — runs HRMS and Recruitment end-to-end, including payroll, without CRM admin rights (no tenant settings, no agent passwords, no lead data)
- **`accounts`** — runs Sales & Billing including issuing and cancelling invoices, without CRM admin rights

A manager approves leave and expenses but can never read a colleague's salary; a senior agent
files interview scorecards without seeing salary bands or offers.

---

## Quick Start

### Prerequisites
- Docker Desktop (or Docker + Docker Compose)
- PostgreSQL 16 (via Docker)
- Redis 7 (via Docker)

### 1. Clone and configure
```bash
git clone https://github.com/yourorg/telecrm-backend
cd telecrm-backend
cp .env.example .env
# Edit .env — set DB_PASSWORD, SECRET_KEY, RAZORPAY_* keys
```

### 2. Start services
```bash
docker-compose up -d db redis
```

### 3. Run migrations + seed data
```bash
docker-compose run --rm web python manage.py migrate_schemas --shared
docker-compose run --rm web python manage.py create_public_tenant
docker-compose run --rm web python manage.py setup_initial_data
# Optional: create a demo tenant
docker-compose run --rm web python manage.py setup_initial_data --create-demo-tenant
```

### 4. Start all services
```bash
docker-compose up
```

Services available:
- **Django** → `http://localhost:8000`
- **Super Admin** → `http://localhost:8000/superadmin/`
- **Flower** (Celery monitor) → `http://localhost:5555`

### 5. Create a tenant
```bash
docker-compose run --rm web python manage.py create_tenant \
  --company="Acme Realty Pvt Ltd" \
  --email=admin@acmerealty.com \
  --phone=9876543210 \
  --name="Rahul Sharma" \
  --plan=starter
```

Access at: `http://acme-realty.localhost:8000/crm/`

---

## URL Structure

### Public Schema (`telecrm.in`)
```
/superadmin/                    → Django Admin (Unfold) — super admins
/api/v1/public/register/        → Tenant self-registration
/api/v1/public/check-subdomain/ → Subdomain availability check
/api/v1/public/plans/           → Public plan listing
/webhooks/razorpay/             → Razorpay payment webhooks
/health/                        → Health check
```

### Tenant Schema (`{tenant}.telecrm.in`)
```
/crm/                           → Dashboard
/crm/login/ /crm/logout/        → Session auth
/crm/agents/                    → Agent list/CRUD
/crm/leads/                     → Lead list (table view)
/crm/leads/kanban/              → Pipeline board
/crm/leads/{id}/                → Lead detail + activity feed
/crm/leads/import/              → CSV/XLSX import wizard
/crm/calls/                     → Call log
/crm/calls/stats/               → Call analytics
/crm/profile/                   → Agent self-profile

/api/v1/auth/login/             → Agent JWT login
/api/v1/auth/me/                → Current agent profile
/api/v1/auth/agents/            → Agent management
/api/v1/leads/                  → Lead CRUD + filters
/api/v1/leads/pipeline/         → Kanban data
/api/v1/leads/stats/            → Dashboard KPIs
/api/v1/leads/import/           → Upload import file
/api/v1/leads/export/           → CSV export (streaming)
/api/v1/calls/                  → Call log
/api/v1/calls/click-to-call/    → Initiate call
/api/v1/calls/stats/            → Call analytics
/api/v1/comms/whatsapp/send/    → Send WhatsApp
/api/v1/comms/campaigns/        → Bulk campaigns
/api/v1/integrations/indiamart/ → IndiaMART webhook
/api/v1/integrations/meta/      → Meta Lead Ads webhook (Lead Forms)
/api/v1/integrations/meta/whatsapp/  → Meta Click-to-WhatsApp webhook
/api/v1/integrations/google/    → Google Ads webhook
/api/v1/integrations/webhook/{token}/ → Generic webhook
/api/v1/reports/agent-performance/   → Agent stats
/api/v1/reports/lead-sources/        → Source breakdown
/api/v1/reports/conversion-funnel/   → Pipeline funnel

/api/v1/auth/features/          → Plan features + modules + role capabilities
/api/v1/auth/capabilities/      → Role capability map only

/api/v1/hrms/dashboard/         → Headcount, attendance today, pending approvals, payroll cost
/api/v1/hrms/employees/         → Employee roster (exit is a soft delete)
/api/v1/hrms/attendance/        → Attendance; PATCH {id}/ is the admin correction path
/api/v1/hrms/attendance/sync/   → Rebuild a day from dialer session logs
/api/v1/hrms/leave/             → Apply / approve / reject / cancel
/api/v1/hrms/leave-balances/bulk-allocate/  → Grant everyone their annual quota
/api/v1/hrms/expenses/          → Submit (multipart, with receipt) / approve / reject
/api/v1/hrms/incentives/compute/  → Recompute a month's earnings from CRM outcomes
/api/v1/hrms/payroll/run/       → Generate draft payslips  {"month": "YYYY-MM"}
/api/v1/hrms/payslips/{id}/finalize/   → Freeze the numbers
/api/v1/hrms/payslips/{id}/mark-paid/  → Record that money left

/api/v1/erp/dashboard/          → Revenue, outstanding, receivables ageing, top customers
/api/v1/erp/invoices/           → List, or POST to raise a standalone invoice
/api/v1/erp/invoices/{id}/issue/    → Assign the GST number (Accounts/Admin only)
/api/v1/erp/invoices/{id}/cancel/   → Cancel, keeping the number in the sequence
/api/v1/erp/payments/           → Payments ledger
/api/v1/erp/export/tally/       → Tally / Zoho Books CSV
/api/v1/erp/reports/gst-summary/    → B2B / B2C by rate (a filing aid, not a return)

/api/v1/recruitment/dashboard/  → Pipeline health, time-to-hire
/api/v1/recruitment/openings/   → Job openings + publish/hold/close
/api/v1/recruitment/stages/     → Configurable pipeline stages (+ reorder)
/api/v1/recruitment/candidates/ → Candidate database (+ duplicate check)
/api/v1/recruitment/applications/   → Pipeline; move, bulk-move, activity trail
/api/v1/recruitment/interviews/     → Scheduling + per-interviewer scorecards
/api/v1/recruitment/offers/{id}/convert-to-employee/  → ATS → HRMS handover

/ws/agent-monitor/              → WebSocket: live agent monitoring
/ws/notifications/{token}/      → WebSocket: agent push notifications
```

---

## Management Commands

```bash
# Initial setup
python manage.py migrate_schemas --shared
python manage.py create_public_tenant [--domain=telecrm.in]
python manage.py setup_initial_data [--create-demo-tenant]

# Tenant management
python manage.py create_tenant --company="..." --email=... --phone=... --name=...
python manage.py seed_dispositions --schema=acme_realty
python manage.py seed_dispositions --all

# Data operations
python manage.py export_leads --schema=acme_realty [--status=interested]

# Integration testing
python manage.py test_webhook --schema=acme_realty --source=indiamart
python manage.py test_webhook --schema=acme_realty --source=generic --token=<token>
```

---

## Celery Beat Schedule (IST times)

| Task | Schedule | Description |
|---|---|---|
| `check_trial_expirations` | Daily 9 AM | Suspend expired trials, send warnings at 7/3/1 days |
| `sync_all_tenant_usage_stats` | Daily 1 AM | Update agent/lead counts per tenant |
| `dispatch_followup_reminders` | Daily 8:30 AM | Push follow-up reminders via WebSocket |
| `dispatch_performance_summaries` | Daily 8 PM | Email daily stats to managers |
| `recalculate_lead_scores` | Daily 6 AM | Recalculate lead quality scores |
| `launch_scheduled_campaigns` | Every 5 min | Launch due bulk campaigns |
| `cleanup_expired_sessions` | Weekly Sunday | Mark stale login sessions inactive |
| `cleanup_expired_jwt_blacklist` | Weekly Sunday | Prune expired JWT blacklist tokens |

---

## Environment Variables

See `.env.example` for full list. Key variables:

```bash
SECRET_KEY=<50+ char random string>
DEBUG=False
BASE_DOMAIN=telecrm.in
DB_NAME=telecrm_db
DB_USER=telecrm
DB_PASSWORD=<strong password>
REDIS_URL=redis://redis:6379/0
RAZORPAY_KEY_ID=rzp_live_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_STORAGE_BUCKET_NAME=telecrm-prod
INTERAKT_API_KEY=...
MSG91_AUTH_KEY=...
```

---

## Plans

| Plan | Price | Agents | Leads | WhatsApp/day |
|---|---|---|---|---|
| Starter | ₹999/mo | 5 | 5,000 | 500 |
| Growth | ₹2,499/mo | 20 | 25,000 | 5,000 |
| Business | ₹5,999/mo | 100 | 1,00,000 | 20,000 |
| Enterprise | Custom | Unlimited | Unlimited | Unlimited |

All prices pre-GST. 18% GST added at billing. SAC code: 998315.

---

## Templates to Build

All HTML templates are listed in `TEMPLATES_LIST.md`. The backend renders:
- `templates/tenant_admin/` — CRM web UI (Tailwind + HTMX)
- `templates/super_admin/` — Extends Django Unfold
- `templates/emails/` — Transactional email templates

---

## Production Deployment

```bash
# 1. Build and push Docker image
docker build -t telecrm-backend:latest .

# 2. Set production env vars (use AWS Parameter Store / Secrets Manager)

# 3. Run with docker-compose (production profile)
docker-compose -f docker-compose.yml up -d

# 4. Run migrations (first deploy only)
docker-compose exec web python manage.py migrate_schemas --shared
docker-compose exec web python manage.py create_public_tenant --domain=telecrm.in
docker-compose exec web python manage.py setup_initial_data
```

For Kubernetes deployment, convert docker-compose services to Deployments/Services. Each service (web, celery_worker, celery_beat) should be a separate Deployment with shared PVC for static/media or use S3 for all file storage.
