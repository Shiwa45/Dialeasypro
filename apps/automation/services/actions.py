"""
TeleCRM Backend — apps/automation/services/actions.py

One function per workflow action. Each takes (run, step, lead) and returns
(result, detail): StepResult.DONE / SKIPPED / FAILED and a sentence for the
run log. An action never raises for an expected problem (no owner, DND,
WhatsApp not connected) — it says so, and the run carries on.

Changes a workflow makes to a lead are marked `_from_workflow`, so they do
not start other workflows: one rule changing a status must not set off a
rule that changes it back.
"""
import logging

from django.db import connection, transaction
from django.utils import timezone

from apps.automation.constants import Action, StepResult
from apps.automation.services.matching import render_text

logger = logging.getLogger(__name__)

DONE, SKIPPED, FAILED = StepResult.DONE, StepResult.SKIPPED, StepResult.FAILED


def _activity(lead, workflow, text):
    from apps.leads.models import LeadActivity

    LeadActivity.objects.create(
        lead=lead, activity_type="other",
        description=f"Workflow “{workflow.name}”: {text}"[:1000],
        meta={"workflow_id": workflow.pk},
    )


def send_whatsapp(run, step, lead):
    from apps.communications.models import WhatsAppTemplate
    from apps.communications.tasks import send_single_whatsapp
    from apps.communications.whatsapp_accounts import resolve_sender
    from apps.communications.whatsapp_ready import (
        mock_allowed, template_values, unmapped_placeholders, whatsapp_connected,
    )

    if not lead.phone:
        return SKIPPED, "The lead has no phone number."
    template = None
    if step.get("template"):
        template = WhatsAppTemplate.objects.filter(pk=step["template"]).first()
        if template is None or not template.is_active or template.status != "approved":
            return FAILED, "The template is no longer an active, approved template."
        if unmapped_placeholders(template):
            return FAILED, f'"{template.name}" has variables not mapped to lead fields.'
    sender = resolve_sender(account_id=step.get("account"), template=template, lead=lead)
    if sender.error:
        return FAILED, sender.error
    if not whatsapp_connected(sender.account) and not mock_allowed():
        return FAILED, "WhatsApp isn't connected for this number."

    message = render_text(step.get("message", ""), lead) if template is None else ""
    send_single_whatsapp.apply_async(
        kwargs={
            "schema_name": connection.schema_name,
            "lead_id": lead.pk,
            "message": message,
            "template_id": template.pk if template else None,
            "variables": template_values(template, lead) if template else None,
            "account_id": sender.account.pk if sender.account is not None else None,
        },
        queue="notifications",
    )
    what = f'template "{template.name}"' if template else "a message"
    where = f" from {sender.account.sender_label}" if sender.account is not None else ""
    return DONE, f"Sent {what}{where}."


def send_sms(run, step, lead):
    from apps.communications.tasks import send_single_sms

    if not lead.phone:
        return SKIPPED, "The lead has no phone number."
    if lead.is_dnd:
        return SKIPPED, "The lead is on DND — no SMS."
    send_single_sms.apply_async(
        kwargs={
            "schema_name": connection.schema_name,
            "lead_id": lead.pk,
            "message": render_text(step["message"], lead),
            "sender_id": step.get("sender_id", ""),
        },
        queue="notifications",
    )
    return DONE, "SMS sent."


def assign(run, step, lead):
    from apps.authentication.models import Agent
    from apps.automation.models import Workflow

    if step.get("only_if_unassigned") and lead.assigned_to_id:
        return SKIPPED, "The lead already has an owner."
    agents = list(Agent.objects.filter(pk__in=step["agents"], is_active=True).order_by("pk"))
    if not agents:
        return FAILED, "None of the chosen agents is active."
    if step.get("mode") == "round_robin" and len(agents) > 1:
        with transaction.atomic():
            wf = Workflow.objects.select_for_update().get(pk=run.workflow_id)
            state = dict(wf.state or {})
            key = f"rr_{run.current_step}"
            last = state.get(key)
            ids = [a.pk for a in agents]
            nxt = ids[(ids.index(last) + 1) % len(ids)] if last in ids else ids[0]
            state[key] = nxt
            wf.state = state
            wf.save(update_fields=["state", "updated_at"])
        agent = next(a for a in agents if a.pk == nxt)
    else:
        agent = agents[0]
    if lead.assigned_to_id == agent.pk:
        return SKIPPED, f"Already assigned to {agent.name}."
    lead._from_workflow = True
    lead.assign_to(agent)
    return DONE, f"Assigned to {agent.name}."


