# DialEasypro — Complete Company Suite: Improvement Plan

**Scope:** finish HRMS, finish Sales & Billing (ERP), add a Recruitment (ATS) module,
and put a proper role/access model behind all three.

**Decisions taken (confirmed):**

| Question | Decision |
|---|---|
| Recruitment depth | Full ATS — openings, candidates, pipeline, interviews + scorecards, offers, hired → Employee |
| Access model | Keep `admin/manager/senior_agent/agent/readonly`, **add `hr` and `accounts` roles** |
| Backend | Full stack — new models, endpoints, migrations, feature keys, module key |
| Delivery | Plan first (this document), implement after approval |

---

## 1. Where the project stands today

### 1.1 What already works

**Backend — `apps/hrms/`** is substantially complete:
Employee, Holiday, Attendance, LeaveType, LeaveBalance, LeaveRequest, ExpenseClaim,
IncentiveRule, IncentiveEarning, SalaryStructure, Payslip; services for attendance
derivation, leave, incentives and payroll; 28 endpoints in `api_urls.py`;
per-row scoping in `permissions.py`.

**Backend — `apps/erp/`** is substantially complete:
Customer, Product, DocumentSequence, Quotation, SalesOrder, CustomerInvoice, Payment,
GST computation in `gst.py`, document numbering in `services/numbering.py`,
Tally export; 22 endpoints in `api_urls.py`.

**Frontend** has `HRMSPage.tsx` (401 lines, 6 tabs) and `ERPPage.tsx` (335 lines, 5 tabs),
plus 6 supporting modals. Nav gating via `useFeatures()` / `ModuleKey` works correctly.

### 1.2 The actual problem

The backend is ~85% built; **the UI only exposes about half of it, and mostly read-only.**
Concretely:

**HRMS — endpoints that exist but have NO UI at all**

| Endpoint | Exists in API layer? | UI? |
|---|---|---|
| `POST /hrms/leave/` (apply for leave) | `hrmsApi.applyLeave` ✅ | ❌ no form anywhere |
| `POST /hrms/expenses/` (submit a claim) | ❌ not even in `api/index.ts` | ❌ |
| `GET /hrms/incentives/` (earnings) | `hrmsApi.incentives` ✅ | ❌ no tab |
| `POST /hrms/incentives/compute/` | `hrmsApi.computeIncentives` ✅ | ❌ no button |
| `POST /hrms/payslips/{id}/finalize/` | ❌ missing | ❌ |
| `POST /hrms/attendance/sync/` | ❌ missing | ❌ |
| `DELETE /hrms/employees/{id}/` | ❌ missing | ❌ |
| `GET /hrms/me/` | `hrmsApi.me` ✅ | ❌ never called |
| Leave `cancel` action | supported by URL regex | ❌ no button |

**HRMS — UI gaps in what does exist**
- No filters anywhere (attendance has no month/employee filter; leave/expenses/payslips have none).
- No pagination — every tab renders `data.results` and silently drops page 2+.
- Payroll run is hardcoded to *this* month; you cannot re-run a past month.
- No payslip detail view — `breakdown` JSON is never shown.
- No attendance correction (the `admin` source in `AttendanceSource` is unreachable from the UI).
- Employees table has edit-on-row-click but no deactivate, no search, no reporting-manager view.
- `LeaveBalance` is only shown for the current user, never managed by an admin.

**Sales & Billing (ERP) — gaps**

| Gap | Detail |
|---|---|
| No standalone invoice creation | Invoices can only be born from a Sales Order. `InvoiceItemView` exists but there is no "New invoice" button. |
| Tally export unreachable | `TallyExportView` is live; `erpApi` has no `tallyExport` method. |
| No payments ledger | `PaymentCreateView` works, but payments are never listed anywhere. |
| No sales order detail | `SalesOrderDetailView` exists; the orders tab is a flat list with one button. |
| No delete for customers/products | `RetrieveUpdateDestroyAPIView` supports DELETE; UI has no path to it. |
| No filters/search/pagination | Same problem as HRMS across all five tabs. |
| No dashboard | No receivables ageing, no revenue summary, no GST summary. |

**Recruitment** — does not exist. No app, no models, no feature keys, no UI.

**Access control**
- Only three of five roles are ever considered in the UI: `HRMSPage` checks `admin`/`manager`,
  `ERPPage` checks `admin`/`manager`. `senior_agent` and `readonly` fall through to agent behaviour.
- There is no HR-specific or finance-specific role, so running HRMS today requires
  giving someone **full CRM admin**, which also hands them lead data, agent passwords
  and tenant settings.
