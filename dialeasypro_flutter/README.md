# DialEasypro — Mobile Agent App

**Auto-dialer CRM for Indian sales teams. NeoDove / GoDial-style mobile app powered by the TeleCRM (Django) backend.**

Built with Flutter (Dart 3), Riverpod, GoRouter, and a neobrutalist design language.

---

## ✨ FEATURES

### Calling
- **Direct auto-dial** — Calls go straight to the OS dialer and connect; no extra "tap to call" step on Android (`CALL_PHONE` permission).
- **Auto-dialer queue** — Load a list of leads, the app dials them one after another with mandatory disposition between calls.
- **Power Dialer presets** — One-tap queues for Overdue Follow-ups, Hot Leads, New Leads, Interested.
- **Custom selection mode** — Multi-select leads from the list to build a queue.
- **Live call timer** — Visual MM:SS during the call, kept on screen.
- **Wake lock** — Screen stays on during calls.
- **Auto-next** — 2-second pause between calls; pause/resume/skip controls.

### Call Disposition
- **Mandatory** — Cannot proceed to the next call without disposing the current one.
- **Positive / Negative** dispositions with color coding.
- **Connected / Not Answered** toggle.
- **Notes** field per call.
- **Auto-follow-up scheduling** — Pick +1hr / Tomorrow / Custom date-time.
- **Disposition-driven follow-ups** — Some dispositions automatically schedule a follow-up after N hours (configured on backend).
- **Voice notes** — Record during/after a call, uploaded to Cloudinary, attached to the call log.

### WhatsApp (Dual Mode)
- **Native mode** — Opens device WhatsApp app (works without API integration).
- **Cloud mode** — Sends via your organization's WhatsApp Cloud API (Interakt / AiSensy / Meta WBA) through the backend.
- **Template picker** — Approved templates with `{{1}}` `{{2}}` variable filling.
- **Custom messages** for one-off conversations.
- **Per-agent preference** — Each agent picks their default mode in Profile.

### Lead Management
- **Filterable list** by status, priority, source, overdue flag.
- **Search** by name/phone.
- **Lead detail tabs**: Overview · Notes · Follow-ups · Calls.
- **Inline status change** chips.
- **Quick add note** input.
- **Schedule follow-up** with type/when/notes.
- **Complete follow-up** with one tap.

### Reports
- Daily activity (new leads, calls made, follow-ups due).
- Pipeline funnel with conversion percentages.
- Call analytics — 30-day trend line chart (total vs connected).

---

## 🏗️ ARCHITECTURE

```
lib/
├── core/
│   ├── theme/                  # Colors, typography, theme
│   ├── widgets/                # Reusable UI widgets (BrutalButton, BrutalCard, etc.)
│   ├── services/               # Cross-cutting services
│   │   ├── phone_service.dart        # Direct dial + call state monitoring
│   │   ├── whatsapp_service.dart     # Native + Cloud send
│   │   ├── recording_service.dart    # Voice notes + Cloudinary upload
│   │   └── permissions_service.dart  # Runtime permissions
│   └── utils/                  # Formatters, validators
├── data/
│   ├── models/                 # Domain models (Lead, Agent, Call, etc.)
│   └── services/               # API client + repositories
└── features/
    ├── auth/                   # Login + auth state
    ├── dashboard/              # Home with KPIs and quick actions
    ├── leads/                  # List, detail, form
    ├── dialer/                 # Auto-dialer flow (state + screens)
    ├── calls/                  # Call log
    ├── communications/         # WhatsApp send (dual mode)
    ├── profile/                # Profile + settings
    └── reports/                # Charts + analytics
```

### State Management
- **Riverpod** (StateNotifierProvider for auth & dialer, FutureProvider.autoDispose for data fetching).
- **GoRouter** for navigation with auth-aware redirect.

### Networking
- **Dio** with JWT Bearer interceptor and auto-refresh on 401.
- Base URL configurable via `--dart-define API_BASE_URL=https://api.yourdomain.com`.

### Persistence
- `flutter_secure_storage` for JWT tokens.
- `SharedPreferences` for user preferences (WhatsApp mode, Cloudinary config).
- `Hive` initialized for future offline caching.

---

## ⚠️ HONEST TECH NOTES

