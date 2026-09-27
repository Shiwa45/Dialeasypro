"""
TeleCRM Backend — apps/communications/whatsapp_webhooks.py

Turning each WhatsApp provider's webhook into CRM rows.

Each provider posts its own shape. A parser per provider reduces it to two
lists — inbound messages and delivery receipts — and one shared path records
them, so the rules below hold for every provider:

- The sender's number is normalised with normalize_indian_phone. The old code
  prefixed "+91" to anything without a "+", so a provider that already sends
  the country code ("919812345678") produced "+91919812345678", which never
  matched a lead (MED-7).
- A number on more than one lead (a duplicate import, the same buyer entered
  twice) used to raise MultipleObjectsReturned, which was swallowed: the reply
  was lost (MED-6). The most recently worked lead gets it, and the alternate
  phone counts too.
- Only Interakt was ever parsed. AiSensy, WATI, Gupshup and Meta Cloud were
  answered 200 and thrown away, so their replies and delivery statuses never
  reached the CRM (MED-8). WATI, Gupshup and Meta Cloud are parsed now.
  AiSensy's webhook format is not one we can confirm, so its posts are logged
  loudly rather than guessed at.
- A late "delivered" never overwrites "read": receipts can arrive out of order.
- Providers retry. An inbound message whose id is already stored is skipped.
"""
import logging
from dataclasses import dataclass

from django.db.models import F, Q
from django.utils import timezone

from apps.core.utils import normalize_indian_phone

logger = logging.getLogger(__name__)


@dataclass
class Inbound:
    phone: str          # as the provider sent it
    text: str
    message_id: str = ""
    message_type: str = "text"


@dataclass
class Receipt:
    message_ids: tuple  # any of these may be the id we stored at send time
    status: str         # sent | delivered | read | failed
    error: str = ""


STATUS_RANK = {"queued": 0, "sent": 1, "delivered": 2, "read": 3}


# ============================================================
# Parsers — payload -> ([Inbound], [Receipt])
# ============================================================

def parse_interakt(payload: dict):
    data = payload.get("data") or {}
    event = payload.get("type")
    if event == "message_status":
        msg_id, status = data.get("message_id", ""), data.get("status", "")
        return [], ([Receipt((msg_id,), status)] if msg_id and status else [])
    if event == "inbound_message":
        text = ((data.get("message") or {}).get("text") or {}).get("body", "")
        return [Inbound(data.get("customer_phone_number", ""), text, data.get("wa_message_id", ""))], []
    return [], []


def parse_meta_cloud(payload: dict):
    from apps.integrations.meta_whatsapp import parse_webhook

    messages, statuses = parse_webhook(payload)
    inbound = [Inbound(m.from_wa_id, m.text, m.message_id, m.message_type) for m in messages]
    receipts = [Receipt((s.message_id,), s.status, s.error) for s in statuses]
    return inbound, receipts


def parse_wati(payload: dict):
    """
    WATI: {"eventType": "message", "waId": "91…", "text": "…", "id": "…"} for a
    reply; eventType "sentMessageDELIVERED" / "…READ" / "…FAILED" (optionally
    suffixed "_v2") for receipts, carrying id / whatsappMessageId / localMessageId.
    """
    event = str(payload.get("eventType") or "")
    if event == "message" and not payload.get("owner"):
        return [Inbound(str(payload.get("waId", "")), payload.get("text") or "",
                        str(payload.get("whatsappMessageId") or payload.get("id") or ""),
                        payload.get("type") or "text")], []
    upper = event.upper()
    for marker, status in (("READ", "read"), ("DELIVERED", "delivered"),
                           ("FAILED", "failed"), ("SENT", "sent")):
        if event.startswith("sentMessage") and marker in upper:
            ids = tuple(str(payload[k]) for k in ("id", "whatsappMessageId", "localMessageId")
                        if payload.get(k))
            return [], ([Receipt(ids, status, payload.get("failedDetail") or "")] if ids else [])
    return [], []


