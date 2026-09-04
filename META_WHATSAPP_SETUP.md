# Meta Click-to-WhatsApp → CRM — Setup

A customer taps **WhatsApp** on a Meta ad, sends a message, and becomes a CRM
lead with the ad's attribution attached. **No Meta Lead Form is involved.**

> **Click-to-WhatsApp is not Lead Ads.** This CRM has both, and they are
> separate integrations that happen to share one Meta app:
>
> | | Lead Ads | Click-to-WhatsApp (this document) |
> |---|---|---|
> | Customer does | fills a Meta Lead Form | sends a WhatsApp message |
> | Webhook field | `leadgen` | `messages` |
> | Endpoint | `/api/v1/integrations/meta/` | `/api/v1/integrations/meta/whatsapp/` |
> | Lead data from | Graph API form fetch | the WhatsApp message itself |
>
> Configuring one does not configure the other.

---

## 1. The flow

```
Meta / Facebook / Instagram Click-to-WhatsApp ad
        ↓  customer taps "WhatsApp"
WhatsApp chat opens, customer sends a message
        ↓
Meta WhatsApp Business Platform (Cloud API)
        ↓  POST, signed with X-Hub-Signature-256
/api/v1/integrations/meta/whatsapp/      ← validates, logs, returns 200 fast
        ↓  Celery, queue "integrations"
find/create Lead → find/create WhatsAppConversation → save WhatsAppMessage
        ↓
store Meta referral (ad id, headline, ctwa_clid, …)
        ↓  optional, needs ads_read
resolve campaign / ad-set / ad NAMES via the Marketing API
        ↓
assign per the tenant's rule, push to the CRM over the existing WebSocket
```

---

## 2. What was added

| Area | Where |
|---|---|
| Webhook (GET verify + POST deliver) | `apps/integrations/views.py` → `MetaWhatsAppWebhookView` |
| Parsing + CRM rules | `apps/integrations/meta_whatsapp.py` |
| Async processing | `apps/integrations/tasks.py` |
| Conversation + attribution model | `apps/communications/models.py` → `WhatsAppConversation` |
| Idempotency ledger | `apps/integrations/models.py` → `MetaWhatsAppEvent` |
| Settings screen | `GET/PUT /api/v1/comms/whatsapp/config/` |
| Tests + payload fixtures | `apps/integrations/tests/` |

No duplicate models were created. The CRM is lead-centric — `Lead` **is** the
contact — so an inbound WhatsApp number resolves to an existing `Lead` by phone,
and messages continue to use the existing `WhatsAppMessage` model.

---

## 3. Environment variables

All optional in production (each tenant stores their own encrypted credentials);
required only for single-tenant or local development. Full descriptions are in
`.env.example`.

| Variable | Purpose |
|---|---|
| `META_APP_ID` | Meta app id. Not secret. |
| `META_APP_SECRET` | Verifies `X-Hub-Signature-256` on every delivery. **Secret.** |
| `META_VERIFY_TOKEN` | Shared string for the webhook handshake. **Secret.** |
| `META_ACCESS_TOKEN` | System-user token for Graph calls. **Secret.** |
| `META_WABA_ID` | WhatsApp Business Account id. |
| `META_PHONE_NUMBER_ID` | The business number's id (not the number). |
| `META_GRAPH_API_VERSION` | Graph version, default `v25.0`. Change here, never in code. |
| `META_WHATSAPP_VERIFY_SIGNATURE` | Default `True`. Only ever `False` on a dev machine. |
| `META_WHATSAPP_ADS_ENRICHMENT` | Default `True`. Resolves campaign/ad names (needs `ads_read`). |

Per-tenant credentials are stored on `WhatsAppConfig.credentials`, an
`EncryptedJSONField` — ciphertext at rest, and the API masks every secret on
read. Set `FIELD_ENCRYPTION_KEY` in production so the ciphertext does not
depend on `SECRET_KEY`.

---

## 4. Migrate and test

