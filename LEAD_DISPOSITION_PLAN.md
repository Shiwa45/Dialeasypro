# Lead status vs call disposition: bug report and fix plan

**Tested:** easyian.shop, workspace `crm`, signed in as admin, 8 Oct 2026. I also read the backend, the web app and the Flutter dialer.
**Live data looked at:** 419 calls and 116 leads. I also created 2 test leads, "QA Disposition Test A/B", and logged 7 calls on them.

---

## 1. Why outcomes are wrong today

Three different things are mixed together:

| Concept | What it should mean | What the software does today |
|---|---|---|
| **Call status** | A fact about the call: was it answered? It comes from the SIM call log (duration > 0) or the provider. | The app reads it from the call log, then the server **overwrites** it with whatever the chosen disposition says. |
| **Disposition** (call outcome) | What happened on *this* call. | One flat list of 10. It mixes answered outcomes, unanswered ones and "dialer decides" (DND). Agents see every option whether or not the call connected. |
| **Lead status** (pipeline stage) | Where the lead stands in the sales journey. | It is moved by some dispositions and by the quick-status buttons, with no order between stages. A call can push a lead backwards. |

So an agent whose call was **not answered** (SIM log 0 s) can still pick "Connected – Interested". The server then records a connected call with 0 s of talk time and moves the lead to Interested. **118 of the 419 live calls are "connected" with 0 s.** Aman shaw shows 47 connected calls and a total talk time of **1 second**. Every connection rate and outcome report is built on this data.

---

## 2. Bugs found

Legend: 🔴 wrong data or reports · 🟠 broken flow · 🟡 polish. "Live" means reproduced on easyian.shop; "Code" means confirmed by reading the code.

### Call outcome capture

| # | Where | Bug | Evidence |
|---|---|---|---|
| D1 🔴 | App post-call screen | The disposition list is never filtered by call status. All 10 options show whether the call connected or not. The app's `CallDisposition` model doesn't even read `marks_connected` or `lead_status`. | Code: `dialer_screen.dart`, `models.dart` |
| D2 🔴 | Server | `CallLog.apply_outcome_rules` silently overrides `is_connected` with the disposition's flag. A 0 s call becomes "connected", and a 90 s call marked "Not Reachable" becomes "not connected" but keeps its 90 s. | Live: 118 connected calls at 0 s. A test "Not Reachable" call kept 90 s. |
| D3 🔴 | Web → Log Manual Call | The "Call was answered" box contradicts the disposition and is silently ignored. I logged "Connected – Interested" with the box **unchecked** and it saved as Connected. | Live, lead 1060 |
| D4 🟠 | Web → Log Manual Call | **The call silently fails to save when Duration is left empty.** The server answers 400 ("duration_seconds: A valid integer is required"), but the modal has no error handler, so nothing happens. | Live |
| D5 🟠 | Web → Log Manual Call | After a call is logged, the lead header still shows the old status. The server had already moved the lead to Interested, but the page said New. | Live |
| D6 🔴 | Server and web | A call can be saved with **no disposition**: "No disposition" is an option in the web modal, and the API accepts it. 2 live calls have none. | Live |
| D7 🔴 | Click-to-call / Call back | Creates a call with no outcome, and there is **no way to add the outcome later**: `GET /calls/{id}/` is read-only. In manual mode the agent then logs the call again, so one call counts twice. | Code: `ClickToCallView`, `CallLogDetailView` |
| D8 🔴 | Server signal | Outcome side effects (lead status, auto follow-up) run **only when a call is created** (`if not created: return`). An outcome set afterwards would change nothing. | Code: `calls/signals.py` |
| D9 🟠 | App | `createCall` is retried after a failure with no idempotency key. If the first request saved but its response was lost, the call is saved twice. | Code: `dialer_state.dart` |
| D10 🟡 | API | The create response has no `disposition_name`. | Live |

### Disposition set-up

| # | Bug | Evidence |
|---|---|---|
| D11 🔴 | "Wrong Number" is marked **answered**, so it inflates the connection rate (7 live calls), and the lead stays Attempted. | Live |
| D12 🔴 | "Do Not Disturb" is set to "dialer decides". The live call was counted as connected at 0 s. The lead's DND flag isn't set, and follow-ups can still be booked. | Live, lead 1061 |
| D13 🟠 | "Already Purchased" doesn't change the lead status: the lead stays **Attempted**. | Live |
| D14 🟠 | The Settings page has a three-way "Answered?" choice (Yes / No / Dialer decides). An outcome named "Connected – X" can be marked unanswered. There is no grouping into connected and not connected, and the seeded defaults can be renamed or deleted. | Live |
| D15 🟠 | `seed_dispositions` uses `get_or_create`. **Existing tenants never receive updates**, so the set-up of older tenants stays stale. | Code |