def change_status(run, step, lead):
    from apps.core.constants import LeadStatus

    if lead.status == step["status"]:
        return SKIPPED, "The lead already has that status."
    label = dict(LeadStatus.CHOICES).get(step["status"], step["status"])
    lead._from_workflow = True
    lead.update_status(step["status"])
    return DONE, f"Status changed to {label}."


def create_followup(run, step, lead):
    from datetime import timedelta

    from apps.leads.models import FollowUp

    if not lead.assigned_to_id:
        return SKIPPED, "The lead has no owner to follow up."
    when = timezone.now() + timedelta(hours=step.get("in_hours", 24))
    FollowUp.objects.create(
        lead=lead, assigned_to_id=lead.assigned_to_id, followup_type=step.get("followup_type", "call"),
        scheduled_at=when, notes=render_text(step.get("note", ""), lead) or f"From workflow “{run.workflow.name}”",
        is_auto=True,
    )
    _activity(lead, run.workflow, f"follow-up booked for {timezone.localtime(when):%d %b, %I:%M %p}.")
    return DONE, f"Follow-up booked for {timezone.localtime(when):%d %b %Y, %I:%M %p}."


def add_note(run, step, lead):
    from apps.leads.models import LeadNote

    LeadNote.objects.create(lead=lead, agent=None, content=render_text(step["text"], lead))
    return DONE, "Note added."


def notify(run, step, lead):
    from apps.authentication.models import NotificationKind
    from apps.authentication.notifications import notify as send_notification

    recipient = step.get("agent") if step.get("to") == "agent" else lead.assigned_to_id
    if not recipient:
        return SKIPPED, "The lead has no owner to notify."
    send_notification(
        recipient, NotificationKind.SYSTEM, render_text(step["message"], lead),
        body=f"{lead.name} · {lead.phone}", lead_id=lead.pk,
    )
    return DONE, "Agent notified."


def webhook(run, step, lead):
    import requests

    from apps.core.safe_fetch import UnsafeURL, _check_public

    url = step["url"]
    try:
        _check_public(url)
    except UnsafeURL as exc:
        return FAILED, f"Webhook refused: {exc}"
    payload = {
        "event": run.trigger,
        "workflow": {"id": run.workflow_id, "name": run.workflow.name},
        "run_id": run.pk,
        "lead": {
            "id": lead.pk, "name": lead.name, "phone": lead.phone, "email": lead.email,
            "city": lead.city, "status": lead.status, "source": lead.source,
            "assigned_to": getattr(lead.assigned_to, "name", None),
            "tags": lead.tags or [],
        },
        "context": run.context or {},
    }
    try:
        resp = requests.post(url, json=payload, timeout=10, allow_redirects=False)
    except requests.RequestException as exc:
        return FAILED, f"Webhook could not be reached: {exc.__class__.__name__}."
    if resp.status_code >= 400:
        return FAILED, f"Webhook answered {resp.status_code}."
    _activity(lead, run.workflow, f"webhook sent ({resp.status_code}).")
    return DONE, f"Webhook answered {resp.status_code}."


HANDLERS = {
    Action.SEND_WHATSAPP: send_whatsapp,
    Action.SEND_SMS: send_sms,
    Action.ASSIGN: assign,
    Action.CHANGE_STATUS: change_status,
    Action.CREATE_FOLLOWUP: create_followup,
    Action.ADD_NOTE: add_note,
    Action.NOTIFY: notify,
    Action.WEBHOOK: webhook,
}
