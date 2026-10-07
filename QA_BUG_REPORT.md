# DialSathi — QA bug report (live site)

**Tested:** easyian.shop, workspace `crm`, signed in as the tenant admin (Business plan, all modules on) · 7 Oct 2026
**How:** every sidebar page and sub-page; every filter, tab, search and date range; every create/edit form opened and checked (not saved); API responses checked for each screen; dark mode; phone width (375 px).
**Not done yet:** anything that saves, sends or deletes — see "Still to test" at the end. Nothing was fixed.

Severity: 🔴 high — wrong data, money, or customers affected · 🟠 medium — a feature doesn't work as shown · 🟡 low — polish / confusing

---

## 🔴 High

| # | Where | What's wrong | Evidence / cause |
|---|---|---|---|
| H1 | Agents | **Alina and pari goyal became deactivated during the test session.** They were active at the start (Agents page showed 3 active). As a knock-on effect: the Assign Lead dialog and the bulk "Assign to agent…" list now offer **only the admin**; all 116 leads are owned by a deactivated agent; the Login Report no longer shows their past days. | Nothing in the test saved anything. Cause unknown — waiting for confirmation that it wasn't done by hand. If it wasn't, something is deactivating agents on its own. |
| H2 | Campaigns | **The "Diwali" WhatsApp campaign says "Sent 106 of 106" but nothing was sent.** WhatsApp isn't connected (Settings → WhatsApp: "Not connected"), so the campaign went through the mock provider and marked everyone "sent". Delivered = 0. | `communications/tasks.py::_get_whatsapp_provider` returns the mock when the config is inactive; neither the launch endpoint nor the scheduler refuses a campaign when no provider is active. |
| H3 | Templates / Campaigns / Lead → WhatsApp | **Template variables are never filled.** The message stored on every lead reads "Hi {{1}} … Get {{2}} … Buy Now: {{3}}". With a real provider, customers would get blank or broken parameters. | `WhatsAppTemplate.render()` uses `variable_mapping`, but no screen sets it. The template form says "map these in the backend". Neither the campaign form nor the single-send form has a mapping step. |
| H4 | Calls, Reports, Dashboard | **Call durations are 0 and "connected" contradicts the outcome.** For example, Pravind's call ran 11:37:19 → 11:37:34 (15 s) with a 7 s recording, but duration = 0. Rows show "Switched Off · Connected", "Busy · Connected", "Already Purchased · No answer". Totals: 800 s of talk time across 418 calls (average 4 s). Every talk-time, average-duration and connection-rate figure is unreliable. | `duration_seconds` isn't derived from `ended_at − started_at` or the recording. `is_connected` isn't tied to the disposition. Dispositions have no "counts as connected" flag; "Positive" mixes up connected with good outcome. |
| H5 | HRMS → Attendance / Payroll | **Sundays are marked Absent** (Sun 4 Oct = ABSENT for pari). Every agent has `working_days = []`, and the Agent edit form has no shift or working-days fields, so nobody can fix it. The October payslip draft also shows **31/31 paid days and no LOP** despite 5 absences in attendance. | `hrms/services/attendance.py`: empty `working_days` means every day is a working day. The draft payslip doesn't refresh when attendance changes. |
| H6 | Sales & Billing → Invoices / Payments | **The customer dropdown in "New invoice" is empty** after you've opened Quotations. The Invoices and Payments customer filters break the same way. | Cache-key clash: `QuotationBuilder.tsx` stores an array under `['erp-customers-picker']`, while `InvoicesTab.tsx` and `PaymentsTab.tsx` read `.results` from that same key. |
| H7 | Login Report | **History disappears when an agent is deactivated.** The last 7 days now show only the admin, and 0 calls, though pari made calls on 30 Sep and 3 Oct. Separately, the admin shows "Not logged in" every day while being signed in, because web sign-ins never count. | The report only lists currently active agents and only reads dialer presence. |
| H8 | Call Queues | **Queue "followup" is assigned only to Aman shaw, who is deactivated**, so nobody can work it. The Edit dialog hides deactivated agents, so saving would silently drop him, and the queue card gives no warning. | — |
| H9 | Agents / HRMS | **HRMS employees stay active when their agent account is deactivated** (pari: agent inactive, employee active). They'll keep being included in payroll runs. | — |

