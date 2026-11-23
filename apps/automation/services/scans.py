"""
TeleCRM Backend — apps/automation/services/scans.py

Triggers that are a state, not an event — "a follow-up has been missed",
"a lead has gone quiet" — are found by a scan every few minutes. Each match
fires with an event key that names the occurrence, so a lead is not chased
twice for the same missed follow-up or the same quiet spell.
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.automation.constants import Trigger
from apps.automation.services.engine import fire

#: Most leads one workflow picks up per scan — a backlog drains over a few
#: scans instead of flooding WhatsApp at once.
SCAN_LIMIT = 200

#: Statuses that are finished: a quiet won or lost lead is not "inactive".
CLOSED_STATUSES = ("converted", "lost", "not_interested", "duplicate", "invalid")


def scan_missed_followups(workflow) -> int:
    from apps.leads.models import FollowUp

    minutes = int((workflow.trigger_config or {}).get("minutes", 30))
    now = timezone.now()
    due = (FollowUp.objects
           .filter(is_completed=False, lead__is_deleted=False,
                   scheduled_at__lte=now - timedelta(minutes=minutes),
                   scheduled_at__gte=now - timedelta(minutes=minutes) - timedelta(days=2))
           .select_related("lead")
           .order_by("scheduled_at")[:SCAN_LIMIT])
    started = 0
    for fu in due:
        started += len(fire(Trigger.FOLLOWUP_MISSED, fu.lead, only=workflow,
                            event_key=f"followup:{fu.pk}",
                            context={"followup_id": fu.pk, "scheduled_at": fu.scheduled_at.isoformat()}))
    return started


def scan_inactive_leads(workflow) -> int:
    from apps.leads.models import Lead

    days = int((workflow.trigger_config or {}).get("days", 3))
    cutoff = timezone.now() - timedelta(days=days)
    leads = (Lead.objects
             .filter(is_deleted=False)
             .exclude(status__in=CLOSED_STATUSES)
             .filter(Q(last_contacted_at__lte=cutoff) | Q(last_contacted_at__isnull=True, created_at__lte=cutoff))
             .exclude(workflow_runs__workflow=workflow, workflow_runs__created_at__gte=cutoff)
             .order_by("last_contacted_at", "created_at")[:SCAN_LIMIT])
    started = 0
    for lead in leads:
        since = (lead.last_contacted_at or lead.created_at).date().isoformat()
        started += len(fire(Trigger.LEAD_INACTIVE, lead, only=workflow,
                            event_key=f"idle:{lead.pk}:{since}",
                            context={"quiet_since": since, "days": days}))
    return started


def run_scans() -> int:
    from apps.automation.models import Workflow

    started = 0
    for wf in Workflow.objects.filter(is_active=True, trigger__in=Trigger.SCANNED):
        if wf.trigger == Trigger.FOLLOWUP_MISSED:
            started += scan_missed_followups(wf)
        elif wf.trigger == Trigger.LEAD_INACTIVE:
            started += scan_inactive_leads(wf)
    return started
