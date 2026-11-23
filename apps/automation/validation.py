"""
TeleCRM Backend — apps/automation/validation.py

Checks a workflow's trigger options, conditions and steps before they are
saved, and returns them cleaned. Every message names the step it is about
("Step 3: pick a template"), because the editor shows them next to it.
"""
from rest_framework.exceptions import ValidationError

from apps.automation.constants import MAX_STEPS, MAX_WAIT_SECONDS, WAIT_UNITS, Action, Trigger


def _ids(value, what):
    if value in (None, ""):
        return []
    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"{what} must be a list.")
    out = []
    for v in value:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            raise ValidationError(f"{what}: {v!r} is not an id.")
    return out


def _strings(value, what, allowed=None):
    if value in (None, ""):
        return []
    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"{what} must be a list.")
    out = [str(v).strip() for v in value if str(v).strip()]
    if allowed is not None:
        bad = [v for v in out if v not in allowed]
        if bad:
            raise ValidationError(f"{what}: unknown value(s) {', '.join(bad)}.")
    return out


def _statuses():
    from apps.core.constants import LeadStatus

    return {k for k, _ in LeadStatus.CHOICES}


def _sources():
    from apps.core.constants import LeadSource

    return {k for k, _ in LeadSource.CHOICES}


def _positive_int(value, what, low, high):
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{what} must be a number.")
    if not (low <= n <= high):
        raise ValidationError(f"{what} must be between {low} and {high}.")
    return n


# ============================================================
# Trigger options
# ============================================================

def clean_trigger_config(trigger: str, config) -> dict:
    config = config or {}
    if not isinstance(config, dict):
        raise ValidationError({"trigger_config": "Must be an object."})
    try:
        if trigger == Trigger.LEAD_STATUS_CHANGED:
            out = {
                "to": _strings(config.get("to"), "To status", _statuses()),
                "from": _strings(config.get("from"), "From status", _statuses()),
            }
            if not out["to"] and not out["from"]:
                raise ValidationError("Pick the status(es) the lead moves to.")
            return out
        if trigger == Trigger.CALL_OUTCOME:
            from apps.calls.models import CallDisposition

            ids = _ids(config.get("dispositions"), "Call outcomes")
            known = set(CallDisposition.objects.filter(pk__in=ids).values_list("pk", flat=True))
            if set(ids) - known:
                raise ValidationError("A chosen call outcome no longer exists.")
            return {"dispositions": ids}
        if trigger == Trigger.WHATSAPP_RECEIVED:
            keywords = [k.lower() for k in _strings(config.get("keywords"), "Keywords")][:30]
            match = config.get("match") or "contains"
            if match not in ("contains", "exact"):
                raise ValidationError("Keyword match must be 'contains' or 'exact'.")
            return {"keywords": keywords, "match": match}
        if trigger == Trigger.FOLLOWUP_MISSED:
            return {"minutes": _positive_int(config.get("minutes", 30), "Minutes late", 5, 7 * 24 * 60)}
        if trigger == Trigger.LEAD_INACTIVE:
            return {"days": _positive_int(config.get("days", 3), "Days without contact", 1, 365)}
        if trigger in (Trigger.CALL_CONNECTED, Trigger.CALL_NOT_CONNECTED):
            direction = config.get("direction") or "any"
            if direction not in ("any", "outbound", "inbound"):
                raise ValidationError("Call direction must be any, outbound or inbound.")
            return {"direction": direction}
        return {}
    except ValidationError as exc:
        raise ValidationError({"trigger_config": exc.detail})


# ============================================================
# Conditions
# ============================================================

def clean_conditions(conditions) -> dict:
    from apps.authentication.models import Agent
    from apps.leads.models import LeadBatch

    conditions = conditions or {}
    if not isinstance(conditions, dict):
        raise ValidationError({"conditions": "Must be an object."})
    try:
        out = {
            "sources": _strings(conditions.get("sources"), "Sources", _sources()),
            "statuses": _strings(conditions.get("statuses"), "Statuses", _statuses()),
            "batches": _ids(conditions.get("batches"), "Batches"),
            "assigned_to": _ids(conditions.get("assigned_to"), "Assigned to"),
            "cities": _strings(conditions.get("cities"), "Cities"),
            "tags": _strings(conditions.get("tags"), "Tags"),
        }
        if out["batches"] and LeadBatch.objects.filter(pk__in=out["batches"]).count() != len(set(out["batches"])):
            raise ValidationError("A chosen batch no longer exists.")
        agents = [a for a in out["assigned_to"] if a]
        if agents and Agent.objects.filter(pk__in=agents).count() != len(set(agents)):
            raise ValidationError("A chosen agent no longer exists.")
    except ValidationError as exc:
        raise ValidationError({"conditions": exc.detail})
    return {k: v for k, v in out.items() if v}


# ============================================================
# Steps
# ============================================================