- `types/index.ts:31` declares `AgentRole` as `... | 'trainee'` — a role that does not
  exist in `apps/core/constants.py` (the real fifth role is `readonly`). Live type bug.
- Backend permission classes are coarse: `IsTenantAdmin` / `IsManagerOrAdmin` only.

---

## 2. Target architecture

### 2.1 Roles

Add two roles to `apps/core/constants.py :: AgentRole`:

```
HR       = "hr"        # HRMS + Recruitment full control, no CRM admin
ACCOUNTS = "accounts"  # Sales & Billing full control, no CRM admin
```

Hierarchy slots them between `senior_agent` and `manager` for CRM purposes,
but module access is *not* decided by hierarchy — it is decided by a capability map.

### 2.2 Capability map (new, `apps/core/capabilities.py`)

Rather than sprinkling `role in (...)` checks, one declarative table:

```python
CAPS = {
    "hrms.view_all":      [ADMIN, HR, MANAGER],
    "hrms.manage":        [ADMIN, HR],
    "hrms.approve":       [ADMIN, HR, MANAGER],
    "hrms.payroll":       [ADMIN, HR],
    "erp.view":           [ADMIN, ACCOUNTS, MANAGER, SENIOR_AGENT, AGENT],
    "erp.manage":         [ADMIN, ACCOUNTS, MANAGER],
    "erp.invoice_issue":  [ADMIN, ACCOUNTS],
    "erp.invoice_cancel": [ADMIN, ACCOUNTS],
    "ats.view":           [ADMIN, HR, MANAGER],
    "ats.manage":         [ADMIN, HR],
    "ats.interview":      [ADMIN, HR, MANAGER, SENIOR_AGENT],   # interviewers
    "ats.offer":          [ADMIN, HR],
}
```

Backed by a single DRF permission class `HasCapability` (`required_capability = "hrms.manage"`),
and mirrored to the frontend by a new `GET /api/v1/auth/capabilities/` endpoint feeding a
`useCapabilities()` hook, so a button is hidden for exactly the same reason the API would refuse it.

### 2.3 New module

```
ModuleKey.RECRUITMENT = "recruitment"
FEATURES[RECRUITMENT] = [
    ATS_JOB_OPENINGS, ATS_CANDIDATES, ATS_INTERVIEWS, ATS_OFFERS,
]
```

Sellable independently, exactly like HRMS and ERP_SALES — `TenantEntitlement.grant_module`
already handles it once the keys exist.

### 2.4 New Django app — `apps/recruitment/`

| Model | Purpose |
|---|---|
| `JobOpening` | title, department, location, employment_type, openings count, experience range, salary band, JD text, status (draft/open/on_hold/closed), hiring_manager → Agent |
| `PipelineStage` | ordered, per-tenant configurable (Applied, Screening, Interview, Offer, Hired, Rejected), `is_terminal` |
| `Candidate` | name, email, phone, source, current company/CTC, expected CTC, notice period, resume FileField, skills JSON, dedupe on (email, phone) |
| `Application` | Candidate × JobOpening, current stage FK, status, owner, applied_on, rating |
| `ApplicationActivity` | append-only stage-change / note / email log |
| `Interview` | application, round no., scheduled_at, mode (phone/video/onsite), interviewers M2M → Agent, status |
| `InterviewFeedback` | interview × interviewer, per-criterion scores JSON, overall recommendation, comments — one row per interviewer |
| `Offer` | application, CTC breakdown, joining date, status (draft/sent/accepted/declined/revoked), offer letter file |

**Hired → Employee bridge:** `services/onboarding.py :: convert_to_employee(offer)` creates the
`authentication.Agent` (if absent) plus the `hrms.Employee` row, carrying designation,
department, date_of_joining and reporting_to across. This is the piece that makes it
"one company solution" rather than two products sharing a login.

---

## 3. Work plan — phased

### Phase 1 — Access model foundation *(backend + small frontend)*

1. `apps/core/constants.py` — add `HR`, `ACCOUNTS` to `AgentRole` (CHOICES, HIERARCHY, MANAGEMENT_ROLES where relevant).
2. New `apps/core/capabilities.py` — the CAPS table + `has_capability(agent, cap)`.
3. New `apps/core/permissions.py :: HasCapability` DRF class.
4. `apps/authentication/views.py` — extend `/auth/features/` response with a `capabilities` dict
   (or add `/auth/capabilities/`); no migration needed, roles are a CharField with choices.