### Lead status

| # | Bug | Evidence |
|---|---|---|
| D16 🔴 | **Outcomes move the lead backwards.** A lead in **Negotiation** became **Follow-up** after a "Callback Requested" call. | Live, lead 1060 |
| D17 🟠 | A **Lost** lead is silently reopened to Interested by a call. That may be wanted, but it isn't logged as a reopen. | Live, lead 1061 |
| D18 🔴 | **"Contacted" is never set** by any outcome: 0 leads are Contacted. A connected call with no status rule (Already Purchased, Wrong Number) leaves the lead at Attempted, which means "never reached". | Live |
| D19 🟠 | Quick-status buttons let anyone set any stage with no reason, including Converted or Lost with no call. My test "conversion" now counts in Reports. | Live |
| D20 🟠 | "Not Interested" is neither active nor final. It's left out of the active count, the pipeline and the final statuses. | Live: the pipeline shows 114 of 116 leads. |
| D21 🟡 | The pipeline donut and funnel also leave out **Follow-up**. The dashboard shows "No pipeline data yet" while still loading. | Live |
| D22 🟡 | Contact count and "Last contacted" go up on **unanswered** calls. | Code: `perform_create` → `log_contact` |
| D23 🟡 | The activity feed doesn't name the outcome ("Call connected — 45s"). The New→Attempted step isn't logged, so the feed reads "attempted → interested" for a lead that was New. | Live |

### Follow-ups and reporting

| # | Bug | Evidence |
|---|---|---|
| D24 🔴 | **Auto follow-ups pile up.** Each outcome books a new one and never closes the previous one. Test lead A has 2 open; lead B has "Not Reachable" and "Interested" follow-ups both open. | Live |
| D25 🔴 | Agent Performance has **no outcome breakdown** (interested, callback, not interested per agent). Its "interested/converted" counts read the current status of leads the agent *owns*. pari goyal called 13 leads owned by Alina and gets 0 for everything. | Live |
| D26 🟠 | The connection rate counts DND and Wrong Number as connected. Talk time is near 0 because of D2. | Live |
| D27 🟡 | No filter or column for "last call outcome" on the Leads list, and the lead page doesn't show the last outcome. | Live |
| D28 🟡 | 406 of 419 calls have no lead link: their leads were deleted and the link was cleared. Per-lead history for those calls is lost. Consider soft delete only. | Live |

---

## 3. The target design

**Rule 1: call status is a fact.** It comes from the SIM call log (duration > 0 means answered) or from the provider. The agent only confirms it when the phone couldn't tell. A disposition never overwrites it.

**Rule 2: dispositions come in two groups.** Each disposition gets a required `category` of `connected` or `not_connected`. The agent sees **only the group matching the call status**, and the server refuses a mismatch.

**Rule 3: lead status moves forward unless the outcome closes the lead.** Stages are ranked:
`new < attempted < contacted < interested / follow_up < negotiation < converted`.
- A connected outcome never moves a lead backwards. A negative outcome (Not Interested, Lost, Invalid) applies at any stage except Converted or Duplicate.
- Any connected call lifts the lead to at least **Contacted**. Any dialled call lifts it to at least **Attempted**.
- Reopening a Lost or Not Interested lead from a call is allowed but logged as "Reopened by call outcome …".

**Rule 4: one open auto follow-up per lead.** A new outcome completes or replaces the previous *auto* follow-up. Manual follow-ups are never touched.

### Proposed default dispositions (seeded for every tenant)

**Connected (call was answered)**