def _clean_step(i: int, step) -> dict:
    from apps.authentication.models import Agent
    from apps.communications.models import WhatsAppConfig, WhatsAppTemplate

    label = f"Step {i + 1}"
    if not isinstance(step, dict):
        raise ValidationError(f"{label}: must be an object.")
    kind = step.get("type")
    if kind not in {k for k, _ in Action.CHOICES}:
        raise ValidationError(f"{label}: unknown step type {kind!r}.")
    out = {"type": kind}

    # Guards, checked when the step runs.
    if step.get("only_if_no_reply"):
        out["only_if_no_reply"] = True
    if step.get("only_if_status_in"):
        out["only_if_status_in"] = _strings(step.get("only_if_status_in"), f"{label}: status", _statuses())

    if kind == Action.WAIT:
        unit = step.get("unit") or "hours"
        if unit not in WAIT_UNITS:
            raise ValidationError(f"{label}: wait in minutes, hours or days.")
        amount = _positive_int(step.get("amount"), f"{label}: wait", 1, 10_000)
        if amount * WAIT_UNITS[unit] > MAX_WAIT_SECONDS:
            raise ValidationError(f"{label}: a wait can be at most 90 days.")
        out.update(amount=amount, unit=unit)

    elif kind == Action.SEND_WHATSAPP:
        template_id = step.get("template")
        message = (step.get("message") or "").strip()
        if template_id in (None, "") and not message:
            raise ValidationError(f"{label}: pick a template or write a message.")
        if template_id not in (None, ""):
            template = WhatsAppTemplate.objects.filter(pk=template_id).first()
            if template is None or not template.is_active:
                raise ValidationError(f"{label}: that template is switched off or gone.")
            from apps.communications.whatsapp_ready import unmapped_placeholders

            missing = unmapped_placeholders(template)
            if missing:
                raise ValidationError(
                    f'{label}: map the variables of "{template.name}" to lead fields first '
                    f"({', '.join('{{%d}}' % n for n in missing)})."
                )
            out["template"] = template.pk
        else:
            if len(message) > 4096:
                raise ValidationError(f"{label}: a WhatsApp message is at most 4096 characters.")
            out["message"] = message
        account_id = step.get("account")
        if account_id not in (None, ""):
            account = WhatsAppConfig.objects.filter(pk=account_id).first()
            if account is None:
                raise ValidationError(f"{label}: that WhatsApp number no longer exists.")
            if "template" in out:
                template = WhatsAppTemplate.objects.get(pk=out["template"])
                if not template.usable_from(account):
                    raise ValidationError(
                        f'{label}: "{template.name}" can\'t be sent from {account.label} '
                        "(it belongs to another WhatsApp Business Account)."
                    )
            out["account"] = account.pk

    elif kind == Action.SEND_SMS:
        message = (step.get("message") or "").strip()
        if not message:
            raise ValidationError(f"{label}: write the SMS.")
        if len(message) > 1000:
            raise ValidationError(f"{label}: an SMS is at most 1000 characters.")
        out["message"] = message
        sender = (step.get("sender_id") or "").strip()[:11]
        if sender:
            out["sender_id"] = sender

    elif kind == Action.ASSIGN:
        agents = _ids(step.get("agents"), f"{label}: agents")
        if not agents:
            raise ValidationError(f"{label}: pick at least one agent.")
        found = set(Agent.objects.filter(pk__in=agents).values_list("pk", flat=True))
        if set(agents) - found:
            raise ValidationError(f"{label}: a chosen agent no longer exists.")
        mode = step.get("mode") or ("round_robin" if len(agents) > 1 else "fixed")
        if mode not in ("fixed", "round_robin"):
            raise ValidationError(f"{label}: assign to one agent or round-robin.")
        out.update(agents=agents, mode=mode)
        if step.get("only_if_unassigned"):
            out["only_if_unassigned"] = True

    elif kind == Action.CHANGE_STATUS:
        status = step.get("status")
        if status not in _statuses():
            raise ValidationError(f"{label}: pick a status.")
        out["status"] = status

    elif kind == Action.CREATE_FOLLOWUP:
        out["in_hours"] = _positive_int(step.get("in_hours", 24), f"{label}: hours", 0, 24 * 90)
        out["note"] = (step.get("note") or "").strip()[:500]
        from apps.core.constants import FollowUpType

        ftype = step.get("followup_type") or FollowUpType.CALL
        if ftype not in {k for k, _ in FollowUpType.CHOICES}:
            raise ValidationError(f"{label}: unknown follow-up type.")
        out["followup_type"] = ftype

    elif kind == Action.ADD_NOTE:
        text = (step.get("text") or "").strip()
        if not text:
            raise ValidationError(f"{label}: write the note.")
        out["text"] = text[:2000]

    elif kind == Action.NOTIFY:
        to = step.get("to") or "owner"
        if to not in ("owner", "agent"):
            raise ValidationError(f"{label}: notify the lead owner or a chosen agent.")
        out["to"] = to
        if to == "agent":
            agent_id = step.get("agent")
            if not agent_id or not Agent.objects.filter(pk=agent_id).exists():
                raise ValidationError(f"{label}: pick the agent to notify.")
            out["agent"] = int(agent_id)
        message = (step.get("message") or "").strip()
        if not message:
            raise ValidationError(f"{label}: write the notification.")
        out["message"] = message[:300]

    elif kind == Action.WEBHOOK:
        url = (step.get("url") or "").strip()
        if not url.startswith("https://") or len(url) > 500:
            raise ValidationError(f"{label}: the webhook URL must start with https://.")
        out["url"] = url

    return out


def clean_steps(steps) -> list:
    if not isinstance(steps, list):
        raise ValidationError({"steps": "Must be a list."})
    if not steps:
        raise ValidationError({"steps": "Add at least one step."})
    if len(steps) > MAX_STEPS:
        raise ValidationError({"steps": f"A workflow can have at most {MAX_STEPS} steps."})
    cleaned = []
    for i, step in enumerate(steps):
        try:
            cleaned.append(_clean_step(i, step))
        except ValidationError as exc:
            detail = exc.detail
            if isinstance(detail, list) and len(detail) == 1:
                detail = detail[0]
            raise ValidationError({"steps": detail})
    if all(s["type"] == Action.WAIT for s in cleaned):
        raise ValidationError({"steps": "Add a step that does something — waits alone do nothing."})
    return cleaned
