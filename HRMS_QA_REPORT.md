# HRMS — QA report

**Tested:** easyian.shop, workspace `crm`, signed in as admin, 9 Oct 2026.
**Covered:** dashboard, employees, attendance (sync, corrections), leave (types, balances, allocation), expenses, incentives (rules, compute), payroll (run, payslip view), and settings (holidays, leave types, incentive rules, salary structures).

**How I tested:**
- **Live:** reproduced on the site.
- **Repro:** reproduced in an automated test against the current code. Each one was a scenario I couldn't safely run on live data, such as finalizing a payslip that can't be undone.
- **Code:** read from the code.

The workspace has one employee (pari goyal, joined 11 Sep, ₹16,000/month structure from 29 Sep) and two active logins. I couldn't sign in as an employee, so the employee side (applying for leave, filing claims, checking in) was tested through the API and in tests.

Severity: 🔴 wrong pay / money · 🟠 broken or wrong behaviour · 🟡 polish

## Fix status (9 Oct 2026)

All findings are fixed in code except H28 (by design, see below) and the company name in H37 (a setting). Not deployed yet. Regression tests: `apps/hrms/tests/test_qa_fixes.py` (35 tests); full backend suite 854 passed; web `tsc` clean.

| # | Fix |
|---|---|
| H1 | Days after the run date are "Still to come": neither paid nor docked. A slip can't be finalized before the month's last day, or if its draft was built before then (re-run first). |
| H2 | Only earnings on a **finalized/paid** slip are frozen. Running payroll recomputes incentives; the nightly recompute also refreshes that month's drafts. |
| H3 | Conversions are counted from any lead activity that moved the lead to Converted, including a "Sale done" call outcome. A repeat call on an already-converted lead isn't counted again. |
| H4, H5 | Each day is paid at the structure in force that day; days before the first structure use the first one. The slip lists the structures used. |
| H6 | Approved claims dated up to the month's end that no slip has paid are included, whatever month they're dated in. |
| H7 | Finalize only from Draft (and only once). |
| H8 | Salary structures: Edit / Remove (refused once a finalized slip used it). Payslips: Reopen (finalized → draft) and Delete draft (releases its incentives and claims). |
| H9 | Components ≥ 0, gross > 0, deductions ≤ gross; one structure per start date. |
| H10 | Nightly sync 00:30 IST, incentive recompute 01:30 IST. |
| H11 | Adding, moving or removing a holiday rebuilds that day's dialer-derived rows. |
| H12 | Not enrolled → 400 "You are not enrolled in HRMS…". |
| H13 | HR can apply leave / file a claim for an employee (Employee picker on web). |
| H14 | Days are counted by the server (working days only); typed days are ignored. Half-day option for a single date (web and app). |
| H15 | Approval refuses full-day leave on days attendance shows worked, naming the dates. Half-day leave leaves the row alone and pays the other half. |
| H16 | Charged to each year's balance (stored on the request); cancelling refunds the same split. |
| H17 | Applying, approving or cancelling leave in a month with a finalized payslip is refused ("reopen that payslip first"). Cancelling rebuilds past days from the dialer. |
| H18 | Refused: switched-off type, before joining, after exit, finalized month, more than a year ahead, no working days in range, overlap, days already worked, insufficient balance per year. |
| H19 | Leave page has a "Leave balances" table for HR (per employee × type, by year); Allocate shows the current figure. |
| H20 | Allocation ≥ 0 and ≥ used; year 2000–2100; used days read-only; a balance with used days can't be deleted. |
| H21 | Quota 0–366. Settings lists switched-off types with "Switch on"; creating a duplicate of a switched-off name says so. |
| H22 | Bulk allocation pro-rates by month for joiners in that year and adds the previous year's remaining days for carry-forward types. |
| H23 | The nightly sync closes a past day that was checked in but never checked out, using the dialer's hours. |
| H24 | Check-out subtracts dialer breaks between check-in and check-out. |
| H25 | "+ Add day" on Attendance (HR). |
| H26 | Employee and date can't be changed on a correction; changing hours without changing status re-derives the status. |
| H27 | Sync asks for confirmation, can't target a future date, and reports rebuilt vs kept rows. |
| H28 | **Not changed** (by design): attendance still comes from the dialer or check-in/out. H23 and "Add day" cover people working off the dialer. |
| H29 | Settings → Policy: full-day / half-day hours. |
| H30 | PAN, IFSC, UAN (12 digits), ESI (10–17), bank account (9–18) validated and normalised; exit ≥ joining; no reporting to self or in a loop. |
| H31 | Claims: not in the future or over a year old, not before joining, at most the policy maximum (default ₹1,00,000), receipt required above the policy threshold (Settings → Policy). |
| H32 | Rates/minimum/cap ≥ 0, revenue share ≤ 100 %, roles must exist; web warns on ₹10,000+ per unit. |
| H33 | Deactivating a rule deletes its earnings no finalized slip has paid; payroll ignores inactive rules. |
| H34 | All pickers load every page (the API caps a page at 100; the employee list and attendance month were also cut at 100). |
| H35 | "Leave awaiting you" excludes your own requests (unless you're the admin, who may approve their own); today's attendance counts active employees only. |
| H36 | Dashboard subtitle includes reimbursements and deductions. |
| H37 | Draft payslips print with a DRAFT watermark. The company name "crm" is a setting: Settings → Company Profile. |
| H38 | Payroll run lists employees with no salary structure separately ("No salary structure") instead of as errors. |

**To deploy:** `python manage.py migrate_schemas` (new `hrms.0002_leave_days_and_policy`), restart Celery beat (new times), rebuild the web app, and run `flutter analyze && flutter test` before the next app build (the Flutter SDK couldn't be run here).

**Also noticed (not changed):** other jobs in `config/celery.py` appear to be written in UTC too (e.g. "9 AM IST" trial check at `hour=3, minute=30`), so they run 5½ hours early. Worth checking separately.

---

## 🔴 Pay and money

| # | Where | Bug | How found |
|---|---|---|---|
| H1 | Payroll run | **Running payroll for the current month pays every remaining day.** October's payroll, run on 9 Oct, paid pari **25 of 31 days** though she was present 1 day: the 20 days still to come were counted as "No record (paid)". The payslip and dashboard show ₹17,903 net for a month that has hardly started. | Live |
| H2 | Incentives | **A draft payslip freezes the month's incentives, usually at ₹0.** Running payroll, even as a draft and mid-month, attaches that month's incentive earnings to the slip. From then on, the nightly recompute and "Compute incentives" both skip them as "already in a payslip". Live: October's "Performance bonus" shows **IN PAYSLIP, 0 units** since 9 Oct. In a test, 5 connected calls made after the draft never appeared on the payslip. | Live + Repro |
| H3 | Incentives | **Sales recorded through the "Sale done / Converted" call outcome don't count** for the Converted-leads or Revenue incentive. The engine only counts a lead converted by hand on the lead page. I introduced this in the call-outcome change last week. | Repro |
| H4 | Payroll | **A new joiner's first month can't be paid.** Payroll looks for a salary structure in force on the 1st of the month. Live: September payroll fails with "EMP-001 has no salary structure effective on 2026-09-01" (joined 11 Sep, structure from 29 Sep). The toast still says "Drafts generated with 1 problem" although no draft was made, and doesn't give the reason. | Live |
| H5 | Payroll | **A pay rise from mid-month is ignored for that month.** Only the structure in force on the 1st is used. | Repro |
| H6 | Expenses → payroll | **A claim dated in a month that has already been paid is never reimbursed.** Payroll only picks up claims dated inside the payslip's month. Example: a claim dated 28 Sep and approved after September was finalized is missing from October's payslip, and stays unpaid forever. | Repro |
| H7 | Payslips | **"Finalize" on a paid payslip turns it back to Finalized** and overwrites the finalized date. There's no status check. | Repro |
| H8 | Payroll | **Mistakes can't be corrected.** A salary structure can't be edited or deleted (only a new one added), and a payslip can't be un-finalized or a draft deleted. A wrong figure on a structure stays in the history. | Live (no edit endpoint) |
| H9 | Salary structures | **Negative pay and impossible deductions are accepted**, e.g. basic **−₹5,000**, or TDS ₹90,000 on a ₹0 salary. | Repro |
| H10 | Attendance sync schedule | **The nightly attendance sync runs at 7 PM, not 12:30 AM.** The schedule was written for UTC (19:00 UTC = 00:30 IST), but the scheduler runs in IST. So a day is only synced at 7 PM the next day. Live: 8 Oct had no attendance row at 1:30 PM on 9 Oct. Payroll run before 7 PM on the 1st pays the month's last day as "No record". The incentive recompute also runs at 8 PM instead of 1:30 AM. | Live + Code |
| H11 | Holidays | **Adding a holiday doesn't change attendance.** I added 2 Oct (Gandhi Jayanti): the day stayed ABSENT and payroll still docked it (LOP went to 7) until I synced that date by hand. Deleting the holiday left the day as HOLIDAY until re-synced. Removed after the test. | Live |

## 🟠 Leave

| # | Bug | How found |
|---|---|---|
| H12 | **Applying for leave or filing an expense as someone not enrolled gives a 500 server error.** The intended message ("You are not enrolled in HRMS…") is never shown. | Live |
| H13 | **HR can't apply leave or file a claim on an employee's behalf.** The Leave page says "Apply above, or wait for your team…" but shows no Apply button to an HR admin who isn't enrolled themselves. | Live |
| H14 | **The number of days is typed freely and isn't checked against the dates.** The web form defaults to 1 whatever range is picked. In a test, 7–12 Sep (6 days) entered as 0.5 was approved: **0.5 day** came off the balance and **6 days** were paid as leave. The app instead counts calendar days, Sundays and holidays included, and has no half-day option. | Repro + Code |
| H15 | **Approving leave wipes a day the employee actually worked**: a present day with 8 h worked becomes "on leave" with 0 h. A half-day leave also marks the whole day as leave. | Repro |
| H16 | **Leave across New Year (30 Dec – 2 Jan) is charged entirely to the first year's balance.** | Repro |
| H17 | **Cancelling approved leave after the payslip is finalized** refunds the balance and deletes the attendance rows, so the finalized payslip no longer matches the records. Nothing stops it. | Repro |
| H18 | **Leave is accepted for a switched-off leave type, for any past date** (e.g. Jan 2020), and for dates before joining. | Repro |
| H19 | **HR can't see anyone's leave balance.** The Leave page only has "Your leave balance", and the Allocate dialog doesn't show current figures. | Live |
| H20 | **Balance admin accepts nonsense**: an allocation of −3 days, year 1890, and "used days" edited directly (set to 20, leaving −8). Reverted after the test. | Live |
| H21 | **Leave types:** a negative annual quota (−5) is accepted. "Removing" a type hides it for good: it can't be switched back on, and a new one with the same name is refused ("already exists"). | Live |
| H22 | **Carry-forward does nothing.** The setting is stored but no code carries balances into the next year. Bulk allocation also gives the full yearly quota to someone who joins mid-year. | Code |

## 🟠 Attendance

| # | Bug | How found |
|---|---|---|
| H23 | **Check-in without check-out counts as a full present day, permanently.** The row becomes "manual", so the sync never corrects it. Live: pari checked in at 1:29 PM today and shows PRESENT with 0.00 h. | Live + Repro |
| H24 | **Manual check-out doesn't subtract breaks.** Break time only comes from the dialer sync. | Code |
| H25 | **A missing day can't be entered.** The Attendance list only offers "Correct" on existing rows; a day with no row can only be created with "Sync from dialer". | Live |
| H26 | **"Correct" can move a row to another employee or date**, and changing worked hours doesn't change the status (8 h 20 m left as ABSENT). | Repro |
| H27 | **"Sync from dialer" runs immediately for the selected date with no confirmation**, and reports "1 row rebuilt" even when it skipped a manual row. | Live |
| H28 | **Automatic attendance only counts time in the auto-dialer.** Anyone working outside it is marked absent every day unless they check in. Live: pari was ABSENT on 1–8 Oct with 0–5 minutes each day. | Live |
| H29 | **The present / half-day thresholds (6 h / 3 h) are fixed in code** and can't be set per company. | Code |

## 🟠 Employees, expenses, incentives

| # | Bug | How found |
|---|---|---|
| H30 | **Employee details aren't validated.** PAN "NOTAPAN", IFSC "XX", UAN "abc", an exit date before the joining date, and someone reporting to themselves are all accepted. | Repro |
| H31 | **Expense claims accept future dates** (2030) and any amount (₹9,99,99,999.99), and no receipt is required. | Repro |
| H32 | **Incentive rules accept negative ₹ per unit, a negative minimum, and roles that don't exist** ("astronaut"). The existing rule pays **₹10,00,000 per conversion** with no warning. A "QA Bad Rule" is left switched off in Settings. | Live |
| H33 | **Earnings from a switched-off rule stay and are paid** at the next payroll run. | Code |
| H34 | **The onboarding agent picker loads only the first 100 users.** | Code |

## 🟡 Polish

- H35: The Dashboard's "Leave awaiting you" counts every pending request, including your own, which you can't approve. "Present / absent today" also counts exited employees' rows.
- H36: The Dashboard's "Net payroll cost ₹17,903" sits under "Gross ₹12,903 · incentives ₹0". The ₹5,000 reimbursement that makes up the difference isn't shown.
- H37: The payslip prints the company as **"crm"**. Set the name in Settings → Company Profile once deployed. A draft payslip also prints without any "DRAFT" mark.
- H38: Exiting an employee leaves them in the next payroll run's error list if they have no salary structure.

---

## Worked correctly

- **Self-approval:** you can't approve your own leave or expense claim.
- **Double-clicks:** they don't approve a request twice.
- **Payslip pro-rating** by calendar days and the loss-of-pay amount are correct: ₹15,999.99 × 25/31 = ₹12,903.22. Earnings lines add up, and the amount in words is right.
- **Mark paid** is refused on a draft payslip.
- **Days before joining** aren't paid, and a leaver's final month is included.
- **Pending leave** in a payroll month is flagged in the payroll result.
- **Exiting an employee** keeps their history; the record isn't deleted.
- **Bulk "Allocate for all employees"** tops balances up and doesn't reduce them.
- **"Sync from dialer"** for a chosen date creates the missing row (8 Oct).

## Not tested on the live site

These all needed a second login or would have changed real records permanently:
- **The employee side:** applying for leave, filing a claim, checking in and out, and the mobile app's "My work" screen.
- **The approval flow:** approving and rejecting leave and claims.
- **Payslip states:** finalizing and marking paid.

The logic behind each of these was exercised in tests instead (H2, H5–H7, H14–H18, H23, H26, H30–H31).

## Data changed during the test

- **8 Oct attendance** for pari was created by "Sync from dialer". This is real data the nightly job hadn't written yet.
- **October's draft payslip** was rebuilt and now includes the 8 Oct absence (net ₹17,387.09).
- **Casual Leave 2026** was allocated to pari: 12 days, none used.
- Left switched off and not removable from the screen: leave type **"QA Negative Leave"** and incentive rule **"QA Bad Rule"**.
- The **2 Oct holiday** was added and then removed; 2 Oct is back to ABSENT.
