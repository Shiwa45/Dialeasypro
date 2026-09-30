# DialEasy mobile app — Bug Review

**Scope:** the Flutter agent app (`dialeasypro_flutter`, version 1.1.1): all Dart source (~14,300 lines), the Android manifest and native Kotlin, plus every backend endpoint the app calls.
**Date:** 29 September 2026
**Method:** read the code, and traced each finding to the lines that cause it. Every API path the app uses was resolved against the backend's URL table, and request bodies were checked against the serializers. Nothing has been fixed yet; this is a list for review.

**Confidence labels:**
- **Confirmed:** the code does this; the consequence follows directly.
- **Likely:** the code allows it; the effect depends on the phone or on timing.

## Summary

| Severity | Count |
|---|---|
| Critical | 2 |
| High | 6 |
| Medium | 11 |
| Low | 7 |
| **Total** | **26** |

**Fix first:**
- **APP-C1:** follow-up reminders never show.
- **APP-C2:** call durations and "connected" are wrong, and both feed every call report.
- **APP-H1:** customer call recordings may go to a Cloudinary account an agent chose.
- **APP-H2:** after a logout and login in the same app session, the agent stays "offline" all shift.

Several findings (APP-H3, H4, H5, M6, M7, M8) come from the break-gated auto-dial flow added in versions 1.1.0 and 1.1.1. They are listed plainly with everything else.


## Fix status (29 September 2026)

| Finding | Status | Commit |
|---|---|---|
| APP-C1 Notifications never initialised | Fixed | 94d5b68 |
| APP-C2 Call duration / connected wrong | Fixed — read from the phone's call log | 14d6065 |
| APP-H1 Recordings to agent-chosen Cloudinary | Fixed (app + backend link check) | c2a4b63 |
| APP-H2 Offline after re-login | Fixed | 0f01db8 |
| APP-H3 Multi-select calling broken | Fixed — manual list on a break | 1eaa3bf |
| APP-H4 Manual call during paused queue | Fixed | 1eaa3bf |
| APP-H5 Break during post-call loses the call | Fixed | 41eb0f1 |
| APP-H6 Incoming call hijacks the dialer | Fixed | 2a72db2 |
| APP-M1 Wrong / personal audio matched | Fixed | fb3f329 |
| APP-M2 Call end time not saved (backend) | Fixed | 552d5d6 |
| APP-M3 Calls logged on invisible leads (backend) | Fixed | 552d5d6 |
| APP-M4 Template variables ignored | Fixed (app + backend) | a345711 |
| APP-M5 Unapproved templates offered | Fixed (app + backend) | a345711 |
| APP-M6 Notification taps land on Auto Dial | Fixed — offers "take break & open" | e3764c8 |
| APP-M7 Manual calls counted as break | Fixed | 1eaa3bf |
| APP-M8 Next agent inherits the queue | Fixed | 53ab97f |
| APP-M9 Play Store blockers | Fixed — `flutter build appbundle -P store=play` drops READ_CALL_LOG, MANAGE_EXTERNAL_STORAGE and USE_EXACT_ALARM (app falls back gracefully); signing via key.properties (template added — keystore still to be created) | 9877f0c, b43e52b |
| APP-M10 Quick import bypasses pipeline | Fixed — server import, managers only | 1d95b9c |
| APP-M11 Dial failures silent | Fixed — alert on failure | 0ead51a |
| APP-L1 Server errors hidden | Fixed | 3d62105 |
| APP-L2 Mic recordings of unanswered calls / no retry | Fixed | 666a0fa |
| APP-L3 Native WhatsApp not logged | Fixed | c86b495 |
| APP-L4 Heartbeat after session expiry | Fixed (with H2) | 0f01db8 |
| APP-L5 Search per keystroke | Fixed | 8b9f8d4 |
| APP-L6 Tokens in plain preferences | Fixed — tokens encrypted with a Keystore key; verified-write fallback to plain storage only on phones where that fails; backups off | 8cb9bcb, e3bd9bc |
| APP-L7 Duplicate-phone message | Fixed as far as possible — the lead is named only to someone who can see it; that the number is taken is inherent to refusing duplicates | 777b796 |

---

## Critical

### APP-C1 · Follow-up reminders and all shade notifications never appear — *Confirmed resource missing; effect very likely*
**Where:** `lib/core/services/notification_service.dart`, `init()`, which uses `AndroidInitializationSettings('@mipmap/ic_launcher')`.

**What's wrong:**
- The app has no `mipmap` resources. The launcher icon has always been under `drawable/`, and the built APK contains no `mipmap/` entries at all.
- The notification plugin checks the default icon when it starts. With an icon that doesn't exist, it refuses to start ("invalid_icon").
- `init()` therefore throws before it marks itself ready. Every later `show()` and `scheduleAt()` calls `init()` again, hits the same error, and the caller swallows it into a debug log.