### Direct Dialing
- **Android**: Works as advertised. The app uses `flutter_phone_direct_caller` which calls Android's `Intent.ACTION_CALL` directly when `CALL_PHONE` permission is granted. No "tap call to confirm" step.
- **iOS**: Apple does **not** allow apps to initiate a call without showing the system confirmation. We fall back to launching the dialer pre-filled with the number; the user has to tap call.

### Call Recording
This is the hard truth nobody else tells you:

**Android 10+ blocks third-party apps from recording cellular call audio** (security restriction in `MediaRecorder` / `AudioRecord`). Apps that claim to do this on the Play Store either:
1. Use accessibility-service workarounds that break with every Android update, or
2. Don't actually work on newer devices.

**The right way to record calls in a production CRM** is server-side recording through your telephony provider:
- **Exotel**, **Knowlarity**, **MCUBE**, **Twilio**, **Plivo** — all support click-to-call APIs that route the call through their PBX, record server-side, and return a recording URL.
- The agent presses CALL in DialEasypro → app hits the backend `click-to-call` endpoint → backend triggers the provider → provider calls the agent → connects to the lead → records → uploads to your S3/Cloudinary → URL stored in `CallRecording.playback_url`.

**What this app DOES record locally**: Voice notes — short audio memos the agent makes during or after the call (e.g., "Customer wants demo on Friday at 3pm"). These use the standard microphone and are uploaded to your Cloudinary unsigned upload preset.

To enable voice-note Cloudinary uploads:
1. Create a Cloudinary account.
2. Settings → Upload → create an unsigned upload preset (e.g., `voice_notes_unsigned`).
3. In the DialEasypro app, go to Profile → Cloudinary → enter your cloud name and preset.

### WhatsApp Cloud API
"Cloud mode" sends through the backend's `POST /api/v1/comms/whatsapp/send/` endpoint. Make sure the backend has:
- A `WhatsAppConfig` row with your Interakt/AiSensy/Meta WBA credentials.
- Approved templates seeded in `WhatsAppTemplate`.

---

## 🏢 MULTI-TENANT SUPPORT

The Django backend uses **django-tenants** with schema-based isolation — each customer organization gets its own subdomain and Postgres schema. The Flutter app is fully multi-tenant aware.

### How agents connect to their workspace

On first launch, the login screen asks for **three** things:
1. **Workspace** — your organization's identifier (e.g. `acmecorp` for `acmecorp.dialeasypro.com`)
2. **Email** — the agent's login
3. **Password**

The app resolves the workspace to a full API URL using these rules (first match wins):
1. If the **Custom API URL** field (Advanced section) is set → use that directly. Useful for self-hosted deployments.
2. If the workspace starts with `http://` or `https://` → use as-is.
3. If the workspace contains a dot (e.g. `crm.acmecorp.com`) → treat as a full domain → `https://crm.acmecorp.com`.
4. Otherwise treat as a subdomain → `https://{workspace}.{ROOT_DOMAIN}`.

Where `ROOT_DOMAIN` defaults to `dialeasypro.com` but can be overridden at build time:
```bash
flutter run --dart-define=ROOT_DOMAIN=mycrm.io
```

### What gets sent on each request

When an agent is signed into workspace `acmecorp`:
- Base URL: `https://acmecorp.dialeasypro.com/api/v1`
- The **Host** header is `acmecorp.dialeasypro.com` (set automatically by Dio from the URL) — django-tenants reads this and routes to the `acmecorp` schema.
- The app also sends `X-Tenant: acmecorp` and `X-DTS-Schema: acmecorp` for backends with header-based middleware fallback.
- `Authorization: Bearer <jwt>` — the JWT issued by the tenant.

### Test connection (Advanced)

The login screen has a "Test" button (under Advanced) that pings the workspace before login. It hits `GET /api/v1/auth/tenant-info/` with a 10s timeout and reports specific errors:
- "Workspace not found" (404)
- "Cannot reach this workspace" (DNS/SSL failure)
- "Connection timed out" (network issue)

### Switching workspaces

Profile → Workspace card → "Switch Workspace" button:
- Clears tokens
- Clears tenant config
- Returns to the login screen with empty workspace field

### Local development

For a local Django backend, leave the workspace field empty and put the dev URL in the Custom API URL field:
- Android emulator: `http://10.0.2.2:8000`
- iOS simulator: `http://localhost:8000`
- Physical device on same WiFi: `http://192.168.1.50:8000`