```bash
# Migrations (three apps: shared schema first, then every tenant schema)
python manage.py migrate_schemas --shared
python manage.py migrate_schemas --tenant

# Docker
docker compose exec web python manage.py migrate_schemas --shared
docker compose exec web python manage.py migrate_schemas --tenant

# Tests
pip install -r requirements-dev.txt
pytest apps/integrations/tests/test_meta_whatsapp.py -v --no-cov
```

New migrations:

- `apps/communications/migrations/0004_whatsappconfig_create_leads_from_inbound_and_more.py`
- `apps/integrations/migrations/0002_alter_leadsourceconfig_source_and_more.py`
- `apps/leads/migrations/0004_alter_lead_source_alter_leadimportjob_default_source.py`

All three are additive — new columns (nullable or defaulted), new tables, new
indexes. Nothing is dropped or renamed, and no existing row is rewritten.

---

## 5. Webhook URL

```
https://<tenant>.<your-domain>/api/v1/integrations/meta/whatsapp/
```

The URL is **per tenant**, resolved from the subdomain — the same convention the
existing IndiaMART / Lead Ads / Google webhooks use. Every tenant configures
their own Meta app pointing at their own subdomain. HTTPS is required; Meta will
not save an `http://` callback.

Read the exact URL for the logged-in tenant from
`GET /api/v1/comms/whatsapp/config/` → `webhook.callback_url`.

---

## 6. Development / test mode

You never need production credentials locally.

**Option A — Meta's test number (real end-to-end).** Every new Meta app gets a
free test phone number under **WhatsApp → API Setup**, with a temporary 24-hour
token, and up to 5 verified recipient numbers. Expose your machine with a
tunnel (`ngrok http 8000`, `cloudflared tunnel`) and give Meta the HTTPS tunnel
URL. Attribution will be absent — a test number receives no ad clicks.

**Option B — replay a fixture (no Meta at all).** The payload builders in
`apps/integrations/tests/meta_whatsapp_payloads.py` produce exactly what Meta
sends. Sign one and POST it:

```bash
python - <<'PY' > /tmp/ctwa.json
import json
from apps.integrations.tests.meta_whatsapp_payloads import ctwa_message
print(json.dumps(ctwa_message()))
PY

SECRET="your_local_app_secret"
SIG="sha256=$(openssl dgst -sha256 -hmac "$SECRET" /tmp/ctwa.json | awk '{print $2}')"

curl -X POST http://localhost:8000/api/v1/integrations/meta/whatsapp/ \
  -H "Host: demo.localhost" \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: $SIG" \
  --data-binary @/tmp/ctwa.json
```

Setting `META_WHATSAPP_VERIFY_SIGNATURE=False` skips the signing step locally —
a **wrong** signature is still rejected even then, and this must never be off in
production.

For the verification handshake:

```bash
curl "http://localhost:8000/api/v1/integrations/meta/whatsapp/?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=12345"
# → 12345
```

---

## 7. Production deployment

1. Deploy the code, then run **both** migration commands (§4). Existing tenants
   are unaffected until they enable inbound.
2. Ensure a Celery worker consumes the `integrations` queue — it already does in
   `docker-compose.yml` and `docker-compose.prod.yml`:
   `-Q default,bulk_ops,notifications,integrations,call_uploads`.
3. **Restart the web and worker processes.** This release adds the Celery app
   import to `config/__init__.py`; without a restart the web process keeps the
   old, unconfigured Celery app and no task is ever enqueued.
4. Confirm the webhook URL terminates TLS and that `/api/v1/integrations/` is
   not behind auth at the proxy.
5. In the CRM: **WhatsApp settings** → provider *Meta Cloud API*, paste the
   credentials, generate a verify token, switch **inbound_enabled** on.
6. Do the Meta-side setup (§8), then send one real WhatsApp message to the
   business number and confirm a lead appears.

### Rate limiting and abuse

The endpoint is unauthenticated by design (Meta cannot send a JWT), so the
signature *is* the authentication — an unsigned or wrongly-signed request is
rejected at 401 before anything is parsed or stored. Put a rate limit in front
of it at the proxy anyway; the existing nginx config is the right place.