**Consequence:** follow-up reminders, overdue alerts and server notifications (new lead assigned, and so on) are never shown. Nothing on screen says so.

**Fix direction:** a proper white notification icon (e.g. `drawable/ic_stat_notify`) used as the default icon, and a check on a real phone.

### APP-C2 · Call duration and "connected" are wrong on every call — *Confirmed*
**Where:** `lib/core/services/phone_service.dart`, `_startDurationTimer()` and `_onPhoneStateChange()`; `lib/features/dialer/dialer_state.dart`, `_onPhoneEvent()`.

**Problem 1: "connected".**
- `CALL_STARTED` is Android's "line open" signal. For an outgoing call it fires when dialling starts, not when the customer answers.
- The app treats it as "the call connected". So every dialled call, answered or not, is saved with `is_connected = true`.
- The after-call screen's "Was the call connected?" switch starts from that value, so it is always pre-ticked.

**Problem 2: duration.**
- Duration is a Dart timer that adds 1 every second while the app runs.
- During a call the phone's own dialer is on screen and Android freezes this app, so the timer stops.
- Recorded durations are therefore near zero, or whatever ticked before the freeze. Ring time is also counted as talk time.

**Consequence:** every connect-rate, talk-time, average-duration and "connected calls" figure is wrong. That covers the dashboard, Calls/History, Reports, agent performance and the new Login Report. The OEM-recording matcher uses the same numbers (APP-M1).

**Fix direction:**
- Read the finished call from Android's call log after it ends. `READ_CALL_LOG` is already declared, and the log has the real duration; zero means not answered.
- Or compute from timestamps, with "connected" as duration > 0 from that log.

---

## High

### APP-H1 · Call recordings upload to an agent-chosen Cloudinary account that can no longer be changed — *Confirmed*
**Where:** `lib/core/services/call_recording_service.dart`, `_uploadIfNew()`, which reads `cloudinary_name` and `cloudinary_preset` from local settings.

**What's wrong:**
- The Cloudinary voice-notes settings were removed from Profile in 1.1.0. The upload code still reads them.
- On any phone where they were ever filled in, customer call recordings keep going to that Cloudinary account (whichever one the agent typed), and only a link is stored in the CRM.
- The settings can't be seen or cleared from the app any more.

**Consequence:** customer audio can sit outside the company's control. Recordings stop working the day that account's preset changes.

**Fix direction:** always upload through the backend (the existing server-side fallback), and delete the old settings keys on start-up.

### APP-H2 · After logging out and back in, the agent stays "offline" on Live Agents — *Confirmed*
**Where:** `lib/features/work/work_session.dart`, `start()` (which returns early when `state.live` is true); `lib/features/auth/auth_provider.dart`, `logout()`.

**What's wrong:**
- Logout ends the presence heartbeat but never resets the work session, so `live` stays true.
- On the next sign-in without closing the app, the shell calls `start()`. It sees `live == true` and returns without reporting *available* or starting the heartbeat.
- The same happens when a session expires and the agent signs in again.

**Consequence:** the agent works all shift while the board and the Login Report show them offline. Their dialling is still reported, but idle time is lost.

**Fix direction:** call `workSessionProvider.end()` (or reset its state) on logout and on session expiry.

### APP-H3 · "Call selected leads" from the Leads list does nothing and shows an endless spinner — *Confirmed*
**Where:** `lib/features/leads/leads_list_screen.dart`, `_startQueueDialer()`; `dialer_state.dart`, `startQueue()`.

**What's wrong:**
- The Leads tab opens only on a break. Since 1.1.1, `startQueue()` refuses to start while on a break.
- The Leads screen ignores the refusal and pushes `/dialer`. The dialer is still idle and shows a loading spinner that never ends.

**Consequence:** multi-select calling can't be used at all.

**Fix direction:** decide whether bulk manual calling belongs on a break. If it does, allow this path. If not, hide the action; either way, never open the dialer when the start was refused.

### APP-H4 · A manual call during a paused queue ends the break on the board and releases the wrong lead — *Confirmed*
**Where:** `dialer_state.dart`, `startSingleCall()`.

**Sequence:**
1. An agent pauses a server queue and takes a break.
2. They call a lead from its page.
3. `startSingleCall()` replaces the dialer state but keeps `_sessionActive` and `_serverQueueId` from the queue.

**Consequence:**
- The manual call reports *on call*, then *available*, to the server. The break ends on Live Agents while the app still shows the agent on break, so the Login Report splits the time wrongly.
- Closing the dialer calls `stop()`, which releases the manually called lead from a queue it was never in.
- The lead that was actually locked in the queue stays locked until its timeout.

**Fix direction:** keep a manual call's state separate from the queue, or stop and release the queue properly first.

