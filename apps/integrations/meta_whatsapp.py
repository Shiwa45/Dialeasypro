"""
TeleCRM Backend — apps/integrations/meta_whatsapp.py

Meta Click-to-WhatsApp → CRM.

A customer taps "WhatsApp" on a Meta ad, sends a message, and lands here as a
CRM lead — with no Lead Form in the flow. This is the official WhatsApp
Business Platform (Cloud API) webhook, NOT Lead Ads: that one is
MetaLeadAdsWebhookView, it fires on `leadgen` changes and fetches form fields
from the Graph API. The two share a Meta app and nothing else.

Shape of an inbound delivery:

    entry[] → changes[] → value
                            ├── metadata {display_phone_number, phone_number_id}
                            ├── contacts[] {wa_id, profile.name}
                            ├── messages[] {id, from, timestamp, type, text,
                            │               referral?}          ← ad attribution
                            └── statuses[] {id, status, ...}    ← delivery receipts

`referral` is the whole point, and it is also the part most easily got wrong:

  * It arrives ONLY on the first message of an ad-referred conversation (and
    again if the customer clicks a different ad later). Message two of the same
    conversation has no referral and must not be treated as organic.
  * The customer can decline to share it, so an ad-driven conversation may
    legitimately arrive with no referral at all.
  * It carries `source_id` — the AD id — and never the campaign, ad-set or ad
    NAME. Those need a separate Marketing API call with `ads_read`
    (`enrich_attribution`). Without that permission the ids are still stored
    and the names stay empty. They are never invented.

This module holds the parsing and CRM logic; the HTTP surface is
MetaWhatsAppWebhookView in views.py, and the async hand-off is
apps/integrations/tasks.py.
"""
import hashlib
import hmac
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.constants import LeadPriority, LeadSource, LeadStatus
from apps.core.quotas import enforce_lead_quota, note_leads_created
from apps.core.utils import mask_phone_number, normalize_indian_phone

logger = logging.getLogger(__name__)

GRAPH_TIMEOUT = 10

# Meta message kinds we store verbatim. Anything outside this set is still
# saved (as "unsupported") so the conversation stays complete.
SUPPORTED_MESSAGE_TYPES = {
    "text", "image", "document", "audio", "video", "sticker",
    "location", "contacts", "button", "interactive", "reaction", "order",
}

# Statuses Meta reports for an outbound message, mapped onto WhatsAppMessage.
STATUS_MAP = {
    "sent": "sent",
    "delivered": "delivered",
    "read": "read",
    "failed": "failed",
}


class MetaWhatsAppError(Exception):
    """A Graph API call failed. Never carries a token or raw payload."""


# ============================================================
# Configuration
# ============================================================

def get_config():
    """
    The tenant's WhatsApp connection, or None if the row does not exist yet.

    Deliberately does NOT create the singleton: a webhook from a tenant that
    never configured WhatsApp should be rejected, not quietly given a config.
    """
    from apps.communications.models import WhatsAppConfig

    return WhatsAppConfig.objects.filter(singleton=1).first()


def graph_version(config=None) -> str:
    """Per-tenant override, else the platform setting. Never hard-coded."""
    if config is not None and getattr(config, "graph_api_version", ""):
        return config.graph_api_version
    return getattr(settings, "META_GRAPH_API_VERSION", "v25.0")


def _credential(config, key: str, setting_name: str = "") -> str:
    """
    A single credential: the tenant's encrypted value wins, and the settings
    fallback exists for single-tenant and local development only.
    """
    if config is not None:
        value = (config.credentials or {}).get(key)
        if value:
            return str(value)
    if setting_name:
        return str(getattr(settings, setting_name, "") or "")
    return ""


def verify_token_for(config) -> str:
    return _credential(config, "verify_token", "META_VERIFY_TOKEN")


def app_secret_for(config) -> str:
    return _credential(config, "app_secret", "META_APP_SECRET")


def access_token_for(config) -> str:
    return _credential(config, "access_token", "META_ACCESS_TOKEN")