You'll also need to add your tenant's domain to `TENANT_LIMIT_SET_CALLS` in Django settings, OR use a tenant whose domain matches `10.0.2.2` in the local DB (django-tenants resolves by domain).

### Backend setup (Django side)

Make sure the public-schema has a `Tenant` row matching each workspace's domain:
```python
# Django shell
from tenants.models import Tenant, Domain
t = Tenant.objects.create(
    schema_name='acmecorp',
    name='Acme Corp',
    paid_until='2030-01-01',
)
Domain.objects.create(
    domain='acmecorp.dialeasypro.com',
    tenant=t,
    is_primary=True,
)
```

Then run `python manage.py migrate_schemas --tenant` to migrate the new schema.

### Recommended backend endpoint for "Test Connection"

To make the workspace probe more useful, the backend should expose:

```python
# tenants/views.py
@api_view(['GET'])
@permission_classes([AllowAny])
def tenant_info(request):
    """Lightweight, unauthenticated tenant resolver test."""
    from django_tenants.utils import get_tenant
    tenant = get_tenant(request)
    return Response({
        'schema': tenant.schema_name,
        'name': tenant.name,
        'is_active': True,
    })

# In tenants/urls.py:
path('api/v1/auth/tenant-info/', tenant_info, name='tenant-info'),
```

If the request hits a domain not registered with a tenant, django-tenants returns 404 — which the app surfaces as "Workspace not found."

---

## 🚀 SETUP

### Prerequisites
- Flutter SDK ≥ 3.16 (Dart ≥ 3.2)
- Android Studio / Xcode for native builds
- A running TeleCRM backend (see the backend repo)

### Steps

```bash
# 1. Extract this zip and cd into it
cd dialeasypro_flutter

# 2. Install Flutter dependencies
flutter pub get

# 3. Download fonts (see assets/fonts/README.md)
cd assets/fonts
curl -sL "https://github.com/floriankarsten/space-grotesk/raw/master/fonts/ttf/SpaceGrotesk-Regular.ttf" -o SpaceGrotesk-Regular.ttf
curl -sL "https://github.com/floriankarsten/space-grotesk/raw/master/fonts/ttf/SpaceGrotesk-Medium.ttf" -o SpaceGrotesk-Medium.ttf
curl -sL "https://github.com/floriankarsten/space-grotesk/raw/master/fonts/ttf/SpaceGrotesk-SemiBold.ttf" -o SpaceGrotesk-SemiBold.ttf
curl -sL "https://github.com/floriankarsten/space-grotesk/raw/master/fonts/ttf/SpaceGrotesk-Bold.ttf" -o SpaceGrotesk-Bold.ttf
curl -sL "https://github.com/googlefonts/dm-fonts/raw/master/Sans/Exports/DMSans-Regular.ttf" -o DMSans-Regular.ttf
curl -sL "https://github.com/googlefonts/dm-fonts/raw/master/Sans/Exports/DMSans-Medium.ttf" -o DMSans-Medium.ttf
curl -sL "https://github.com/googlefonts/dm-fonts/raw/master/Sans/Exports/DMSans-SemiBold.ttf" -o DMSans-SemiBold.ttf
cd ../..

# 4. Run on Android (with your defaults for SaaS root domain)
flutter run --dart-define=ROOT_DOMAIN=dialeasypro.com

# For a custom branded deployment:
flutter run --dart-define=ROOT_DOMAIN=mycrm.io --dart-define=API_BASE_URL=https://api.mycrm.io

# For local development against an Android emulator hitting a Django dev server:
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000

# 5. Build release APK
flutter build apk --release --dart-define=ROOT_DOMAIN=dialeasypro.com
```

### Backend Pairing
- Make sure agents are seeded: `python manage.py createsuperuser` (admin) or create via Django admin / superadmin panel.
- Test login from the app using the agent's email + password.
- Seed at least one `CallDisposition` (e.g., "Interested", "Not Interested", "Callback") in the tenant schema, otherwise the disposition view will be empty.

---

## 🎨 DESIGN SYSTEM

### Colors
- **Primary yellow** `#FFE17C`
- **Dark** `#171E19`
- **Cream** `#FFFBEE` (subtle accents)
- Status-coded leads (info/success/warning/error/purple/teal/orange).