### APP-H5 · Taking a break during the post-call step lets the call be thrown away — *Confirmed*
**Where:** `work_session.dart`, `takeBreak()`; `dialer_state.dart`, `goOnBreak()`. Both refuse only while dialling or in a call.

**What's wrong:**
- On the post-call screen, a break moves the dialer to *paused*.
- From *paused*, the close button and the back button allow leaving the dialer (the "dispose first" guard only checks `postCall`).
- Leaving calls `stop()`, and the finished call is never saved.

**Consequence:** calls missing from every report and from the lead's history. The lead also stays locked until its timeout.

**Fix direction:** refuse a break until the outcome is saved.

### APP-H6 · An incoming call during an auto-dial session overwrites the current call — *Likely*
**Where:** `phone_service.dart` and `dialer_state.dart`, `_onPhoneEvent()`.

**What's wrong:** every phone event is applied to the current dialer call, whatever the number. A customer calling back while the agent is on the post-call screen does this:
1. `CALL_STARTED` flips the dialer back to the in-call view.
2. The end of that call overwrites the saved duration and end time.
3. The outcome is then saved against the wrong call's numbers.

**Fix direction:** ignore events whose number doesn't match the dialled number, and ignore any events after the call ended.

---

## Medium

### APP-M1 · Recordings can be matched to the wrong call, or pick up personal audio — *Confirmed*
**Where:** `call_recording_service.dart`, `_findRecordingFile()` and `_candidateDirs`.

**What's wrong:**
- A file with no phone number in its name is accepted on time alone: modified within 70 seconds of the calculated call end, which scores ≥ 20.
- The scanned folders include `Sounds`, `Music/Recordings` and `Recordings/Voice Recorder`, which hold voice memos and personal recordings.
- The calculated call end uses the wrong duration from APP-C2.

**Consequence:** a personal recording, or a different call's recording, can be uploaded and attached to a customer's call.

**Fix direction:** require the number match, or a narrow window around the real call-log times, and drop the non-call folders.

### APP-M2 · Call end times from the app are never stored — *Confirmed (backend)*
**Where:** `apps/calls/serializers.py`, `CallLogCreateSerializer.Meta.fields`, which has no `ended_at`.

The app sends `ended_at` with every call, and the serializer silently drops it. Every app-made call has an empty end time.

### APP-M3 · Any agent can log a call against any lead — *Confirmed (backend)*
**Where:** `apps/calls/views.py`, `CallLogListCreateView.perform_create()`.

**What's wrong:** creating a call never checks that the agent may see `lead`. A call posted for someone else's lead still:
- marks it worked;
- advances *new* to *attempted*;
- clears its queue lock;
- adds activity to its history.

This is the same kind of gap as the click-to-call issue (HIGH-4) fixed in the CRM review.

### APP-M4 · WhatsApp template variables typed by the agent are ignored, and the record doesn't match what was sent — *Confirmed*
**Where:** `lib/features/communications/whatsapp_send_screen.dart`; backend `send_single_whatsapp`.

**What's wrong:**
- The screen asks the agent to fill `{{1}}`, `{{2}}`, and so on, and sends the filled-in text plus `template_id`.
- For a template, the backend ignores that text and fills the variables from the lead itself (`_extract_variables`).
- It then stores the agent's typed text as the message content.

**Consequence:** the variables the agent typed never reach the customer, and the CRM shows a message the customer didn't receive.

### APP-M5 · Unapproved WhatsApp templates are offered — *Confirmed*
**Where:** `whatsapp_send_screen.dart`, line 13: `listTemplates(approvedOnly: false)`.

Agents can pick pending, rejected or switched-off templates. The provider rejects them, and the app only says "Send failed" (see APP-L1).

### APP-M6 · Tapping a reminder or notification lands on Auto Dial instead of the lead — *Confirmed*
**Where:** `reminder_plan.dart` (route `/leads/{id}`); `app.dart` break-gate redirect.

While working (not on a break), `/leads/...` isn't allowed, so every notification tap is redirected to Auto Dial and the lead is never shown. This takes effect once APP-C1 is fixed and notifications appear.

**Fix direction:** allow read-only lead pages, or offer "take a break to open this lead".

### APP-M7 · Manual calls made on a break count as break time in the Login Report — *Confirmed (design gap)*
Manual calls and WhatsApp are only reachable on a break, and single calls report no presence. So all manual work is recorded as *break*, and the report can't separate real breaks from manual calling.

**Fix direction:** report *on call* for manual calls too, or add a separate "manual work" status.

### APP-M8 · The next agent on the same phone inherits the previous agent's queue — *Confirmed*
**Where:** `auth_provider.dart`, `logout()`, which never stops or clears `dialerProvider`.

