"""
TeleCRM Backend — apps/automation/hooks.py

The one place other apps tell workflows that something happened. Each hook
is a thin, never-raising call into the engine, so a workflow problem can
never fail the save, call or webhook that set it off.
"""
import logging

from apps.automation.constants import Trigger

logger = logging.getLogger(__name__)


def _fire(*args, **kwargs):
    try:
        from apps.automation.services.engine import fire

        return fire(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.error("[Workflows] hook failed: %s", exc, exc_info=True)
        return []


def lead_saved(lead, *, created: bool, old_status=None, old_owner_id=None):
    from django.utils import timezone

    stamp = int(timezone.now().timestamp())
    if created:
        _fire(Trigger.LEAD_CREATED, lead, event_key=f"created:{lead.pk}",
              context={"source": lead.source})
        if lead.assigned_to_id:
            _fire(Trigger.LEAD_ASSIGNED, lead, event_key=f"assigned:{lead.pk}:{lead.assigned_to_id}:{stamp}",
                  context={"agent_id": lead.assigned_to_id})
        return
    if old_status is not None and old_status != lead.status:
        _fire(Trigger.LEAD_STATUS_CHANGED, lead, event_key=f"status:{lead.pk}:{lead.status}:{stamp}",
              context={"old_status": old_status, "new_status": lead.status})
    if lead.assigned_to_id and old_owner_id != lead.assigned_to_id:
        _fire(Trigger.LEAD_ASSIGNED, lead, event_key=f"assigned:{lead.pk}:{lead.assigned_to_id}:{stamp}",
              context={"agent_id": lead.assigned_to_id, "previous_agent_id": old_owner_id})


def call_applied(call, lead):
    """A call was saved on the lead, or its outcome was set."""
    if lead is None:
        return
    base = {"call_id": str(call.pk), "direction": call.direction, "agent_id": call.agent_id}
    trigger = Trigger.CALL_CONNECTED if call.is_connected else Trigger.CALL_NOT_CONNECTED
    _fire(trigger, lead, event_key=f"call:{call.pk}", context=base)
    if call.disposition_id:
        _fire(Trigger.CALL_OUTCOME, lead, event_key=f"outcome:{call.pk}:{call.disposition_id}",
              context={**base, "disposition_id": call.disposition_id})


def whatsapp_received(lead, *, message_id: str, text: str, account_id=None):
    if lead is None:
        return
    _fire(Trigger.WHATSAPP_RECEIVED, lead, event_key=f"wa:{message_id}"[:150],
          context={"text": (text or "")[:1000], "account_id": account_id, "message_id": message_id})