### Typography
- **Headings/buttons**: Space Grotesk (700)
- **Body**: DM Sans (400/500)
- **Numbers/phone/IDs**: monospace

### Components
- 2-3px black borders everywhere.
- Solid color shadows offset by 3-6px.
- Press animation: shadow shrinks + element translates down-right.
- Haptic feedback on every primary interaction.

---

## 📁 KEY FILES

| File | Purpose |
|---|---|
| `lib/main.dart` | Entry: orientation, Hive, PhoneService.init, Cloudinary config |
| `lib/app.dart` | GoRouter routes + bottom-nav shell |
| `lib/features/dialer/dialer_state.dart` | Auto-dialer queue state machine |
| `lib/features/dialer/dialer_screen.dart` | Active dialer UI (pre-call → in-call → disposition → next) |
| `lib/features/dialer/queue_starter_screen.dart` | Preset queues + custom selection entry |
| `lib/core/services/phone_service.dart` | Direct dial + phone state monitoring |
| `lib/core/services/whatsapp_service.dart` | Native (wa.me) + Cloud (backend API) |
| `lib/core/services/recording_service.dart` | Voice note recording + Cloudinary upload |

---

## 🔐 PERMISSIONS

### Android (declared in `android/app/src/main/AndroidManifest.xml`)
| Permission | Purpose |
|---|---|
| `CALL_PHONE` | Direct dial without tap-to-confirm |
| `READ_PHONE_STATE` | Detect call started/ended/ringing |
| `READ_CALL_LOG` | (optional) Sync existing calls |
| `RECORD_AUDIO` | Record voice notes |
| `POST_NOTIFICATIONS` | Follow-up reminders |
| `READ_CONTACTS` | Optional contact import |
| `WAKE_LOCK` | Keep screen on during calls |

### iOS (declared in `ios/Runner/Info.plist`)
- `NSMicrophoneUsageDescription` — voice notes
- `NSContactsUsageDescription` — contact import
- `LSApplicationQueriesSchemes` — tel, whatsapp, sms, mailto

---

## 🧭 NAVIGATION MAP

```
/login
/dashboard (tab) ─── BIG auto-dialer CTA, KPIs, recent leads
/leads (tab)
  ├── ?select=true        → multi-select mode (queue picker)
  ├── /leads/new          → create lead
  ├── /leads/import       → CSV import (admin web)
  ├── /leads/:id          → detail (Overview · Notes · Followups · Calls)
  ├── /leads/:id/edit     → edit form
  └── /leads/:id/whatsapp → WhatsApp send (template + dual mode)
/calls (tab)              ─── call log with stats strip
/reports (tab)            ─── funnel + call analytics
/profile                  ─── settings, WhatsApp mode, Cloudinary, password
/dialer/queue             ─── preset queue picker
/dialer                   ─── ACTIVE DIALER (single-call or queue)
```

---

## 🐛 TROUBLESHOOTING

**Direct dial doesn't trigger the call**
→ Check `CALL_PHONE` permission was granted. Some OEM ROMs (Xiaomi/MIUI, Vivo) have an additional "auto-start" permission that needs to be enabled in device settings.

**WhatsApp doesn't open**
→ User doesn't have WhatsApp installed, or the lead's phone number is malformed. The app normalizes Indian numbers automatically (adds `+91` if missing).

**Voice notes don't upload**
→ Cloudinary config is missing. Go to Profile → Cloudinary section → enter cloud name + unsigned preset name → Save.

**"No dispositions configured"**
→ Backend hasn't seeded any `CallDisposition` rows. Run `python manage.py setup_initial_data` or create some in Django admin.

**Auto-dialer skips the next call**
→ Check that the previous call was disposed. The state machine won't move forward until disposition is saved.

---

## 📦 BUILD

```bash
# Debug
flutter run --dart-define=API_BASE_URL=https://api.yourdomain.com

# Release APK
flutter build apk --release --dart-define=API_BASE_URL=https://api.yourdomain.com
# Output: build/app/outputs/flutter-apk/app-release.apk

# Release App Bundle (for Play Store)
flutter build appbundle --release --dart-define=API_BASE_URL=https://api.yourdomain.com

# iOS
flutter build ios --release --dart-define=API_BASE_URL=https://api.yourdomain.com
```

---

## 📝 LICENSE

Proprietary — DialEasypro / TeleCRM.

---

**Built to ship. No fluff.**
