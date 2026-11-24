"""
TeleCRM Backend — apps/communications/inbox.py

The WhatsApp inbox: every lead who has written to one of the tenant's
WhatsApp numbers, newest conversation first, with what is still unread.

Before this a customer's reply was stored on the lead and shown only to
somebody who happened to open that lead's WhatsApp tab. Nothing listed the
leads that had written, nothing counted what was unread, and the live
"message_received" event the webhook sent went to no screen that listened.

A conversation here is a LEAD, not a WhatsAppConversation row: those exist only
for Meta Cloud numbers, and a lead's thread already spans every number and
provider it has talked on. Leads that have only ever been messaged (a bulk
campaign of ten thousand) are not conversations until the customer writes.

Read state lives on the inbound message (`seen_at`) and is shared by the team:
whoever opens the thread clears it for everyone, as in a shared mailbox.
"""
import logging
from datetime import timedelta

from django.db.models import Count, Exists, Max, OuterRef, Q, Subquery
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Meta's customer-service window: a business may send free text only this
#: long after the customer's last message; after it, only a template.
REPLY_WINDOW = timedelta(hours=24)

#: Newest messages returned for one thread.
THREAD_LIMIT = 200


def _visible_leads(agent):
    """
    The leads this person may see, as a flat id subquery.

    `leads_visible_to` can be `.distinct()` over team joins; aggregating over
    it directly would count a message once per join row. Filtering by id
    keeps the counts honest.
    """
    from apps.leads.models import Lead
    from apps.leads.views import leads_visible_to

    return Lead.objects.filter(pk__in=leads_visible_to(agent).values("pk"))


def conversations(agent, params=None):
    """
    The inbox for `agent`: one row per lead that has written in, newest
    activity first.

    `params` (a QueryDict or dict) narrows it:
      unread=1        only conversations with unread messages
      mine=1          only leads assigned to me
      unassigned=1    only leads with no owner
      agent=<id>      only leads assigned to this agent
      account=<id>    only conversations that used this WhatsApp number
      q=<text>        lead name or phone contains
    """
    from apps.communications.models import WhatsAppMessage

    params = params or {}
    last = WhatsAppMessage.objects.filter(lead=OuterRef("pk")).order_by("-created_at")

    qs = (
        _visible_leads(agent)
        .annotate(
            wa_last_at=Max("whatsapp_messages__created_at"),
            wa_last_inbound_at=Max(
                "whatsapp_messages__created_at",
                filter=Q(whatsapp_messages__direction="inbound"),
            ),
            wa_unread=Count(
                "whatsapp_messages",
                filter=Q(whatsapp_messages__direction="inbound",
                         whatsapp_messages__seen_at__isnull=True),
            ),
            wa_last_text=Subquery(last.values("content")[:1]),
            wa_last_direction=Subquery(last.values("direction")[:1]),
            wa_last_type=Subquery(last.values("message_type")[:1]),
            wa_last_status=Subquery(last.values("status")[:1]),
            wa_last_account=Subquery(last.values("account_id")[:1]),
            wa_last_template=Subquery(last.values("template__name")[:1]),
        )
        .filter(wa_last_inbound_at__isnull=False)
        .select_related("assigned_to")
    )

    def flag(name):
        return str(params.get(name, "")).lower() in ("1", "true", "yes")

    if flag("unread"):
        qs = qs.filter(wa_unread__gt=0)
    if flag("mine"):
        qs = qs.filter(assigned_to=agent)
    if flag("unassigned"):
        qs = qs.filter(assigned_to__isnull=True)
    if (owner := params.get("agent")) not in (None, ""):
        try:
            qs = qs.filter(assigned_to_id=int(owner))
        except (TypeError, ValueError):
            pass
    if (account := params.get("account")) not in (None, ""):
        try:
            qs = qs.filter(Exists(
                WhatsAppMessage.objects.filter(lead=OuterRef("pk"), account_id=int(account))
            ))
        except (TypeError, ValueError):
            pass
    if term := str(params.get("q", "")).strip():
        qs = qs.filter(Q(name__icontains=term) | Q(phone__icontains=term))

    return qs.order_by("-wa_last_at", "-pk")


def window(last_inbound_at, now=None):
    """Whether free text may still be sent, and until when."""
    if last_inbound_at is None:
        return {"open": False, "closes_at": None}
    closes = last_inbound_at + REPLY_WINDOW
    return {"open": closes > (now or timezone.now()), "closes_at": closes}


def summary(agent):
    """Unread totals for the badge."""
    from apps.communications.models import WhatsAppMessage

    totals = WhatsAppMessage.objects.filter(
        direction="inbound", seen_at__isnull=True,
        lead__in=_visible_leads(agent).values("pk"),
    ).aggregate(messages=Count("pk"), conversations=Count("lead", distinct=True))
    return {
        "unread_conversations": totals["conversations"] or 0,
        "unread_messages": totals["messages"] or 0,
    }


def mark_seen(lead):
    """Clear the lead's unread messages. Returns how many were cleared."""
    from apps.communications.models import WhatsAppMessage

    return WhatsAppMessage.objects.filter(
        lead=lead, direction="inbound", seen_at__isnull=True,
    ).update(seen_at=timezone.now())


def unread_count(lead):
    from apps.communications.models import WhatsAppMessage

    return WhatsAppMessage.objects.filter(
        lead=lead, direction="inbound", seen_at__isnull=True,
    ).count()


def message_arrived(lead, preview, *, is_new_lead=False):
    """
    Tell people a customer has written. Called once per stored inbound
    message, after it is saved; never raises.

    - Every open CRM tab for the lead's owner, and the admins' monitor
      screens, get a live `whatsapp_inbox` event so the inbox and its badge
      refresh at once.
    - The owner gets a notification (bell, phone) — but only when this
      message starts a new unread run. A customer who sends five messages in
      a row is one notification, not five; the inbox count says the rest.
    """
    from django.db import connection

    preview = (preview or "").strip()[:100] or "[media]"
    payload = {
        "lead_id": lead.pk,
        "lead_name": lead.name,
        "phone": lead.phone,
        "channel": "whatsapp",
        "message_preview": preview,
        "new_lead": bool(is_new_lead),
    }
    schema = connection.schema_name

    try:
        from apps.core.consumers import broadcast_to_monitors, send_agent_notification

        if lead.assigned_to_id:
            send_agent_notification(schema_name=schema, agent_id=lead.assigned_to_id,
                                    event_type="whatsapp_inbox", data=payload)
        broadcast_to_monitors(schema_name=schema, event_type="whatsapp_inbox", data=payload)
    except Exception as exc:  # noqa: BLE001 — realtime is never load-bearing
        logger.debug("[WA Inbox] realtime push skipped: %s", exc)

    if not lead.assigned_to_id:
        return
    try:
        if unread_count(lead) != 1:
            return
        from apps.authentication.models import NotificationKind
        from apps.authentication.notifications import notify

        notify(
            lead.assigned_to_id,
            NotificationKind.WHATSAPP_REPLY,
            f"{lead.name} wrote on WhatsApp" if not is_new_lead else f"New WhatsApp lead: {lead.name}",
            body=preview,
            lead_id=lead.pk,
            url=f"/inbox/{lead.pk}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[WA Inbox] notification for lead %s failed: %s", lead.pk, exc)