## 🟠 Medium

| # | Where | What's wrong |
|---|---|---|
| M1 | Agents → Edit | The email field is editable but **changes are silently ignored**: `AgentUpdateSerializer` has no `email` field. |
| M2 | Agents → New Agent | The browser autofills the **admin's saved email into "Employee ID"**: Alina's employee ID is `alina@gmail.com`, Aman's is `shiwansh283@gmail.com`. The form needs `autocomplete` attributes, otherwise the admin's saved password can be autofilled as the new agent's password too. |
| M3 | My Profile | "Total logins" shows **undefined** (not in the profile API). "Last active" and "Account created" show raw ISO timestamps (`2026-10-07T13:41:00.677180+05:30`). |
| M4 | Integrations / Settings → WhatsApp | Webhook URLs are shown **relative**, for example `/api/v1/integrations/meta/whatsapp/` and `/api/v1/comms/webhook/whatsapp/interakt/?token=…`. Copying them gives a URL Meta/Interakt can't use. (Meta Lead Ads shows the full URL correctly.) |
| M5 | Settings → Billing | The support contact says **"TeleCRM · support@telecrm.in"**, which is a different company's brand and domain. |
| M6 | Dashboard, Reports, Calls | Stat cards mix today and period: "CONNECTED CALLS **0** · **46.2%** connection rate" and "AVERAGE CALL DURATION … across the period" next to "today" cards. On Reports with "Last 30 days" selected, the cards still say "Calls today". On Calls, the From/To filter doesn't change the cards. |
| M7 | Dashboard "Pipeline", Reports "Conversion funnel" / "Agent performance" | Show **"No pipeline data yet" / 0 leads** for 30 days while 116 leads exist, because they count only leads *created* in the range. Agent performance shows Alina "Leads 0" while she owns 116. |
| M8 | Leads filters (also New/Edit lead, Queues, Campaign audience) | The source list is missing **Instagram, 99acres, Housing.com, MagicBricks, JustDial, Sulekha, TradeIndia, API**. Leads from those sources can't be filtered or picked. |
| M9 | Search | A phone number with spaces (`99302 15251`) or a leading 0 (`09930215251`) finds nothing. The top bar says "Search leads, phone, name, **source**…" but searching "Meta" returns 0. |
| M10 | Lead → Edit | State, Pincode, Address, Do-Not-Disturb and Expected close date are shown on Overview but **can't be edited** anywhere. |
| M11 | Lead detail | "Upcoming follow-ups" lists a follow-up from 3 Oct (overdue) with no overdue mark. Activity shows a raw key: "Lead received via **meta_facebook**". Calls to the same number made before the lead existed aren't shown. |
| M12 | Communications → Send Single Message | Needs a typed **numeric Lead ID**: no search or lead picker. The page header says "WhatsApp, Email & SMS" but there's no Email channel. |
| M13 | Communications → New Template | The provider list (Interakt, AiSensy, Wati, Gupshup) **lacks Meta Cloud API**, which Settings → WhatsApp supports. The template "Test" says "Used 0 times" though the Diwali campaign used it. |
| M14 | Campaigns | There's **no way to open a campaign** to see recipients, failures or replies. The audience has no Batch filter and doesn't say whether DND leads are excluded. |
| M15 | Integrations → Website Widget | The log says 1 lead created on 4 Oct, but its batch (#1) is empty and **no website-source lead exists** (all 116 leads are Meta). Find out where it went. |
| M16 | Integrations → Meta Lead Ads | "Leads received: **366**" versus 116 leads in the CRM. Budget and Company Name are mapped, but they're empty on every Meta lead. Worth checking the mapping is applied. |
| M17 | HRMS (admin) | "Check in / Check out" and "Apply for leave" are offered to the admin, who isn't an employee. These will probably error (not clicked). |
| M18 | Recruitment → Settings | The subtitle says "Pipeline stages **and interview types**", but there's no interview-types section. |

## 🟡 Low / polish

1. Leads → **Clear Filters** doesn't clear the top search box, and the search text stays there on every page you visit afterwards.
2. The Notifications dropdown stays open after you navigate to another page.
3. The sidebar group "**Analytics**" contains Integrations and Settings.
4. Lead names are upper-case on the Dashboard but mixed case on Leads. The source is labelled "Meta - Facebook Lead Ads" in the table but "Meta Lead Ads" in the filter.
5. The Overdue list isn't sorted by due date (3 Oct, 30 Sep, 1 Oct, 28 Sep…).
6. The lead detail tab title is just "Leads" instead of the lead's name.
7. Call charts skip days with no calls (axis 12 Sep → 27 Sep with nothing between), which reads as continuous.
8. Reports → Lead Sources shows empty headers with no empty-state message.
9. Sales & Billing → Exports repeats itself: "Filing aid, not a return. Filing aid only."
10. Recruitment dashboard says "Nothing has been set up yet — set up your pipeline" although stages exist.
11. The customer "State" dropdown shows bare codes (AN, AP…) and lists DN and DD separately (merged into DH in 2020).
12. Login Report says "Live — refreshes every 30 seconds" for past ranges too. "Select dates…" opens with 1–7 Oct after "Last 30 days" was chosen.
13. The recruitment stages API returns stages unsorted (the screen sorts them).
14. Templates show `**bold**` markdown. WhatsApp uses single `*`, so customers would see the asterisks.
15. Custom fields can only be changed by "the DialSathi team" (Settings): an admin can't add one even though the plan allows 100.

---

## What worked

- Every page loads at desktop and phone width (no sideways scrolling), and dark mode reads well.
- Leads: status filter, search (name and phone), overdue, pagination, select-all and bulk bar, all tabs on lead detail, the "lead not found" page.
- Calls: direction, outcome, disposition, recording, search and date filters all match the API; the details drawer works.
- Every form opens with the right fields and closes on Esc/Cancel: lead, follow-up, manual call, queue, agent, password, HRMS (onboard, edit, exit, leave, allocation, claim, attendance correction, incentive rule, payslip view), Sales & Billing (quotation, invoice, customer, product, history), Recruitment (opening, candidate, interview, offer, stage), Settings (disposition, team), Integrations (add, both configure screens).
- No JavaScript errors on any page, and no failed API calls apart from the deliberate "lead 999999" check.
- The plan, the modules and the Web Access setting read correctly from the server.

## Still to test (each needs a save, send or delete)

Create/edit/delete a lead; status changes; notes; follow-ups (schedule and mark done); document upload; manual call log; click-to-call; CSV import and a batch; assigning leads; queue create/pull; agent create/edit/password/deactivate/reactivate; web-access switch with an agent login; recruiter login; HRMS check-in, leave, claim, payroll run/finalize, incentive compute; quotation → order → invoice → payment → GST export; recruitment opening → candidate → interview → offer → onboard; settings saves; WhatsApp test message; campaign draft/launch. These need permission to create clearly-labelled **QA test** records in this workspace, and to avoid real customers' numbers.

---

## Fix status (round 1)

| Item | Status | What changed |
|---|---|---|
| H1 agents deactivated | Investigated | No code path deactivates agents on its own — only the Deactivate button, the Django-admin bulk action or a PATCH. Check Django admin → Audit logs (entity "Agent") for who did it. The deactivate dialog now warns about leads still assigned, queues and HRMS. |
| H2 campaign "sent" without WhatsApp | Fixed | Launch (manual and scheduled) and single sends are refused when WhatsApp isn't connected; if a send ever reaches the placeholder provider, recipients are marked **failed**, not sent. |
| H3 `{{1}}` never filled | Fixed | Templates get a "Fill the variables from" mapping (lead fields, agent name/phone, custom fields). Unmapped templates can't be used for a campaign or send. Provider template name defaults to the template name. Usage count now increments. |
| H4 call duration / connected | Fixed | Call outcomes have "Was the call answered?" (backfilled for existing outcomes); it decides "connected". Connected calls with 0 s take their duration from start/end or the recording. Existing history repaired by migration. Talk time counts connected calls only. |
| H5 Sundays absent / stale payslip | Fixed | Working days default to Mon–Sat (existing agents and past Sunday "absent" rows fixed by migration); agent form has shift and working days. Draft payslips rebuild whenever attendance changes. |
| H6 empty invoice customer list | Fixed | Quotation builder used the same cache key with a different shape. |
| H7 login report history | Fixed | Deactivated agents with activity in the range still appear; web sign-ins show as "Signed in … · not on dialer". Same for the Agent Performance report. |
| H8 queue with deactivated agent | Fixed | Queue cards flag "No active agent" / deactivated members; the edit dialog says they'll be removed on save. |
| H9 HRMS employee with login off | Flagged | Employees list shows **LOGIN OFF**; deactivate dialog reminds to exit them in HRMS. (Not auto-exited: a login switched off isn't always someone leaving.) |
| M1 agent email edit ignored | Fixed | Email is editable with a uniqueness check. |
| M2 autofill into new-agent form | Fixed | autocomplete off / new-password. |
| M3 profile "undefined" | Fixed | Login count returned; dates formatted. |
| M4 relative webhook URLs | Fixed | WhatsApp config now returns absolute URLs. |
| M5 TeleCRM / telecrm.in | Partly | Default name now "DialSathi". **Set your real support email** in Super admin → Global settings (`support_email`) or the `SUPPORT_EMAIL` env var. |
| M6 today vs period cards | Fixed | Calls and Reports cards all describe the same range (Calls page follows its date filter, today by default). |
| M7 empty pipeline | Fixed | Dashboard pipeline shows where all leads stand now; funnel labelled "created in this period"; Agent performance shows "Leads received" + "Owns now". |
| M8 missing sources | Fixed | Source lists match the server (18 sources); removed the invalid "Other". |
| M9 search | Fixed | Phone with spaces / leading 0 / +91, names in any order, source names. |
| M10 lead edit fields | Fixed | State, pincode, address, expected close date, DND editable; clearing a field clears it; source/address/DND saved. |
| M11 lead detail | Fixed | Overdue follow-ups flagged; source label in activity; tab title is the lead's name. |
| M12 single message by lead ID | Fixed | Search-by-name/phone lead picker. |
| M13 Meta Cloud provider / usage | Fixed | Meta Cloud API offered; usage counted. |
| M14 campaign results | Fixed | "Results" dialog per campaign (per-recipient status and failure reason); audience can filter by batch and says how many DND leads are skipped. |
| M15 website lead missing | Not a code fix | The lead was most likely deleted; nothing in the intake path drops it. |
| M16 Meta mapping not applied | Fixed | Mapping keys match Meta's field names loosely ("Company name" ↔ `company_name`). Applies to new leads. |
| M17 admin check-in/leave/claim | Fixed | Shown only to people on the HRMS roster. |
| M18 interview types text | Fixed | Copy corrected. |
| Low items 1–14 | Fixed | Search box sync, bell closes on navigation, "Setup" group, name casing, overdue sorted by due date, continuous chart days, lead-sources empty state, exports copy, recruitment dashboard copy, state names (and GST state-code mismatch CT/TG/OR/UT/DD vs CG/TS/OD/UK/DN — could charge IGST within a state), custom date range starts from the chosen preset, stages sorted. |
| Low 15 custom fields support-only | Not changed | Product decision — say if admins should manage them. |

Deploy: `migrate_schemas` (new: calls 0006, authentication 0007, erp 0002 — they backfill data), then rebuild the web app.
