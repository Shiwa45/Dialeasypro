"""
TeleCRM Backend — apps/authentication/notifications.py

One way to tell an agent something.

Before this, a follow-up reminder was pushed straight down a WebSocket by the
Celery task and nothing else happened. If the agent was not connected at that
exact second the notification ceased to exist — and a reminder fires precisely
when the agent is not sitting in the CRM. Nothing was stored, so there was no
unread count, no history, and no way for the mobile app to ask what it missed
while it was closed.

`notify()` now does three things in order, and the first one is the one that
matters:

  1. Write the row. Durable, and the only step that must not fail.
  2. Push it over the agent's WebSocket, so an open tab updates instantly.
  3. Hand it to the push transport for a device that is not looking.

Steps 2 and 3 are best-effort. A dead channel layer or an unconfigured push
provider must never lose the notification or break the thing that raised it.
"""
import logging

from django.db import connection
from django.utils import timezone

from apps.authentication.models import Notification, NotificationKind

logger = logging.getLogger(__name__)


def notify(
    recipient,
    kind,
    title,
    *,
    body="",
    lead_id=None,
    followup_id=None,
    url="",
    push=True,
):
    """
    Record a notification for one agent and deliver it.

    `recipient` may be an Agent or an agent id. Returns the Notification, or
    None when there is no recipient to notify — an unassigned lead's follow-up
    has nobody to tell, and that is not an error.
    """
    recipient_id = getattr(recipient, "pk", recipient)
    if not recipient_id:
        return None

    note = Notification.objects.create(
        recipient_id=recipient_id,
        kind=kind,
        title=title[:160],
        body=body,
        lead_id_ref=lead_id,
        followup_id_ref=followup_id,
        url=url,
    )

    payload = serialize(note)

    # ---- 2. The open tab -------------------------------------
    try:
        from apps.core.consumers import send_agent_notification

        send_agent_notification(
            schema_name=connection.schema_name,
            agent_id=recipient_id,
            # The consumer routes on this name; it has a followup_reminder
            # handler already, and `notification` is the general one.
            event_type="notification",
            data=payload,
        )
    except Exception as exc:
        # A notification that reached the database but not the socket is
        # still delivered — the client picks it up on its next poll or load.
        logger.warning("[Notify] socket push failed for agent %s: %s", recipient_id, exc)

    # ---- 3. The device that is not looking -------------------
    if push:
        try:
            from apps.authentication.push import send_push

            send_push(recipient_id, title=note.title, body=note.body, data=payload)
        except Exception as exc:
            logger.warning("[Notify] push failed for agent %s: %s", recipient_id, exc)

    return note


def notify_many(recipients, kind, title, **kwargs):
    """notify() for several agents. Duplicate ids are collapsed."""
    seen = set()
    out = []
    for r in recipients:
        rid = getattr(r, "pk", r)
        if not rid or rid in seen:
            continue
        seen.add(rid)
        note = notify(r, kind, title, **kwargs)
        if note:
            out.append(note)
    return out


def serialize(note) -> dict:
    """The shape both clients read. Kept here so the socket frame and the REST
    response can never drift apart."""
    return {
        "id": note.pk,
        "kind": note.kind,
        "title": note.title,
        "body": note.body,
        "lead_id": note.lead_id_ref,
        "followup_id": note.followup_id_ref,
        "url": note.url,
        "is_read": note.is_read,
        "created_at": note.created_at.isoformat(),
    }


# ============================================================
# Follow-ups
# ============================================================

def _when(dt) -> str:
    """A time an agent can read, in the tenant's own timezone."""
    return timezone.localtime(dt).strftime("%d %b, %I:%M %p")


def followup_scheduled(followup):
    """
    Somebody put a follow-up on this agent's lead.

    Raised when the follow-up is created, not when it comes due — an agent
    should know a commitment has been made for them the moment it is made,
    rather than finding out half an hour before it is expected.
    """
    lead = followup.lead
    return notify(
        followup.assigned_to_id,
        NotificationKind.FOLLOWUP_SCHEDULED,
        f"Follow-up set for {lead.name}",
        body=(
            f"{followup.get_followup_type_display()} on {_when(followup.scheduled_at)}."
            + (f" {followup.notes}" if followup.notes else "")
        ),
        lead_id=followup.lead_id,
        followup_id=followup.pk,
        url=f"/leads/{followup.lead_id}",
    )


def followup_due(followup, *, overdue=False):
    """The reminder itself, as the scheduled time approaches or passes."""
    lead = followup.lead
    kind = NotificationKind.FOLLOWUP_OVERDUE if overdue else NotificationKind.FOLLOWUP_DUE
    title = (
        f"Overdue: follow up with {lead.name}"
        if overdue
        else f"Follow up with {lead.name}"
    )
    return notify(
        followup.assigned_to_id,
        kind,
        title,
        body=(
            f"{followup.get_followup_type_display()} was due {_when(followup.scheduled_at)}."
            if overdue
            else f"{followup.get_followup_type_display()} at {_when(followup.scheduled_at)}."
        )
        + (f" {followup.notes}" if followup.notes else ""),
        lead_id=followup.lead_id,
        followup_id=followup.pk,
        url=f"/leads/{followup.lead_id}",
    )