def ads_token_for(config) -> str:
    """
    Token used for the Marketing API name lookup. A tenant can supply a
    separate `ads_access_token` when their WhatsApp system user has no
    `ads_read`; otherwise the WhatsApp token is tried.
    """
    return _credential(config, "ads_access_token") or access_token_for(config)


# ============================================================
# Webhook security
# ============================================================

def verify_signature(raw_body: bytes, header: str, app_secret: str) -> bool:
    """
    Validate Meta's X-Hub-Signature-256 (HMAC-SHA256 of the exact raw body).

    Constant-time compared. Must be given the untouched request body — any
    re-serialization changes the digest and every delivery starts failing.
    """
    if not app_secret or not header:
        return False
    if not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", header)


def signature_required() -> bool:
    return bool(getattr(settings, "META_WHATSAPP_VERIFY_SIGNATURE", True))


# ============================================================
# Payload parsing
# ============================================================

@dataclass
class InboundMessage:
    """One normalized inbound WhatsApp message."""

    message_id: str
    from_wa_id: str
    phone_number_id: str
    display_phone_number: str = ""
    waba_id: str = ""
    profile_name: str = ""
    message_type: str = "text"
    text: str = ""
    timestamp: datetime | None = None
    referral: dict = field(default_factory=dict)
    media: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)

    @property
    def phone(self) -> str:
        """E.164 form of the sender's wa_id, or "" when unparseable."""
        return normalize_indian_phone(self.from_wa_id) or ""


@dataclass
class StatusUpdate:
    """One delivery receipt for a message we sent."""

    message_id: str
    status: str
    timestamp: datetime | None = None
    recipient_id: str = ""
    error: str = ""


def _parse_timestamp(value) -> datetime | None:
    """Meta sends a unix-seconds string. Anything else is left as None."""
    try:
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _extract_text(message: dict, msg_type: str) -> str:
    """
    The human-readable body, whatever the kind. Media captions count as text —
    they are usually the whole enquiry ("is this still available?").
    """
    if msg_type == "text":
        return (message.get("text") or {}).get("body", "") or ""
    if msg_type == "button":
        return (message.get("button") or {}).get("text", "") or ""
    if msg_type == "interactive":
        interactive = message.get("interactive") or {}
        for key in ("button_reply", "list_reply"):
            if reply := interactive.get(key):
                return reply.get("title", "") or ""
        return ""
    if msg_type == "reaction":
        return (message.get("reaction") or {}).get("emoji", "") or ""
    if msg_type in {"image", "video", "document", "audio", "sticker"}:
        return (message.get(msg_type) or {}).get("caption", "") or ""
    if msg_type == "location":
        loc = message.get("location") or {}
        return loc.get("name") or loc.get("address") or ""
    return ""


def _extract_media(message: dict, msg_type: str) -> dict:
    """
    Media identifiers only — never the bytes. Downloading a media id needs an
    authenticated Graph call and is left to a later change; storing the id and
    mime type keeps that door open.
    """
    if msg_type not in {"image", "video", "document", "audio", "sticker"}:
        return {}
    payload = message.get(msg_type) or {}
    media = {
        "media_id": payload.get("id", ""),
        "mime_type": payload.get("mime_type", ""),
        "sha256": payload.get("sha256", ""),
        "filename": payload.get("filename", ""),
        "voice": payload.get("voice"),
    }
    return {k: v for k, v in media.items() if v not in (None, "")}


