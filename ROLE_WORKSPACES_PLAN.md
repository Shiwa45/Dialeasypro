# Role Workspaces — Agent Portal & Recruiter Role

**Goal:** an agent can sign in on the web and sees *only their own work* — their
dashboard, the leads assigned to them, their call history. A new **Recruiter**
role sees *only Recruitment*. Everything else stays exactly as it is for admins,
managers, HR and accounts.

## Decisions (confirmed)

| Question | Decision |
|---|---|
| What may an agent do on the web? | **Work their leads** — status, notes, follow-ups, click-to-call, edit details. No creating leads, no messaging, no HRMS on the web. |
| Who gets the agent workspace? | **Agent + Read-only.** Read-only sees the same screens with every write control removed. Senior agents keep their current team view. |
| Recruiter powers | **Full ATS** — openings, candidates, pipeline, interviews, offers. Converting an accepted offer into an HRMS employee stays with **HR/Admin** (it creates payroll records). |
| Can admins switch agent web access off? | **Yes** — tenant setting, default **on**. |

---

## 1. What the audit found

**Agents can already sign in on the web.** The login endpoint has no role check;
the only barrier is a line of text on the login page ("Admin access only").
Once in, an agent gets the full admin sidebar — Agents, Settings, Reports,
Campaigns, Integrations, every module — because the sidebar is gated on the
*plan*, never on the *role*. Most of those screens then fail with 403s or show
tenant-wide numbers.

**Data scoping in the API is mostly right already.** `leads_visible_to`,
`calls_visible_to` and the reports all default to "own rows only" for any role
not explicitly granted more. That is the real security boundary, and it holds.

**But five things are wrong:**

| # | Finding | Impact |
|---|---|---|
| 1 | `WhatsAppConversationListView` uses the inverted default: *"if role == agent, restrict"* | HR, Accounts, Read-only and Senior agents can list **every** WhatsApp conversation in the tenant. A new Recruiter role would inherit the same leak. |
| 2 | No `IsNotReadOnly` on any lead or call write endpoint | A **Read-only** user can change lead status, add notes, schedule follow-ups and place calls. "Read-only" is not enforced anywhere. |
| 3 | No "my performance" endpoint | The agent-performance report is manager-only and plan-gated. The current dashboard calls tenant-wide reports, so an agent's dashboard is either empty or wrong. |
| 4 | Recruitment pickers call `/auth/agents/` (manager/admin only) and `/hrms/employees/` | **HR already gets 403** when choosing an interview panel or hiring manager; a Recruiter would too. The offer's "Reports to" picker needs an HRMS capability a recruiter will never have. |
| 5 | Leads page shows *New Lead / Export / Assign / bulk-select* to everyone | Buttons an agent clicks only to be refused. |

---

## 2. The design: one server-decided "workspace"

The server computes a single value per user and sends it with `/auth/features/`:

| Workspace | Roles | Home |
|---|---|---|
| `full` | admin, manager, senior_agent, hr, accounts | `/dashboard` (unchanged) |
| `agent` | agent, readonly | `/dashboard` → **My Performance** |
| `recruiter` | recruiter | `/recruitment/dashboard` |

The sidebar, the route guard and the landing page all read that one value, so
they can never disagree with each other — or with the server. A URL typed by
hand into the address bar for a screen outside the workspace redirects home
rather than rendering a broken page.

**Hiding a screen is not security** — the API stays the boundary. Every
endpoint an agent or recruiter could call directly keeps (or gains) its own
role check and row scoping.

### Agent workspace

| Screen | Route | Shows | Agent can | Read-only can |
|---|---|---|---|---|
| My Performance | `/dashboard` | Own calls, talk time, connection rate, leads by status, conversions, follow-ups due/overdue, daily trend | — | — |
| My Leads | `/leads` | Leads **assigned to me** | open, filter, search | open, filter, search |
| Lead detail | `/leads/:id` | One of my leads | status, notes, follow-ups, call, edit details | view only |
| Call History | `/calls` | **My** calls | — | — |
| Profile | `/profile` | Own profile, password | edit | edit |

Removed for these roles: New Lead, Export, Assign/Distribute, bulk selection,
the Assigned column, Import, Batches, Queues, Agents, Live Agents, Reports,
Communications, Campaigns, every module, Integrations, Settings.

### Recruiter workspace

Recruitment only: Dashboard, Job Openings, Pipeline, Candidates, Interviews,
Offers, Settings — plus Profile. The **Onboard → HRMS** button is hidden and the
API refuses it (403) for a recruiter.

---

## 3. Backend work

1. **Role** — `AgentRole.RECRUITER = "recruiter"`; choices, hierarchy, migration.
2. **Capabilities** — recruiter added to `ats.view / manage / interview / offer`;
   new `ats.onboard` (admin, hr) guards *convert-to-employee* and *suggest
   employee code*; recruiter is **not** in `crm.view`.
   New `workspace_for(agent)` beside `capabilities_for`.