| Disposition | Slug | Lead status | Auto follow-up | Extra |
|---|---|---|---|---|
| Interested | `interested` | Interested | 24 h | positive |
| Call back later | `callback` | Follow-up | 4 h (agent can change) | positive |
| Send details on WhatsApp / email | `send_details` | Follow-up | 24 h | positive |
| Meeting / visit / demo scheduled | `meeting_scheduled` | Negotiation | at the meeting time | positive |
| Sale done / Converted | `converted` | Converted / Won | — | positive |
| Not interested | `not_interested` | Not Interested | — | |
| Already purchased / not required | `already_purchased` | Lost | — | |
| Wrong person / wrong number | `wrong_person` | Invalid* | — | |
| Asked not to call (DND) | `dnd_request` | Lost | — | sets the lead's DND flag and blocks further dialling |
| Language barrier | `language_barrier` | Contacted | — | optional: reassign to a language-matched agent |
| Call dropped mid-conversation | `call_dropped` | Contacted | 1 h | |

**Not connected (call was not answered)**

| Disposition | Slug | Lead status | Auto follow-up |
|---|---|---|---|
| Ringing, no answer | `no_answer` | at least Attempted | 2 h |
| Busy | `busy` | at least Attempted | 1 h |
| Switched off | `switched_off` | at least Attempted | 6 h |
| Not reachable / out of coverage | `not_reachable` | at least Attempted | 4 h |
| Call rejected / cut | `rejected` | at least Attempted | 2 h |
| Invalid / out-of-service number | `invalid_number` | Invalid* | — |
| Voicemail / IVR | `voicemail` | at least Attempted | 24 h |

\* **Invalid** is a new final lead status for junk and wrong numbers, so they stop counting as Lost sales. Alternatively these go to Lost with a reason; see open decisions.

Optional rule, configurable per tenant: after **N consecutive not-connected attempts** (default 6), the lead moves to Lost with the reason "Unreachable" and leaves the queues.

---

## 4. Implementation plan

