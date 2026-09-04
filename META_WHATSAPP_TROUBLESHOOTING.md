# Meta Click-to-WhatsApp — Troubleshooting

Setup instructions are in [META_WHATSAPP_SETUP.md](META_WHATSAPP_SETUP.md).

## First: read the integration's own health

```
GET /api/v1/comms/whatsapp/config/
```

```json
{
  "inbound_enabled": true,
  "last_webhook_at": "2026-09-04T11:20:11Z",
  "last_webhook_error": "",
  "total_inbound_messages": 42,
  "webhook": {
    "callback_url": "https://acme.telecrm.in/api/v1/integrations/meta/whatsapp/",
    "https": true,
    "verify_token_set": true,
    "app_secret_set": true,
    "graph_api_version": "v25.0",
    "signature_enforced": true
  }
}
```

`last_webhook_at` is the single most useful field: if it is null or stale, the
problem is between Meta and the server and nothing in the CRM will help.

Then the raw deliveries — payload, processing result, and any error:

```
GET /api/v1/integrations/logs/?source=meta_ctwa
```

Server-side, every line is prefixed `[Meta CTWA]`:

```bash
docker compose logs -f web celery_worker | grep "Meta CTWA"
```

---

## Verification fails ("The URL couldn't be validated")

| Cause | Check |
|---|---|
| Verify token mismatch | Generate a fresh one (`POST /api/v1/comms/whatsapp/webhook-token/`) and paste that exact value into Meta. It is shown once. |
| Wrong URL | Must end in `/api/v1/integrations/meta/whatsapp/`, **with** the trailing slash. `/meta/` alone is the Lead Ads endpoint. |
| Wrong tenant host | The subdomain must resolve to the tenant. A URL on the apex domain hits the public schema, where this route does not exist → 404. |
| Not HTTPS, or an invalid certificate | Meta requires a valid publicly-trusted certificate. Self-signed will not do. |
| Endpoint not public | Meta calls from its own IPs with no credentials. Anything in front asking for auth or a VPN breaks it. |

Test it yourself — this must echo the challenge:

```bash
curl "https://acme.telecrm.in/api/v1/integrations/meta/whatsapp/?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=hello"
# → hello
```

A 403 means the token did not match. The response deliberately never says
*which* part was wrong, so it cannot be used to guess a token.

---

## Verification passed but no messages arrive

1. **Is the `messages` field subscribed?** WhatsApp → Configuration → Webhook
   fields. This is the most common miss — verification succeeds without any
   subscription, so everything looks correct while nothing is delivered.
2. **Is `inbound_enabled` on?** A delivery to a tenant with inbound off is
   answered `{"status": "disabled"}` and discarded. Deliberate: erroring instead
   would make Meta disable the endpoint.
3. **Is the message going to the right number?** The one registered in *this*
   app, matching `phone_number_id`.
4. **Is a Celery worker consuming the `integrations` queue?** The HTTP handler
   returns 200 and hands off; with no worker, `WebhookLog` rows pile up with
   `processed=false` and no lead is ever created.
   ```bash
   docker compose exec celery_worker celery -A config.celery inspect active_queues | grep integrations
   ```
5. **Were the processes restarted after deploy?** This release added the Celery
   app import to `config/__init__.py`. An un-restarted web process silently
   fails to enqueue.

---

## Every delivery returns 401

The signature check failed. In order of likelihood:

- **Wrong app secret.** It must come from the *same* Meta app that sends the
  webhook. Copy it again from App settings → Basic.
- **Something rewrote the body.** The HMAC covers the exact bytes Meta sent. A
  proxy that re-serializes JSON, strips whitespace, or re-encodes will break
  every delivery. Check nginx/Cloudflare body transformations.
- **No secret configured at all** while `META_WHATSAPP_VERIFY_SIGNATURE=True`.
  Correct behaviour: an endpoint that cannot verify must not accept.

`app_secret_set` in the health block tells you whether a secret is stored. The
value itself is never returned.

---

## Leads are created but have no campaign or ad name

**This is expected without `ads_read`, and is not a bug.**