3. **Web-access switch** — `Tenant.agent_web_access` (bool, default true). The
   web client sends `X-Client: web`; login refuses an agent/read-only user with
   `web_access_disabled` when the tenant has switched it off. `/auth/features/`
   reports it so an already-open session signs out. Admin-only
   `GET/PATCH /api/v1/auth/web-access/`.
   *This is a policy switch for the web client, not a security boundary: the
   API is shared with the mobile app by design, and what an agent can reach
   through it is the same scoped data either way.*
4. **My performance** — `GET /api/v1/reports/my-performance/?days=1|7|30`.
   Always the caller's own numbers; any role; no plan gate.
5. **Fix #1** — WhatsApp conversations scoped through `leads_visible_to`.
6. **Fix #2** — `IsNotReadOnly` on every lead/call/comms write an agent can reach.
7. **Fix #4** — `GET /api/v1/recruitment/people/` (agents for panels and hiring
   managers) and `GET /api/v1/recruitment/reporting-options/` (employees for
   "Reports to"), both on `ats.view`. Fixes HR's existing 403 too.

## 4. Frontend work

1. `useWorkspace()` hook from the features payload.
2. Sidebar per workspace; top-bar lead search hidden for recruiters.
3. `WorkspaceGuard` — per-workspace route allowlist, everything else → home.
4. New **My Performance** dashboard page.
5. Leads page: agent workspace hides New Lead, Export, Assign, bulk select and
   the Assigned column; title becomes *My Leads*.
6. Lead detail: read-only hides every write control; agents can't see a
   reassignment field.
7. Calls page: *My Call History*, no agent filter or column.
8. Login: honest copy, `X-Client: web` header, clear message for
   `web_access_disabled`.
9. Settings: *Allow agents to sign in on the web* toggle (admin).
10. Agents page: **Recruiter** in the role picker (+ types).
11. Recruitment: pickers use the new endpoints; Onboard button needs `ats.onboard`.

## 5. Verification

- Backend tests for: workspace mapping, recruiter capabilities (incl. onboard
  refused), web-access switch at login, my-performance returns only own data,
  read-only write refusal, WhatsApp conversation scoping, the two pickers.
- Full backend suite against Postgres; `makemigrations --check`; `tsc`.

## 6. Deliberately not in this change

- **The mobile app does not know the Recruiter role.** A recruiter who signs in
  to the app would see an empty lead list. Worth blocking there later.
- **HR and Accounts still get the full sidebar**, filtered only by plan. The
  workspace mechanism built here can give them focused ones in a later change.
- **The shared API still lets agents create leads and send messages** — the
  mobile app depends on both. The web simply doesn't offer them.

---

## Addendum — plan gating (added after the first build)

**Request:** agent web access only on selected plans; the Recruiter role only for tenants with Recruitment unlocked.

| Rule | How it works |
|---|---|
| Agent web access is a plan feature | New feature key `agent_web_access` ("Agent Web Panel"). Agents / read-only users may sign in on the web only when the plan (or an add-on entitlement) includes it **and** the tenant switch is on. The plan wins: switch on + feature off = refused. Mobile app unaffected. |
| Which plans get it | Migration `plans/0005` adds the feature to every existing plan: **on** for Business and Enterprise, **off** (but present as a checkbox) for the others. Change per plan in Django admin → Plans. New installs: `setup_initial_data` gives Business/Enterprise every feature. |
| Settings → Web Access | Shows the upgrade screen when the plan lacks the feature; `PATCH /auth/web-access/` returns 402 `upgrade_required`. `GET` returns `available_in_plan`. |
| Recruiter role needs Recruitment | "Has Recruitment" = all four ATS features (same rule as `modules.recruitment` in `/auth/features/`). Without it: the role can't be assigned (create/edit → 400), a recruiter can't sign in on **any** client (403 `recruitment_not_in_plan`), and an open session is signed out with the reason. Existing recruiters can still be edited/re-roled by admins. |
| Open sessions | `/auth/features/` returns `web_access_allowed` + `web_access_message`; the web app signs the person out with that message (plan downgraded, switch off, Recruitment removed). |
| Security fix found on the way | `PATCH /auth/me/` used the admin serializer with no actor — any user could set their own `role` to `admin`. Now uses `AgentSelfUpdateSerializer` (name, phone, timezone, language only), and the admin serializer refuses a role change with no actor. |

Code: `apps/authentication/web_access.py` (`feature_checker`, `refusal_for`, `recruitment_in_plan`, `agent_web_in_plan`), login + features + web-access views, `check_role_in_plan` in serializers. Tests: `apps/authentication/tests/test_workspaces.py`, `apps/plans/tests/test_agent_web_feature_migration.py`.