def parse_webhook(payload: dict) -> tuple[list[InboundMessage], list[StatusUpdate]]:
    """
    Turn a raw Meta delivery into normalized messages and status updates.

    Tolerant by design: a delivery can legitimately contain fields we do not
    handle (`account_update`, template status changes, an `errors` array), and
    a malformed entry must not cost us the good entries beside it. Anything
    unrecognized is skipped, never raised.
    """
    messages: list[InboundMessage] = []
    statuses: list[StatusUpdate] = []

    if not isinstance(payload, dict):
        return messages, statuses
    if payload.get("object") not in (None, "whatsapp_business_account"):
        return messages, statuses

    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        waba_id = str(entry.get("id") or "")

        for change in entry.get("changes") or []:
            if not isinstance(change, dict) or change.get("field") != "messages":
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue

            metadata = value.get("metadata") or {}
            phone_number_id = str(metadata.get("phone_number_id") or "")
            display_phone = str(metadata.get("display_phone_number") or "")

            # wa_id → profile name, so a message can be labelled with the
            # customer's own WhatsApp display name.
            profiles = {}
            for contact in value.get("contacts") or []:
                if isinstance(contact, dict) and contact.get("wa_id"):
                    profiles[str(contact["wa_id"])] = (
                        (contact.get("profile") or {}).get("name", "") or ""
                    )

            for message in value.get("messages") or []:
                if not isinstance(message, dict):
                    continue
                message_id = str(message.get("id") or "")
                from_wa_id = str(message.get("from") or "")
                if not message_id or not from_wa_id:
                    # Without an id there is no idempotency key, and without a
                    # sender there is no contact. Both are unusable.
                    logger.warning(
                        "[Meta CTWA] Skipping message with no id/sender "
                        "(phone_number_id=%s)", phone_number_id,
                    )
                    continue

                raw_type = str(message.get("type") or "text")
                msg_type = raw_type if raw_type in SUPPORTED_MESSAGE_TYPES else "unsupported"

                messages.append(InboundMessage(
                    message_id=message_id,
                    from_wa_id=from_wa_id,
                    phone_number_id=phone_number_id,
                    display_phone_number=display_phone,
                    waba_id=waba_id,
                    profile_name=profiles.get(from_wa_id, ""),
                    message_type=msg_type,
                    text=_extract_text(message, raw_type),
                    timestamp=_parse_timestamp(message.get("timestamp")),
                    referral=message.get("referral") or {},
                    media=_extract_media(message, raw_type),
                    context=message.get("context") or {},
                ))

            for status in value.get("statuses") or []:
                if not isinstance(status, dict) or not status.get("id"):
                    continue
                errors = status.get("errors") or []
                statuses.append(StatusUpdate(
                    message_id=str(status["id"]),
                    status=str(status.get("status") or ""),
                    timestamp=_parse_timestamp(status.get("timestamp")),
                    recipient_id=str(status.get("recipient_id") or ""),
                    error=str((errors[0] or {}).get("title", "")) if errors else "",
                ))

    return messages, statuses


def parse_referral(referral: dict) -> dict:
    """
    Map Meta's `referral` object onto our columns.

    Only keys Meta actually sent are returned. A key absent from the payload is
    absent from the result — the caller must not fill it in with a placeholder,
    because "no campaign recorded" and "campaign named ''" mean different
    things to whoever reads the lead later.
    """
    if not isinstance(referral, dict) or not referral:
        return {}

    mapping = {
        "source_type": "referral_source_type",
        "source_id": "referral_source_id",
        "source_url": "referral_source_url",
        "headline": "referral_headline",
        "body": "referral_body",
        "media_type": "referral_media_type",
        "ctwa_clid": "ctwa_clid",
    }
    parsed = {}
    for meta_key, column in mapping.items():
        value = referral.get(meta_key)
        if value not in (None, ""):
            parsed[column] = str(value)

    # source_id IS the ad id when the referral came from an ad (source_type
    # "post" means an organic post, and then it is a post id, not an ad).
    if referral.get("source_type") == "ad" and referral.get("source_id"):
        parsed["meta_ad_id"] = str(referral["source_id"])

    if parsed:
        parsed["is_ad_referred"] = True
        parsed["referral_payload"] = referral
    return parsed


# ============================================================
# Marketing API enrichment (campaign / ad set / ad names)
# ============================================================