Meta's webhook carries the **ad id** (`referral.source_id`) and `ctwa_clid` —
never a campaign, ad-set or ad name. The names require a Marketing API lookup.

Check the conversation:

```
GET /api/v1/comms/whatsapp/conversations/?ad_referred=true
```

- `attribution.ad_id` present, no `campaign_name` → the lookup did not run or
  was refused. `attribution_error` on the conversation says why (visible in
  Django admin → WhatsApp Conversations).
- `(#200) Ads management permission required` / error 190 → the token lacks
  `ads_read`. Regenerate the system-user token with that scope, or store a
  separate `ads_access_token` on the WhatsApp config.
- `META_WHATSAPP_ADS_ENRICHMENT=False` → the lookup is switched off.

Re-run it for one conversation without replaying webhooks:

```python
from apps.integrations.tasks import enrich_ctwa_attribution
enrich_ctwa_attribution.delay("acme", "<conversation-uuid>")
```

## Leads have no attribution at all

- The customer messaged the business number **directly** rather than through an
  ad — genuinely organic, correctly recorded as `source=whatsapp`.
- It was not the first message of the conversation. Meta sends `referral` once,
  at the start; it is stored on the conversation, not re-sent per message.
- The customer declined to share referral data. Meta allows this.
- The ad is not a Click-to-WhatsApp ad (a "Send message" ad routing to Messenger
  or Instagram Direct produces no WhatsApp webhook at all).

---

## Duplicate leads

Should be impossible; if you see them, check which case it is:

- **Same wamid twice** → look at `MetaWhatsAppEvent` (Django admin → Meta
  WhatsApp Events). A `dedupe_key` is unique, claimed inside the same
  transaction as the CRM writes. Two rows for one message id would mean the
  ledger table was truncated.
- **Same person, two leads** → their number is stored in two formats. Matching
  is on the normalized E.164 phone; a legacy lead saved as `9876543210` will not
  match `+919876543210`. Normalize the older rows.
- **Same person, two conversations** → expected when they clicked a *different*
  ad. Each ad keeps its own attribution; the older thread is closed. Exactly one
  open conversation per contact per business number is enforced by a partial
  unique index.

---

## A lead was expected but nothing was created

Check, in this order:

1. `create_leads_from_inbound` is on.
2. `ctwa_leads_only` — if on, organic inbound is deliberately ignored.
3. **Plan lead quota.** The log says `[Meta CTWA] Lead quota reached`; the
   delivery is acknowledged (retrying cannot fix a quota) and the message is
   dropped. Raise the plan limit, then ask the customer to message again — Meta
   will not redeliver.
4. **Unparseable sender.** A `wa_id` that does not normalize to a valid phone is
   skipped; the log records it with the number masked.

---

## Delivery receipts do nothing

`status` events only update a `WhatsAppMessage` that this CRM sent, matched on
`provider_message_id`. A receipt for a message sent from the WhatsApp Manager
UI, or before this integration was live, has nothing to update — recorded as
`ignored`, which is correct.

---

## Meta disabled our webhook

Meta disables an endpoint that repeatedly errors or times out. It is designed
not to happen here — the handler validates and returns inside milliseconds, all
CRM work is async, and non-retryable conditions answer 200. If it still occurs:

1. Look for 5xx on the endpoint at the proxy.
2. Check response time (must stay well under Meta's ~20s).
3. Re-enable in the app's WhatsApp → Configuration page.

Deliveries missed while disabled are **not** replayed. Recover them from
`WebhookLog` if the payloads were logged, or accept the loss.

---

## Bumping the Graph API version

Set `META_GRAPH_API_VERSION` (or the per-tenant `graph_api_version` override) —
never edit code. Check
[the version changelog](https://developers.facebook.com/docs/graph-api/changelog/versions)
first, then run `pytest apps/integrations/tests/test_meta_whatsapp.py`.

Note the older Meta Lead Ads fetch (`v25.0`) and the WhatsApp send provider
(`v21.0`) still pin their versions inline in code. They were left untouched so
this integration could not disturb a working send path; migrating them to the
setting is a separate change.