def parse_gupshup(payload: dict):
    """
    Gupshup: {"type": "message", "payload": {"id", "source": "91…",
    "type": "text", "payload": {"text": …}}} for a reply;
    {"type": "message-event", "payload": {"id", "gsId", "type": "delivered"…}}
    for receipts.
    """
    body = payload.get("payload") or {}
    if payload.get("type") == "message":
        inner = body.get("payload") or {}
        return [Inbound(str(body.get("source", "")), inner.get("text") or "",
                        str(body.get("id", "")), body.get("type") or "text")], []
    if payload.get("type") == "message-event":
        status = body.get("type")
        if status == "enqueued":
            status = "sent"
        ids = tuple(str(body[k]) for k in ("id", "gsId") if body.get(k))
        if ids and status in ("sent", "delivered", "read", "failed"):
            reason = ((body.get("payload") or {}).get("reason")) or ""
            return [], [Receipt(ids, status, reason)]
    return [], []


PARSERS = {
    "interakt": parse_interakt,
    "meta_cloud": parse_meta_cloud,
    "wati": parse_wati,
    "gupshup": parse_gupshup,
}


# ============================================================
# Recording
# ============================================================

def handle(provider: str, payload: dict):
    """Parse and record one webhook post. Unknown shapes are logged, not raised."""
    parser = PARSERS.get(provider)
    if parser is None:
        logger.warning(
            f"[WA Webhook] No parser for provider {provider!r}; event not recorded. "
            f"Keys: {sorted(payload)[:20]}"
        )
        return
    inbound, receipts = parser(payload if isinstance(payload, dict) else {})
    for receipt in receipts:
        record_receipt(receipt)
    for message in inbound:
        record_inbound(provider, message)


def record_receipt(receipt: Receipt):
    from apps.communications.models import WhatsAppMessage

    ids = [i for i in receipt.message_ids if i]
    if not ids or receipt.status not in ("sent", "delivered", "read", "failed"):
        return
    qs = WhatsAppMessage.objects.filter(provider_message_id__in=ids, direction="outbound")

    if receipt.status == "failed":
        qs.update(status="failed", error_message=receipt.error[:500])
        return

    now = timezone.now()
    rank = STATUS_RANK[receipt.status]
    # Never step backwards: a late "delivered" must not undo "read".
    behind = [s for s, r in STATUS_RANK.items() if r < rank]
    update = {"status": receipt.status}
    if receipt.status == "delivered":
        update["delivered_at"] = now
    elif receipt.status == "read":
        update["read_at"] = now
    qs.filter(status__in=behind).update(**update)


def lead_for_number(phone: str):
    """The lead a message from this number belongs to, or None."""
    from apps.leads.models import Lead

    if not phone:
        return None
    return (
        Lead.objects.filter(Q(phone=phone) | Q(alternate_phone=phone), is_deleted=False)
        .order_by(F("last_contacted_at").desc(nulls_last=True), "-created_at")
        .first()
    )


def record_inbound(provider: str, message: Inbound):
    from apps.communications.models import WhatsAppMessage
    from apps.leads.models import LeadActivity

    phone = normalize_indian_phone(message.phone)
    if not phone or not (message.text or message.message_type != "text"):
        return
    if message.message_id and WhatsAppMessage.objects.filter(
        provider_message_id=message.message_id, direction="inbound",
    ).exists():
        return  # a provider retry

    lead = lead_for_number(phone)
    if lead is None:
        logger.info(f"[WA Webhook] Inbound from unknown number (provider={provider})")
        return

    valid_types = {k for k, _ in WhatsAppMessage.MESSAGE_TYPES}
    WhatsAppMessage.objects.create(
        lead=lead, direction="inbound",
        message_type=message.message_type if message.message_type in valid_types else "unsupported",
        content=message.text, provider=provider, status="received",
        provider_message_id=message.message_id,
    )
    if lead.assigned_to_id:
        from django.db import connection

        from apps.core.consumers import send_agent_notification

        send_agent_notification(
            schema_name=connection.schema_name,
            agent_id=lead.assigned_to_id,
            event_type="message_received",
            data={
                "lead_id": lead.pk,
                "lead_name": lead.name,
                "channel": "whatsapp",
                "message_preview": message.text[:100],
            },
        )
    LeadActivity.objects.create(
        lead=lead, activity_type="whatsapp",
        description=f"WhatsApp reply received: {message.text[:100]}",
    )