5. Migration for the `Agent.role` choices change (choices-only, no data change).
6. Frontend: fix `types/index.ts` `AgentRole` (`trainee` → `readonly`, add `hr`, `accounts`);
   add `hooks/useCapabilities.ts`; add the two roles to `AgentsPage.tsx` role dropdown and
   `HRMSSettings.tsx` ROLES array.
7. Replace every `agent?.role === 'admin'` check in `HRMSPage`/`ERPPage` with `can('hrms.manage')` etc.

**Deliverable:** an HR user can be created who sees HRMS + Recruitment and nothing else privileged.

### Phase 2 — HRMS completion

Backend additions:
- `POST /hrms/payslips/{id}/finalize/` — already routed, verify + add `mark-paid`.
- `PATCH /hrms/attendance/{id}/` — new `AttendanceDetailView`, capability `hrms.manage`, forces `source=admin`.
- `DELETE /hrms/employees/{id}/` — soft delete (`is_active=False`, sets `date_of_exit`).
- `POST /hrms/leave-balances/` + `PATCH` — admin allocates balances.
- Filters on every list view: `?employee=`, `?status=`, `?month=`, `?date_from=`/`?date_to=`.
- `GET /hrms/dashboard/` — headcount, present today, pending approvals, month payroll cost.

Frontend — rebuild `HRMSPage.tsx` as a directory of sub-pages rather than one 400-line file:

```
pages/hrms/
  index.tsx              tab shell + capability gating
  DashboardTab.tsx       NEW — headcount, attendance today, pending approvals, payroll cost
  AttendanceTab.tsx      + month/employee filter, pagination, admin edit modal, "Sync from dialer"
  LeaveTab.tsx           + Apply-for-leave modal, cancel own request, balance management (admin)
  ExpensesTab.tsx        + Submit-claim modal with receipt upload, receipt preview
  PayslipsTab.tsx        + month picker for payroll run, payslip detail drawer (breakdown JSON),
                           finalize + mark-paid buttons, print/PDF view
  IncentivesTab.tsx      NEW — earnings by month/employee, "Compute incentives" for a chosen month
  EmployeesTab.tsx       + search, department filter, deactivate, org/reporting view
  EmployeeDetail.tsx     NEW — one employee: profile, salary history, attendance, leave, payslips
  HRMSSettings.tsx       (keep; add leave-balance allocation section)
```

Every table gets: search box, relevant filters, pagination, empty state, and row actions
(view / edit / delete) — the "add + edit option" requirement, applied uniformly.

### Phase 3 — Sales & Billing completion

Backend additions:
- `POST /erp/invoices/` — create a standalone invoice (currently only order-derived).
- `PATCH /erp/invoices/{id}/items/{item_id}/` — edit a draft line (delete exists, edit does not).
- `GET /erp/payments/` — payments ledger, filterable by customer/date.
- `GET /erp/dashboard/` — revenue MTD, outstanding, receivables ageing buckets, top customers.
- `GET /erp/reports/gst-summary/` — GSTR-1-shaped B2B/B2C summary for a month.
- Filters on all list views: `?customer=`, `?status=`, `?date_from=`, `?date_to=`, `?q=`.

Frontend — same split:

```
pages/erp/
  index.tsx              tab shell + capability gating
  DashboardTab.tsx       NEW — revenue, outstanding, ageing, top customers (charts)
  InvoicesTab.tsx        + filters, pagination, "New invoice" builder, issue/cancel from list
  InvoiceDetail.tsx      (keep; add edit-line, print/PDF, payment history, send-by-email)
  OrdersTab.tsx          + filters, order detail drawer, cancel
  QuotationsTab.tsx      + filters, duplicate quotation, send-by-WhatsApp/email
  CustomersTab.tsx       + search, delete, customer detail (invoices, payments, outstanding)
  ProductsTab.tsx        + search, delete, stock adjustment, bulk price update
  PaymentsTab.tsx        NEW — ledger with filters + record payment
  ExportsTab.tsx         NEW — Tally export + GST summary download
```

### Phase 4 — Recruitment (ATS)

Backend — new app scaffolded exactly like `apps/hrms`:
`models.py, constants.py, serializers.py, views.py, api_urls.py, admin.py, permissions.py,
services/{pipeline,onboarding}.py, migrations/0001_initial.py, tests/`.
Registered in `TENANT_APPS` and `config/urls.py` at `/api/v1/recruitment/`.