After agent A logs out mid-queue:
- agent B sees "Return to active queue" for A's queue and can dial from it;
- A's locked lead stays locked until its timeout;
- A's persisted break flag is cleared, but the dialer is not.

### APP-M9 · Play Store would likely reject this build — *Confirmed (release blocker, if published there)*
**Where:** `android/app/src/main/AndroidManifest.xml`; `android/app/build.gradle`.

**Restricted permissions:** each of these needs a special Play declaration and is normally allowed only for certain kinds of app:
- `READ_CALL_LOG` and `PROCESS_OUTGOING_CALLS` (default dialer apps only);
- `MANAGE_EXTERNAL_STORAGE` (file managers and similar);
- `USE_EXACT_ALARM` (alarm and calendar apps).

**Signing:** release builds use the debug signing key. Moving to a real key later forces every phone to uninstall and reinstall.

This doesn't matter for direct APK installs, but decide before any Play submission.

### APP-M10 · The mobile quick-import bypasses the import pipeline — *Confirmed*
**Where:** `lib/features/leads/lead_import_screen.dart`, `_import()`.

**What's wrong:**
- It creates one lead per request: no batch (batch names are mandatory on the web), no import record and no duplicate rule.
- Rows skipped at parse time (short phone numbers) aren't listed.
- Failures give no reason; the most common is the "already exists" duplicate.
- Leaving the screen mid-import keeps the loop running and calls `setState` after the screen has closed.

**Fix direction:** upload through the backend import endpoint, or remove the mobile importer.

### APP-M11 · Dial failures leave the queue waiting silently — *Confirmed (partly addressed in 1.1.1)*
The 1.1.1 fix returns a failed dial to the lead preview with a message. But in queue mode the auto-advance timer is cancelled, and nothing moves the queue on until the agent notices. On an unattended phone the queue just stops.

**Fix direction:** show a clear banner, and offer a retry or skip.

---

## Low

### APP-L1 · Server error reasons are hidden behind generic messages — *Confirmed*
These catch the error and show a fixed text, although the backend explains the problem:
- leave request: "Could not submit the request" (hides "Insufficient balance…" and overlapping leave);
- expense claim: "Could not submit the claim";
- leave cancel: "Could not cancel";
- lead status change: "Update failed";
- note: "Failed";
- WhatsApp: "Send failed".

`ApiClient.errorMessage()` already turns server replies into readable text.

### APP-L2 · Microphone fallback recordings: unanswered calls uploaded, failed uploads never retried — *Confirmed*
**Where:** `call_recording_service.dart`.

- Mic capture starts at dial time, so an unanswered call produces a "recording" of ringing, which is uploaded if it's over 4 KB.
- A failed mic upload keeps the file but never queues it for retry (only OEM matches are queued), and it stays in the temp folder.

### APP-L3 · Messages sent through native WhatsApp leave no trace in the CRM — *Confirmed*
`sendNative()` only opens WhatsApp. No activity or message is logged on the lead, so managers can't see that contact happened.

### APP-L4 · The heartbeat keeps running after the session expires — *Likely*
When a refresh is refused, the app goes to the login screen but the heartbeat timer is never stopped. Every 25 seconds it retries: a 401, then a refresh attempt, then another session-expired callback. This continues until the next login.

### APP-L5 · Lead search fires a request on every keystroke — *Confirmed*
**Where:** `leads_list_screen.dart`, line 121.

There's no debounce, so typing a 10-digit number sends 10 requests. Slower responses can arrive last and show results for an older search.

### APP-L6 · Tokens are stored in plain app preferences — *Confirmed (known trade-off)*
Access and refresh tokens are in `SharedPreferences`, not encrypted storage. The code comment explains why (unreliable secure storage on some phones). With the 30-day refresh token, a rooted or backed-up phone exposes a long-lived session.

### APP-L7 · The duplicate-phone error reveals leads the agent can't see — *Confirmed (backend)*
Creating a lead with an existing number returns "A lead with this phone number already exists", even when that lead belongs to someone the agent can't see. Minor, but it confirms who is already a customer.

---

## Checked and found sound

- **API paths:** all 49 paths the app calls exist on the backend, and request bodies for calls, click-to-call, WhatsApp send, leads and follow-ups match their serializers.
- **Login and sessions (1.1.x):** no login flicker; the session ends only on a refused refresh token; workspace resolution uses production (`easyian.shop`) by default.
- **Release networking:** HTTPS only (no cleartext in release builds).
- **Dates and times:** shown in local time (IST); follow-ups are sent in UTC; HR dates are sent as plain dates.
- **Number parsing:** dashboard, report and call-stat values match their types, with averages rounded server-side.
- **Leads:** new leads default to the creating agent; lead status values match the backend.
- **Permissions and first run:** report endpoints are open to agents, gated by plan features; the first-run setup can be skipped, so it doesn't trap agents.