def fetch_ad_attribution(ad_id: str, access_token: str, version: str) -> dict:
    """
    Look up the names behind an ad id.

    Needs `ads_read` on the ad account that owns the ad — a WhatsApp-only
    system user does NOT have it, and Meta answers 190/200 in that case. That
    is a configuration fact, not an outage, so it is returned as an error
    string for the admin rather than raised.
    """
    if not ad_id or not access_token:
        return {}

    url = f"https://graph.facebook.com/{version}/{ad_id}"
    try:
        response = requests.get(
            url,
            params={
                "access_token": access_token,
                "fields": "id,name,adset{id,name},campaign{id,name}",
            },
            timeout=GRAPH_TIMEOUT,
        )
    except requests.RequestException as exc:
        # Network-level failure — transient, worth a retry later.
        raise MetaWhatsAppError(f"Graph request failed: {exc.__class__.__name__}") from exc

    if response.status_code != 200:
        detail = ""
        try:
            detail = (response.json().get("error") or {}).get("message", "")
        except ValueError:
            pass
        raise MetaWhatsAppError(
            f"Graph {response.status_code}: {detail or 'ad lookup rejected'}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise MetaWhatsAppError("Graph returned a non-JSON body") from exc

    adset = data.get("adset") or {}
    campaign = data.get("campaign") or {}
    result = {
        "meta_ad_id": data.get("id", ""),
        "meta_ad_name": data.get("name", ""),
        "meta_adset_id": adset.get("id", ""),
        "meta_adset_name": adset.get("name", ""),
        "meta_campaign_id": campaign.get("id", ""),
        "meta_campaign_name": campaign.get("name", ""),
    }
    return {k: v for k, v in result.items() if v}


def enrich_attribution(conversation, config) -> bool:
    """
    Fill in campaign/ad-set/ad names on a conversation. Returns True if
    anything was written. Never raises — attribution is a nice-to-have and
    must not fail the lead that carries it.
    """
    if not getattr(settings, "META_WHATSAPP_ADS_ENRICHMENT", True):
        return False
    if not conversation.meta_ad_id or conversation.attribution_enriched_at:
        return False

    token = ads_token_for(config)
    if not token:
        return False

    try:
        data = fetch_ad_attribution(conversation.meta_ad_id, token, graph_version(config))
    except MetaWhatsAppError as exc:
        conversation.attribution_error = str(exc)[:300]
        conversation.save(update_fields=["attribution_error", "updated_at"])
        logger.info(
            "[Meta CTWA] Ad enrichment unavailable for ad=%s: %s",
            conversation.meta_ad_id, exc,
        )
        return False

    if not data:
        return False

    for field_name, value in data.items():
        setattr(conversation, field_name, value)
    conversation.attribution_enriched_at = timezone.now()
    conversation.attribution_error = ""
    conversation.save(update_fields=[
        *data.keys(), "attribution_enriched_at", "attribution_error", "updated_at",
    ])

    # Mirror the names onto the lead's existing attribution columns so the
    # normal lead list/report filters see Click-to-WhatsApp leads too.
    _sync_lead_campaign_fields(conversation)
    logger.info(
        "[Meta CTWA] Attribution enriched | ad=%s campaign=%s",
        conversation.meta_ad_id, conversation.meta_campaign_name or "-",
    )
    return True


def _sync_lead_campaign_fields(conversation):
    """
    Copy the ad names onto Lead.campaign_name / Lead.ad_name.

    Those two columns already drive campaign reporting for Lead Ads and Google,
    so Click-to-WhatsApp leads populate the same ones rather than inventing a
    parallel set. Only ever fills a blank — a name typed by a human wins.
    """
    from apps.leads.models import Lead

    lead = conversation.lead
    updates = {}
    if conversation.meta_campaign_name and not lead.campaign_name:
        updates["campaign_name"] = conversation.meta_campaign_name[:300]
    if conversation.meta_ad_name and not lead.ad_name:
        updates["ad_name"] = conversation.meta_ad_name[:300]
    if updates:
        Lead.objects.filter(pk=lead.pk).update(**updates)


# ============================================================
# CRM processing
# ============================================================

@dataclass
class ProcessResult:
    """What one webhook event did, for logging and the webhook log row."""

    status: str                     # processed | duplicate | ignored | skipped
    lead_id: int | None = None
    conversation_id: str = ""
    created_lead: bool = False
    created_message: bool = False
    detail: str = ""


def _resolve_lead(message: InboundMessage, config, conversation_referral: dict):
    """
    Find the contact behind this number, or create one.

    Phone is the CRM's identity for a person (see Lead), so an existing lead on
    the same number is THE contact — a second lead would fragment their call
    history. Existing CRM data is never overwritten: the WhatsApp profile name
    only fills a blank or a placeholder, and nothing else on the lead is
    touched here.

    Returns (lead, created) or (None, False) when policy says not to create one.
    """
    from apps.leads.models import Lead

    phone = message.phone
    if not phone:
        return None, False

    lead = Lead.objects.filter(phone=phone, is_deleted=False).order_by("id").first()
    if lead is not None:
        if message.profile_name and lead.name.strip().lower() in ("", "unknown"):
            lead.name = message.profile_name[:200]
            lead.save(update_fields=["name", "updated_at"])
        return lead, False

    if config is not None and not config.create_leads_from_inbound:
        return None, False
    # `ctwa_leads_only` tenants buy this integration for ad traffic; organic
    # inbound from a stranger should not open a lead for them.
    if config is not None and config.ctwa_leads_only and not conversation_referral:
        return None, False

    # A new contact counts against the plan's lead caps exactly like any other
    # inbound source. Raises PlanLimitExceededException, handled by the caller.
    enforce_lead_quota(1)

    assigned_to = getattr(config, "inbound_assign_to", None) if config else None
    lead = Lead.objects.create(
        name=(message.profile_name or "WhatsApp Lead")[:200],
        phone=phone,
        source=LeadSource.META_CTWA if conversation_referral else LeadSource.WHATSAPP,
        status=LeadStatus.NEW,
        priority=LeadPriority.WARM,
        assigned_to=assigned_to,
        assigned_at=timezone.now() if assigned_to else None,
        source_lead_id=message.message_id,
        source_meta={
            "channel": "whatsapp",
            "wa_id": message.from_wa_id,
            "business_phone_number_id": message.phone_number_id,
            "whatsapp_business_id": message.waba_id,
            "first_message": message.text[:1000],
            "referral": conversation_referral.get("referral_payload", {}),
        },
    )
    note_leads_created(1)
    return lead, True


def _resolve_conversation(message: InboundMessage, lead, referral: dict):
    """
    The open thread for this contact on this business number, or a new one.

    Reuse is keyed on (wa_id, phone_number_id) and guarded by a partial unique
    index, so two concurrent deliveries cannot both create one. A referral on a
    later message means the customer clicked a NEW ad: that opens a fresh
    conversation rather than rewriting the first ad's attribution.
    """
    from apps.communications.models import WhatsAppConversation

    existing = WhatsAppConversation.objects.filter(
        contact_wa_id=message.from_wa_id,
        business_phone_number_id=message.phone_number_id,
        status=WhatsAppConversation.STATUS_OPEN,
    ).order_by("-created_at").first()

    if existing is not None:
        # A DIFFERENT ad means a genuinely new campaign touch, and each ad
        # deserves its own honest attribution. An open thread that had no ad
        # attribution at all is merely being labelled for the first time —
        # forking there would split one continuous chat into two histories.
        new_ad = bool(
            referral
            and existing.is_ad_referred
            and referral.get("referral_source_id")
            and referral["referral_source_id"] != existing.referral_source_id
        )
        if not new_ad:
            if referral and not existing.is_ad_referred:
                # First referral seen on an already-open organic thread.
                for field_name, value in referral.items():
                    setattr(existing, field_name, value)
                existing.save(update_fields=[*referral.keys(), "updated_at"])
            if message.profile_name and not existing.whatsapp_profile_name:
                existing.whatsapp_profile_name = message.profile_name[:200]
                existing.save(update_fields=["whatsapp_profile_name", "updated_at"])
            return existing, False

        # A different ad — close the old thread so the partial unique index
        # stays satisfied, then open a new one below.
        existing.status = WhatsAppConversation.STATUS_CLOSED
        existing.save(update_fields=["status", "updated_at"])

    conversation = WhatsAppConversation(
        lead=lead,
        contact_wa_id=message.from_wa_id,
        contact_phone=message.phone,
        whatsapp_profile_name=(message.profile_name or "")[:200],
        business_phone_number_id=message.phone_number_id,
        business_display_phone=message.display_phone_number[:25],
        whatsapp_business_id=message.waba_id[:50],
        first_message_at=message.timestamp or timezone.now(),
        **referral,
    )
    try:
        with transaction.atomic():
            conversation.save()
    except IntegrityError:
        # Lost the race against a concurrent delivery — take theirs.
        conversation = WhatsAppConversation.objects.filter(
            contact_wa_id=message.from_wa_id,
            business_phone_number_id=message.phone_number_id,
            status=WhatsAppConversation.STATUS_OPEN,
        ).order_by("-created_at").first()
        return conversation, False
    return conversation, True


def _record_message(message: InboundMessage, lead, conversation):
    """
    Store the inbound message once.

    Keyed on Meta's wamid so a replay updates nothing and inserts nothing —
    the ledger already blocks replays, and this is the second line of defence
    for a payload that arrives through some other path (a manual backfill).
    """
    from apps.communications.models import WhatsAppMessage
    from apps.core.constants import WhatsAppProvider

    metadata = {}
    if message.media:
        metadata["media"] = message.media
    if message.context:
        metadata["context"] = message.context
    if message.message_type == "unsupported":
        metadata["note"] = "Message type not modelled; stored for completeness."

    wa_message, created = WhatsAppMessage.objects.get_or_create(
        provider_message_id=message.message_id,
        direction="inbound",
        defaults={
            "lead": lead,
            "conversation": conversation,
            "message_type": message.message_type,
            "content": message.text,
            "provider": WhatsAppProvider.META_CLOUD,
            "status": "received",
            "wa_timestamp": message.timestamp,
            "metadata": metadata,
        },
    )
    return wa_message, created


def _touch_conversation(conversation, message: InboundMessage):
    from django.db.models import F

    now = message.timestamp or timezone.now()
    type(conversation).objects.filter(pk=conversation.pk).update(
        last_message_at=now,
        last_inbound_at=now,
        message_count=F("message_count") + 1,
        updated_at=timezone.now(),
    )


def _update_lead_from_message(lead, message: InboundMessage, conversation, config):
    """
    Apply the CRM's own rules to an inbound message on an EXISTING lead.

    Explicitly not "create a lead per message": an active lead is updated, and
    only a lead that was closed out (lost / not interested) is reopened, and
    only when the tenant asked for that. A converted customer is left alone —
    dragging a won deal back to New would corrupt the pipeline.
    """
    from apps.leads.models import Lead, LeadActivity

    updates = {"last_contacted_at": timezone.now()}
    reopened = False

    closed_statuses = {LeadStatus.LOST, LeadStatus.NOT_INTERESTED}
    if (
        getattr(config, "reopen_lead_on_inbound", True)
        and lead.status in closed_statuses
    ):
        updates["status"] = LeadStatus.NEW
        reopened = True

    # Attribution from a fresh ad click belongs on the lead's own columns too,
    # but only where the CRM has nothing better already.
    if conversation is not None:
        if conversation.meta_campaign_name and not lead.campaign_name:
            updates["campaign_name"] = conversation.meta_campaign_name[:300]
        if conversation.meta_ad_name and not lead.ad_name:
            updates["ad_name"] = conversation.meta_ad_name[:300]

    Lead.objects.filter(pk=lead.pk).update(**updates)

    preview = (message.text or f"[{message.message_type}]")[:200]
    LeadActivity.objects.create(
        lead=lead,
        activity_type="whatsapp",
        description=f"WhatsApp message received: {preview}",
        meta={
            "direction": "inbound",
            "message_id": message.message_id,
            "message_type": message.message_type,
            "conversation_id": str(conversation.pk) if conversation else "",
            "reopened": reopened,
        },
    )
    return reopened


def _notify(lead, conversation, message: InboundMessage, *, is_new_lead: bool):
    """
    Push the new lead/message into the CRM UI over the WebSocket layer that
    already exists (apps/core/consumers.py). Best-effort: a realtime hiccup
    must never fail a webhook that has already written to the database.
    """
    try:
        from django.db import connection

        from apps.core.consumers import broadcast_to_monitors, send_agent_notification

        schema = connection.schema_name
        payload = {
            "lead_id": lead.pk,
            "lead_name": lead.name,
            "phone": lead.phone,
            "channel": "whatsapp",
            "source": lead.source,
            "message_preview": (message.text or f"[{message.message_type}]")[:100],
            "conversation_id": str(conversation.pk) if conversation else "",
            "attribution": conversation.attribution if conversation else {},
        }
        if lead.assigned_to_id:
            send_agent_notification(
                schema_name=schema,
                agent_id=lead.assigned_to_id,
                event_type="new_lead" if is_new_lead else "message_received",
                data=payload,
            )
        broadcast_to_monitors(
            schema_name=schema,
            event_type="new_lead" if is_new_lead else "message_received",
            data=payload,
        )
    except Exception as exc:  # noqa: BLE001 — realtime is never load-bearing
        logger.debug("[Meta CTWA] Realtime notify skipped: %s", exc)


def process_message(message: InboundMessage, config, webhook_log=None) -> ProcessResult:
    """
    Contact → conversation → message → lead, exactly once.

    The whole unit is one transaction that begins by claiming the event's
    dedupe key. A retry of an already-processed delivery finds the key taken
    and returns "duplicate" without writing; a failure rolls the claim back
    with everything else, so the retry that follows genuinely reprocesses.
    """
    from apps.integrations.models import MetaWhatsAppEvent

    dedupe_key = f"msg:{message.message_id}"

    with transaction.atomic():
        event, claimed = MetaWhatsAppEvent.objects.get_or_create(
            dedupe_key=dedupe_key,
            defaults={
                "message_id": message.message_id,
                "kind": MetaWhatsAppEvent.KIND_MESSAGE,
                "webhook_log": webhook_log,
            },
        )
        if not claimed:
            logger.info(
                "[Meta CTWA] Duplicate delivery ignored | message_id=%s status=%s",
                message.message_id, event.status,
            )
            return ProcessResult(
                status="duplicate",
                lead_id=event.lead_id,
                detail=f"already {event.status}",
            )

        referral = parse_referral(message.referral)
        lead, lead_created = _resolve_lead(message, config, referral)

        if lead is None:
            event.mark(MetaWhatsAppEvent.STATUS_IGNORED, error="no matching lead policy")
            logger.info(
                "[Meta CTWA] Message stored no lead | wa_id=%s reason=policy_or_bad_phone",
                mask_phone_number(message.from_wa_id),
            )
            return ProcessResult(status="skipped", detail="lead creation not permitted")

        conversation, conv_created = _resolve_conversation(message, lead, referral)
        wa_message, msg_created = _record_message(message, lead, conversation)

        if msg_created and conversation is not None:
            _touch_conversation(conversation, message)

        if not lead_created:
            _update_lead_from_message(lead, message, conversation, config)
        else:
            from apps.leads.models import LeadActivity

            LeadActivity.objects.create(
                lead=lead,
                activity_type="imported",
                description=(
                    "Lead created from a Click-to-WhatsApp ad"
                    if referral else "Lead created from an inbound WhatsApp message"
                ),
                meta={
                    "source": lead.source,
                    "message_id": message.message_id,
                    "conversation_id": str(conversation.pk) if conversation else "",
                    "referral": referral.get("referral_payload", {}),
                },
            )

        event.lead = lead
        event.conversation_id = conversation.pk if conversation else None
        event.created_lead = lead_created
        event.mark(MetaWhatsAppEvent.STATUS_PROCESSED)

    # ---- After the commit: nothing below may fail the write above ----
    logger.info(
        "[Meta CTWA] Processed | message_id=%s lead=%s lead_created=%s "
        "conversation_created=%s ad_referred=%s",
        message.message_id, lead.pk, lead_created, conv_created, bool(referral),
    )

    if conversation is not None and referral:
        enrich_attribution(conversation, config)

    _notify(lead, conversation, message, is_new_lead=lead_created)

    return ProcessResult(
        status="processed",
        lead_id=lead.pk,
        conversation_id=str(conversation.pk) if conversation else "",
        created_lead=lead_created,
        created_message=msg_created,
    )


def process_status(update: StatusUpdate, config, webhook_log=None) -> ProcessResult:
    """
    Apply a delivery receipt to the outbound message it belongs to.

    Unknown message ids are normal — the receipt may be for something sent
    outside this CRM — so they are recorded as ignored, not failed.
    """
    from apps.communications.models import WhatsAppMessage
    from apps.integrations.models import MetaWhatsAppEvent

    mapped = STATUS_MAP.get(update.status)
    if not mapped:
        return ProcessResult(status="ignored", detail=f"unmapped status {update.status}")

    dedupe_key = f"status:{update.message_id}:{update.status}"

    with transaction.atomic():
        event, claimed = MetaWhatsAppEvent.objects.get_or_create(
            dedupe_key=dedupe_key,
            defaults={
                "message_id": update.message_id,
                "kind": MetaWhatsAppEvent.KIND_STATUS,
                "webhook_log": webhook_log,
            },
        )
        if not claimed:
            return ProcessResult(status="duplicate", detail="status already applied")

        fields = {"status": mapped}
        when = update.timestamp or timezone.now()
        if mapped == "delivered":
            fields["delivered_at"] = when
        elif mapped == "read":
            fields["read_at"] = when
        elif mapped == "failed" and update.error:
            fields["error_message"] = update.error[:500]

        updated = WhatsAppMessage.objects.filter(
            provider_message_id=update.message_id, direction="outbound",
        ).update(**fields)

        if not updated:
            event.mark(MetaWhatsAppEvent.STATUS_IGNORED, error="unknown message id")
            return ProcessResult(status="ignored", detail="no matching outbound message")

        event.mark(MetaWhatsAppEvent.STATUS_PROCESSED)

    return ProcessResult(status="processed", detail=f"status={mapped}")


def process_payload(payload: dict, config, webhook_log=None) -> dict:
    """
    Process one whole webhook delivery.

    Every event is isolated: one bad message must not stop the four good ones
    delivered beside it, because Meta would then redeliver the entire batch and
    the good ones would have to be deduped anyway.
    """
    from apps.core.exceptions import PlanLimitExceededException

    messages, statuses = parse_webhook(payload)
    summary = {
        "messages": len(messages),
        "statuses": len(statuses),
        "leads_created": 0,
        "leads_updated": 0,
        "duplicates": 0,
        "errors": 0,
        "quota_blocked": 0,
        "last_error": "",
    }

    for message in messages:
        try:
            result = process_message(message, config, webhook_log)
        except PlanLimitExceededException as exc:
            # An upgrade — not a retry — fixes this, so it is counted and the
            # delivery is still acknowledged.
            summary["quota_blocked"] += 1
            summary["last_error"] = str(exc.detail)[:500]
            logger.warning("[Meta CTWA] Lead quota reached: %s", exc.detail)
            continue
        except Exception as exc:  # noqa: BLE001 — one event must not sink the batch
            summary["errors"] += 1
            summary["last_error"] = str(exc)[:500]
            logger.error(
                "[Meta CTWA] Failed to process message_id=%s: %s",
                message.message_id, exc, exc_info=True,
            )
            continue

        if result.status == "duplicate":
            summary["duplicates"] += 1
        elif result.status == "processed":
            if result.created_lead:
                summary["leads_created"] += 1
            else:
                summary["leads_updated"] += 1

    for update in statuses:
        try:
            process_status(update, config, webhook_log)
        except Exception as exc:  # noqa: BLE001
            summary["errors"] += 1
            summary["last_error"] = str(exc)[:500]
            logger.error(
                "[Meta CTWA] Failed to apply status for %s: %s",
                update.message_id, exc, exc_info=True,
            )

    return summary