Endpoints (~24): openings CRUD + publish/close, stages CRUD + reorder, candidates CRUD +
resume upload + dedupe check, applications CRUD + move-stage + bulk-move, activity feed,
interviews CRUD + schedule/reschedule/cancel, feedback submit, offers CRUD + send/accept/decline,
`POST /offers/{id}/convert-to-employee/`, and `GET /recruitment/dashboard/`.

Frontend — new `pages/recruitment/`:

```
index.tsx              tab shell
DashboardTab.tsx       open roles, candidates by stage, interviews this week, time-to-hire
OpeningsTab.tsx        list + create/edit modal + close/reopen
OpeningDetail.tsx      JD, pipeline board for that role, applications
CandidatesTab.tsx      searchable database, resume upload, dedupe warning, bulk import
CandidateDetail.tsx    profile, resume viewer, all applications, activity timeline
PipelineBoard.tsx      drag-and-drop kanban across stages
InterviewsTab.tsx      calendar + list, schedule modal, feedback form, scorecards
OffersTab.tsx          offer list, offer builder with CTC breakdown, "Hire → create employee"
RecruitmentSettings.tsx  pipeline stages, interview criteria templates, offer letter template
```

Nav: new rail item under **Modules**, `/recruitment`, icon added to `Layout.tsx :: I`,
gated on `Module.RECRUITMENT`, plus `PAGE_TITLES` entry.

### Phase 5 — Cross-cutting polish

- **Shared UI primitives** — extract the `Table`, `Pill`, `CELL` patterns currently duplicated in
  `HRMSPage`, `ERPPage` and `HRMSSettings` into `components/DataTable.tsx` + `components/StatusPill.tsx`,
  with built-in sorting, pagination and empty state. Reduces ~300 lines of duplication and makes
  every new table consistent by default.
- **`components/FilterBar.tsx`** — one filter row component used by all 20+ tables.
- **Seed data** — extend `seed_data.py` with leave types, holidays, an incentive rule,
  pipeline stages and a sample opening, so a fresh tenant is usable immediately.
- **Entitlements command** — `apps/plans/management/commands/entitlements.py` picks up
  `recruitment` automatically from `ModuleKey.ALL`; verify and add to `--help` text.
- **Tests** — `apps/recruitment/tests/` (pipeline transitions, offer→employee conversion),
  `apps/hrms/tests/` (attendance correction, leave balance), `apps/erp/tests/` (standalone invoice, ageing).
- **Docs** — update `DB_SCHEMA.md` and `README.md` with the new app, roles and module.

---

## 4. Order of execution and risk

| Phase | Depends on | Risk | Note |
|---|---|---|---|
| 1 Access model | — | **Medium** | Touches every module's permission checks. Do it first so phases 2–4 are written against the final model rather than retrofitted. |
| 2 HRMS | 1 | Low | Mostly additive; existing endpoints keep working. |
| 3 ERP | 1 | Low | Standalone invoice creation is the only new domain logic; GST math is reused. |
| 4 Recruitment | 1, 2 | Medium | New app + migration. The offer→employee bridge needs HRMS Employee stable. |
| 5 Polish | 2, 3, 4 | Low | Refactor after behaviour is proven, not before. |

**Migrations:** three new migrations (core role choices, hrms field additions, recruitment initial).
All tenant-schema; `migrate_schemas` must be run for every tenant on deploy.

**Backwards compatibility:** no endpoint is removed or renamed. Existing `admin`/`manager` users
keep every permission they have today — the new roles only *add* paths.

---

## 5. Rough size

| Phase | Backend | Frontend | Files touched/added |
|---|---|---|---|
| 1 Access model | ~250 LOC | ~150 LOC | 9 |
| 2 HRMS | ~500 LOC | ~1,800 LOC | 18 |
| 3 ERP | ~600 LOC | ~1,900 LOC | 17 |
| 4 Recruitment | ~1,600 LOC | ~2,400 LOC | 26 |
| 5 Polish | ~200 LOC | ~600 LOC | 12 |
| **Total** | **~3,150** | **~6,850** | **~82** |

---

## 6. Open items for you to confirm before Phase 4

1. **Resume storage** — reuse the existing `FileField` + `mediafiles/` setup (same as expense
   receipts), or do you want S3 for resumes?
2. **Interview invites** — should scheduling an interview send an email/WhatsApp to the candidate
   through the existing `apps/communications` provider, or is in-app only enough for v1?
3. **Careers page** — a public application form (`urls_public.py`) for candidates to apply
   themselves is *not* in this plan. Say the word and it becomes Phase 6.