### Phase 1: backend model and rules
1. `CallDisposition`:
   - Add `category` (`connected` / `not_connected`, required), `is_system` (seeded defaults: slug and category locked, can't be deleted), `sets_dnd` and `closes_lead`.
   - Keep `marks_connected` for one release as a read-only alias derived from `category`, so old app builds keep working.
2. Migration: map `marks_connected` True to connected and False to not_connected. Assign `None` (DND) by slug or name. Anything still unclear goes to "connected" and is flagged for review on the Settings page.
3. `Lead`: add `last_disposition` (FK), `last_call_connected`, `last_dialed_at` (exists), `last_connected_at`, `dial_attempts` and `connected_calls`. `last_contacted_at` and `contact_count` will count **connected calls only** (fixes D22).
4. Add one service, `apply_call_outcome(call)` in `apps/calls/services/outcomes.py`. It is idempotent and does five things:
   - checks that the disposition category matches the call status;
   - applies the stage rules from Rule 3;
   - updates the `last_*` fields and DND;
   - replaces the open auto follow-up (Rule 4);
   - writes **one** activity line, e.g. "Call · Connected · Interested · 45s → status Interested".

   It is called from call create, from the new outcome endpoint and from the webhooks. The `post_save` signal stops doing business logic (fixes D8, D23, D24).
5. `CallLog.apply_outcome_rules`: stop overriding `is_connected` (fixes D2). A connected call with 0 s still gets its duration filled from its timestamps or recording.
6. API:
   - `POST /calls/` requires a disposition for agent-logged calls and returns 400 "This outcome is for answered calls" on a mismatch (fixes D3, D6). During the app transition, a mismatch from an old app build is accepted, with `is_connected` taken from the call log, and is logged.
   - Add `PATCH /calls/{id}/outcome/` to dispose a call created by click-to-call, Call back or a provider (fixes D7). The Calls page gets a "Needs outcome" filter.
   - `GET /calls/dispositions/?category=connected|not_connected`.
   - Accept an optional `client_call_id`, unique per agent, as an idempotency key (fixes D9). Return `disposition_name` (fixes D10).
7. Lead status: in `LeadStatusUpdateView`, require a reason for Lost, Not Interested and Invalid. Converted is allowed for manager/admin only, or with a reason (fixes D19). Add `invalid` to `LeadStatus` and make `not_interested` a final status (fixes D20).

### Phase 2: seed and upgrade dispositions for all tenants
1. Rewrite `seed_dispositions` as an **upsert by slug**:
   - It creates missing defaults, updates the category and rules of system dispositions, and leaves custom ones alone (only their category is backfilled).
   - Old slugs map to new ones. For example, `connected_interested` becomes `interested` and `wrong_number` becomes `wrong_person`. Existing call history keeps its links because rows are renamed, not replaced.
2. Run the upgrade for all tenants from a data migration, so `migrate_schemas` covers every tenant. Keep `python manage.py seed_dispositions --all` for manual re-runs. New tenants are already seeded by `tenants/signals.py`.
3. Backfill per tenant:
   - set `Lead.last_disposition`, `last_connected_at` and the call counts from call history;
   - move leads with a connected call that are still at Attempted up to Contacted;
   - close duplicate open auto follow-ups.

   Historic `is_connected` values are **not** rewritten; see open decisions.

### Phase 3: web app
1. **Log call modal**:
   - Step 1 asks "Was the call answered?" (Yes / No). Step 2 shows only that group's outcomes.
   - The outcome is required, and Duration is required (> 0) when answered.
   - Errors show the server message. The lead, activity and follow-ups refresh after saving (fixes D3, D4, D5).
2. **Lead page**: add a "Last call" chip (outcome · connected/not · when) plus attempts and connected counts. Rename "Quick Status" to "Pipeline stage", with a reason prompt for Lost, Not Interested and Invalid.
3. **Leads list**: add a "Last outcome" column and filter, and a "Never connected" quick filter (fixes D27).
4. **Calls page**: show "Connected / Not connected" and the outcome together. Add a "Needs outcome" filter and a "Set outcome" action.
5. **Settings → Call Dispositions**: two sections (Connected / Not connected), with category required when adding. System rows are locked except name, follow-up hours and active. Remove the "Dialer decides" option (fixes D14).
6. **Dashboard pipeline / funnel**: include Follow-up and Not Interested, count the totals correctly, and show a loading state instead of "No pipeline data yet" (fixes D20, D21).

### Phase 4: Flutter app
1. `CallDisposition.fromJson` reads `category`, `lead_status`, `sets_dnd` and `auto_followup_hours`.
2. Post-call screen:
   - If the SIM log says answered or not answered, the toggle is preset and the list is filtered to that group.
   - If the phone couldn't tell (`source == 'estimate'`), the agent must answer "Was it answered?" first, and only then does the list appear.
   - Flipping the toggle clears the selected outcome (fixes D1).
3. Send `client_call_id` and retry safely (fixes D9). Show the server's mismatch message.
4. "Call back later" opens the follow-up time picker straight away, and the server's auto follow-up is replaced, not duplicated.
5. Lead detail status change in the app uses the same reason rules as the web.

### Phase 5: reports
1. **Agent outcome report**, per agent and date range, built from **calls, not lead ownership** (fixes D25): dials, connected, connection %, talk time, then one column per disposition grouped Connected / Not connected.
2. **Call analytics**:
   - The outcome breakdown is split into the two groups, plus a "No outcome" bucket.
   - The connection rate is based on call status only (fixes D26).
   - A data-quality line flags connected calls with 0 s.
3. **Funnel**: stage counts based on stages reached, from status history, as well as current counts.

### Phase 6: tests and rollout
- Backend tests:
  - category validation and mismatch handling (including the old-app path);
  - forward-only stage rules for every disposition from every stage;
  - DND and Invalid handling;
  - auto follow-up replacement and the outcome endpoint;
  - idempotency;
  - the upsert seeder on a tenant with old and custom dispositions;
  - the backfill.
- Rollout order:
  1. Deploy the backend and run `migrate_schemas`, which upgrades every tenant.
  2. Deploy the web app.
  3. Release the app build.
  4. One release later, remove the `marks_connected` alias and the old-app tolerance.

---

## 5. Decisions needed from you

1. **The default disposition list** (section 3): add, remove or rename anything for your customers' industries, such as real estate or education.
2. **Wrong or invalid numbers**: should they get a new **Invalid** lead status, or go to **Lost** with a reason?
3. **Reopening**: may an answered call move a Lost or Not Interested lead back to Interested, or should only a manager reopen it?
4. **Old call data**: leave the 118 "connected at 0 s" calls as they are (my suggestion), or reclassify them as not connected when there's no recording and duration is 0?
5. **The auto-Lost rule** after N unanswered attempts: on or off by default, and what N?

---

## Test data left in the workspace

- Leads **QA Disposition Test A** (id 1060) and **QA Disposition Test B** (id 1061).
- 7 calls on them, logged today under shivansh mishra. They show in today's call stats.
- Lead A is at Follow-up and lead B at Converted. B was set to Converted while testing whether outcomes can change a converted lead; it counts as 1 conversion in Reports.
- Their auto follow-ups.

---

## Fix status (8 Oct 2026)

All 28 bugs are fixed, using the plan's defaults for the open decisions:
- **Invalid:** added as a new lead status.
- **Reopening:** an answered call may reopen a closed lead, and the reopen is logged.
- **Call history:** old calls are left as they are; nothing is rewritten.
- **Auto-Lost:** the optional rule (Lost after N unanswered dials) is **not** built yet.

**Backend:** 792 tests pass, including 48 new ones in `apps/calls/tests/test_disposition_groups.py`.
- `CallDisposition` gets `category` (connected / not_connected), `is_system` and `sets_dnd`. `marks_connected` is now derived from the category and no longer overwrites a call's status.
- `apps/calls/services/outcomes.py` is the one place a call updates its lead:
  - forward-only stage rules, plus closing outcomes;
  - call counters recomputed from the lead's calls;
  - the DND flag;
  - one open automatic follow-up per lead;
  - one activity line per call.

  It runs on call create (signal), on click-to-call (after the dial) and on the new `PATCH /calls/{id}/outcome/`.
- `POST /calls/`:
  - the outcome is required;
  - the outcome must match the call status (current web and app send `client_call_id` and get a 400 on a mismatch; old app builds are accepted and logged);
  - `client_call_id` makes a retried save return the call already saved;
  - the response includes `disposition_name`.
- Lead model:
  - new fields: `last_disposition`, `last_call_connected`, `last_connected_at`, `dial_attempts`, `connected_calls`;
  - `contact_count` now counts answered calls only;
  - new status `invalid`;
  - Not Interested and Invalid are final statuses.
- Manual status changes: Lost and Invalid need a reason. Converted needs one too, unless a manager or admin sets it.
- Leads list filters: `last_disposition` (id, `connected`, `not_connected` or `none`), `never_connected=true` and `never_called=true`.
- Calls filters: `disposition=none` and `category=`.
- Reports:
  - the funnel returns `pipeline` and `closed` (Follow-up, Not Interested and Invalid are no longer left out);
  - call analytics groups outcomes, with a "No outcome" bucket and a count of answered calls with 0 s;
  - new `GET /reports/agent-outcomes/` credits each call to the agent who made it.
- AI suggestions only offer answered-call outcomes.
- Migrations:
  - `calls/0007` (schema) and `0008` upgrade every tenant's outcomes in place;
  - `leads/0009` (schema) and `0010` backfill the call summary, move answered-but-Attempted leads to Contacted, and close duplicate automatic follow-ups;
  - all four were tested on legacy data;
  - `seed_dispositions` now upserts.

**Web** (type-checks clean):
- The new **Log a call / Set outcome** dialog asks "Answered?" first and then shows only that group. Answered calls need a talk time. Errors are shown, and the lead page refreshes after saving.
- **☎ Call** leaves a "Set call outcome" banner. Calls with no outcome can be fixed from the lead page and the call log.
- The lead header shows the last call (outcome, answered or not, dial count). Quick status is now "Pipeline stage" and asks for a reason where needed. The edit form asks for one too.
- The Leads list has a "Last call" column and filter. The call log has "Call status" and "Outcome" filters, including "Needs an outcome".
- **Settings → Call Dispositions** shows two groups. Built-in outcomes can't be deleted or moved to the other group, there is a "Marks DND" option, and there's no "dialer decides" any more.
- Dashboard pipeline: shows every lead and a loading state. Reports: a new **Call Outcomes** tab, the outcome breakdown split by group, and closed leads in the funnel.

**Flutter app**:
- The post-call screen asks "Answered / Not answered" first. It is preset from the SIM call log and must be chosen when the phone couldn't tell. Only that group's outcomes are offered.
- "Call back later" opens the follow-up picker.
- Each save sends `client_call_id`, and a refused save shows the server's reason.
- Status changes to Lost, Invalid or Converted ask for a reason.

I couldn't compile it here because the Flutter SDK download is blocked. Run `flutter analyze && flutter test` before building. The widget test `test/disposition_dropdown_test.dart` is updated for the new flow.

**Deploy order:**
1. Backend, then `python manage.py migrate_schemas`, which upgrades every tenant's outcomes and backfills leads.
2. Web.
3. App build.

Run `python manage.py seed_dispositions --all` only if you want to re-run the upgrade by hand.