---

## 8. What the client must do in Meta

Meta moves its menus often, so this describes **what to look for** rather than a
fixed click path.

1. **Meta account + Business portfolio** — business.facebook.com. The person
   doing this needs full control of the portfolio.
2. **Facebook Page** — the Page the ads will run from.
3. **WhatsApp Business Account (WABA)** — a phone number **not** currently
   registered to the WhatsApp consumer or Business app. Note the WABA id.
4. **Meta app** — developers.facebook.com → *My Apps* → create a **Business**
   type app, linked to the portfolio.
5. **Add the WhatsApp product** to the app.
6. **Collect the ids** — under WhatsApp → *API Setup*: **Phone number ID**,
   **WhatsApp Business Account ID**; under App settings → Basic: **App ID** and
   **App Secret**.
7. **Register the production number** and set its display name and two-step PIN.
8. **Create a permanent token** — Business settings → *Users* → **System users**
   → add a system user with admin access to the app and WABA → *Generate token*.
   Scopes: `whatsapp_business_messaging`, `whatsapp_business_management`, and
   `ads_read` if campaign/ad names are wanted. A system-user token does not
   expire; the *API Setup* temporary token expires in 24 hours and is for
   testing only.
9. **Configure the webhook** — WhatsApp → *Configuration* → Webhook → **Edit**:
   - Callback URL: the tenant URL from §5
   - Verify token: the value generated in the CRM
   - Click **Verify and token** — it must go green immediately.
10. **Subscribe to `messages`.** This one field carries inbound messages,
    delivery receipts, *and* the Click-to-WhatsApp `referral`. Without it
    nothing arrives.
11. **Test an inbound message** — send a WhatsApp from a personal phone to the
    business number.
12. **Verify the lead** in the CRM (Leads → newest).
13. **Run a real Click-to-WhatsApp ad** — Ads Manager → objective *Engagement*
    or *Sales* → conversion location **WhatsApp** → choose the WhatsApp number.
    A published ad is required; a preview click does not produce a referral.
14. **Verify attribution** — click the ad from a phone that has never messaged
    the business, send a message, then open the lead. Ad id and headline appear
    immediately; campaign and ad-set names appear only if the token has
    `ads_read`.

---

## 9. Requires manual action in Meta (cannot be automated)

| Item | Why |
|---|---|
| Business verification | Meta reviews documents; days to weeks. Required for production messaging volumes. |
| Phone number registration + display name review | Meta approves the display name. |
| App review / advanced access | `whatsapp_business_messaging` and `whatsapp_business_management` need advanced access for numbers outside the app's own portfolio. |
| System-user token generation | Only in Business settings, by a human with admin rights. |
| Webhook URL + verify token entry | Meta has no API to set an app's webhook callback. |
| Subscribing to `messages` | Done in the app's WhatsApp configuration. |
| `ads_read` grant | Needed for campaign/ad-set/ad **names**. Without it the ad id is still captured. |
| Creating the Click-to-WhatsApp ad | Ads Manager. |
| Payment method on the WABA | Meta charges per conversation; without it messaging stops. |

## 10. Known platform limitations

- **The webhook has no campaign or ad name in it.** Meta sends `referral.source_id`
  (the ad id) and `ctwa_clid` only. Names require the separate `ads_read` lookup.
  When it is unavailable those fields stay **empty** — the integration does not
  guess them.
- **Referral appears on the first message only.** Later messages in the same
  conversation carry none; the attribution is held on the conversation, not
  re-read per message.
- **A customer can withhold referral data**, so an ad-driven lead can genuinely
  arrive with no attribution at all.
- **One callback URL per Meta app.** Multi-tenant means one Meta app per tenant,
  pointing at that tenant's subdomain. A single shared app fanning out to many
  tenants by `phone_number_id` is not implemented.
- **24-hour customer service window.** Free-form replies are only allowed within
  24 hours of the customer's last message; outside it Meta requires an approved
  template. This affects replies, not lead capture.
