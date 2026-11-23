"""
TeleCRM Backend — apps/automation/services/matching.py

Does this event, and this lead, fit a workflow? Pure functions over the
saved options, so every rule is testable without a database round trip.
"""
from apps.automation.constants import Trigger


def trigger_matches(workflow, context: dict) -> bool:
    """The trigger's own options against the event that happened."""
    cfg = workflow.trigger_config or {}
    trigger = workflow.trigger
    context = context or {}

    if trigger == Trigger.LEAD_STATUS_CHANGED:
        to, frm = cfg.get("to") or [], cfg.get("from") or []
        if to and context.get("new_status") not in to:
            return False
        if frm and context.get("old_status") not in frm:
            return False
        return True

    if trigger == Trigger.CALL_OUTCOME:
        wanted = cfg.get("dispositions") or []
        return not wanted or context.get("disposition_id") in wanted

    if trigger in (Trigger.CALL_CONNECTED, Trigger.CALL_NOT_CONNECTED):
        direction = cfg.get("direction") or "any"
        if direction == "any":
            return True
        call_dir = (context.get("direction") or "").lower()
        if direction == "outbound":
            return call_dir == "outbound"
        return call_dir in ("inbound", "missed")

    if trigger == Trigger.WHATSAPP_RECEIVED:
        keywords = cfg.get("keywords") or []
        if not keywords:
            return True
        text = " ".join((context.get("text") or "").lower().split())
        if cfg.get("match") == "exact":
            return text in keywords
        return any(k in text for k in keywords)

    return True


def lead_matches(lead, conditions: dict) -> bool:
    """Every condition list given must contain the lead's value."""
    c = conditions or {}
    if c.get("sources") and lead.source not in c["sources"]:
        return False
    if c.get("statuses") and lead.status not in c["statuses"]:
        return False
    if c.get("batches") and lead.batch_id not in c["batches"]:
        return False
    if c.get("assigned_to"):
        owner = lead.assigned_to_id or 0
        if owner not in c["assigned_to"]:
            return False
    if c.get("cities"):
        city = (lead.city or "").strip().lower()
        if city not in {x.lower() for x in c["cities"]}:
            return False
    if c.get("tags"):
        tags = {str(t).lower() for t in (lead.tags or [])}
        if not tags & {t.lower() for t in c["tags"]}:
            return False
    return True


def in_quiet_hours(workflow, local_time) -> bool:
    """Quiet hours may cross midnight (21:00 → 09:00)."""
    if not workflow.quiet_hours_enabled:
        return False
    start, end = workflow.quiet_start, workflow.quiet_end
    if isinstance(start, str):
        from datetime import time

        start = time.fromisoformat(start)
        end = time.fromisoformat(end)
    t = local_time.replace(tzinfo=None) if hasattr(local_time, "tzinfo") else local_time
    if start == end:
        return False
    if start < end:
        return start <= t < end
    return t >= start or t < end


def quiet_hours_end(workflow, now):
    """The next moment quiet hours end, as an aware datetime."""
    from datetime import datetime, time, timedelta

    from django.utils import timezone

    end = workflow.quiet_end
    if isinstance(end, str):
        end = time.fromisoformat(end)
    local = timezone.localtime(now)
    candidate = timezone.make_aware(datetime.combine(local.date(), end), local.tzinfo)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate


def render_text(text: str, lead) -> str:
    """{name}, {first_name}, {phone}, {city}, {agent_name} … from the lead."""
    import re

    from apps.communications.whatsapp_ready import LEAD_VARIABLE_FIELDS, lead_value

    def sub(m):
        key = m.group(1)
        if key in LEAD_VARIABLE_FIELDS:
            return lead_value(lead, key)
        return m.group(0)

    return re.sub(r"\{([a-z_]+)\}", sub, text or "")
