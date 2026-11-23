"""
TeleCRM Backend — apps/automation/services/engine.py

fire()     — an event happened to a lead: start every active workflow whose
             trigger, options and conditions fit.
advance()  — run a workflow's steps for one lead until it reaches a wait,
             quiet hours or the end.

A run is created once per (workflow, event): a retried webhook, a re-saved
call or a second click cannot send the same message twice. A workflow that
does not repeat uses "lead:<id>" as the event, so a lead goes through it once.

Runs start after the caller's transaction commits — never for a lead whose
save was rolled back — on the "automation" path of the default queue.
"""
import logging
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.db.models import F
from django.utils import timezone

from apps.automation.constants import WAIT_UNITS, Action, RunStatus, StepResult, Trigger
from apps.automation.services import matching

logger = logging.getLogger(__name__)

#: Events a workflow's own changes must not set off again (loop guard).
SELF_TRIGGERABLE = {Trigger.LEAD_STATUS_CHANGED, Trigger.LEAD_ASSIGNED}


def automation_enabled() -> bool:
    """The tenant's plan includes workflows ("Follow-up Automation Rules")."""
    from apps.core.constants import FeatureKey
    from apps.core.middleware import TenantFeatureFlagMiddleware
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(schema_name=connection.schema_name).first()
    if tenant is None:
        return False
    mw = TenantFeatureFlagMiddleware(lambda r: None)
    return bool(mw._get_tenant_features(tenant).get(FeatureKey.FOLLOW_UP_AUTOMATION, False))


def fire(trigger: str, lead, *, event_key: str, context: dict | None = None, only=None) -> list:
    """
    Start the workflows this event sets off. Returns the runs created.
    Never raises: a workflow problem must not fail the save that caused it.
    """
    try:
        return _fire(trigger, lead, event_key=event_key, context=context or {}, only=only)
    except Exception as exc:  # noqa: BLE001
        logger.error("[Workflows] fire(%s) failed for lead %s: %s",
                     trigger, getattr(lead, "pk", None), exc, exc_info=True)
        return []


def _fire(trigger, lead, *, event_key, context, only):
    from apps.automation.models import Workflow, WorkflowRun

    if lead is None or getattr(lead, "is_deleted", False) or not getattr(lead, "pk", None):
        return []
    if trigger in SELF_TRIGGERABLE and getattr(lead, "_from_workflow", False):
        return []
    workflows = [only] if only is not None else list(
        Workflow.objects.filter(is_active=True, trigger=trigger)
    )
    if not workflows or not automation_enabled():
        return []

    created = []
    for wf in workflows:
        if not matching.trigger_matches(wf, context) or not matching.lead_matches(lead, wf.conditions):
            continue
        key = (event_key if wf.repeat else f"lead:{lead.pk}")[:150]
        try:
            with transaction.atomic():
                run, made = WorkflowRun.objects.get_or_create(
                    workflow=wf, event_key=key,
                    defaults={
                        "lead": lead, "trigger": trigger, "context": context,
                        "status": RunStatus.PENDING, "next_run_at": timezone.now(),
                    },
                )
        except IntegrityError:
            continue
        if made:
            created.append(run)
            Workflow.objects.filter(pk=wf.pk).update(
                runs_count=F("runs_count") + 1, last_run_at=timezone.now(),
            )

    schema = connection.schema_name
    for run in created:
        transaction.on_commit(lambda pk=run.pk: _enqueue(schema, pk))
    return created


def start_manual(workflow, lead, actor=None):
    """'Run on a lead' from the editor: the steps, ignoring trigger and conditions."""
    from apps.automation.models import WorkflowRun

    run = WorkflowRun.objects.create(
        workflow=workflow, lead=lead, trigger="manual",
        event_key=f"manual:{lead.pk}:{timezone.now().timestamp()}"[:150],
        context={"started_by": getattr(actor, "name", "")},
        status=RunStatus.PENDING, next_run_at=timezone.now(),
    )
    schema = connection.schema_name
    transaction.on_commit(lambda: _enqueue(schema, run.pk))
    return run


def _enqueue(schema: str, run_id: int):
    from apps.automation.tasks import run_workflow

    run_workflow.apply_async(args=[schema, run_id], queue="default")


# ============================================================
# Running
# ============================================================

def _log(run, step_index, step_type, result, detail):
    entry = {
        "step": step_index, "type": step_type, "result": result,
        "detail": str(detail)[:500], "at": timezone.now().isoformat(),
    }
    run.log = list(run.log or []) + [entry]
    if result == StepResult.FAILED:
        run.has_errors = True
        run.error = str(detail)[:500]


def _replied_since(lead, since) -> bool:
    from apps.communications.models import WhatsAppMessage

    return WhatsAppMessage.objects.filter(lead=lead, direction="inbound", created_at__gt=since).exists()


def _finish(run, status, note=""):
    run.status = status
    run.finished_at = timezone.now()
    run.next_run_at = None
    if note:
        _log(run, run.current_step, "end", StepResult.SKIPPED, note)
    run.save()


def advance(run_id: int) -> None:
    """Run the next steps of one run. Safe to call twice: the row is locked."""
    from apps.automation.models import WorkflowRun
    from apps.automation.services.actions import HANDLERS
    from apps.leads.models import Lead

    with transaction.atomic():
        run = (WorkflowRun.objects.select_for_update()
               .select_related("workflow").filter(pk=run_id).first())
        if run is None or run.status not in RunStatus.OPEN:
            return
        now = timezone.now()
        if run.next_run_at and run.next_run_at > now:
            return
        wf = run.workflow
        if not wf.is_active and run.trigger != "manual":
            return _finish(run, RunStatus.CANCELLED, "The workflow was switched off.")
        lead = Lead.objects.filter(pk=run.lead_id, is_deleted=False).select_related("assigned_to").first()
        if lead is None:
            return _finish(run, RunStatus.CANCELLED, "The lead was deleted.")

        steps = wf.steps or []
        while run.current_step < len(steps):
            i = run.current_step
            step = steps[i]
            kind = step.get("type")

            if kind == Action.WAIT:
                seconds = int(step.get("amount", 1)) * WAIT_UNITS.get(step.get("unit", "hours"), 3600)
                run.next_run_at = now + timedelta(seconds=seconds)
                run.current_step = i + 1
                run.status = RunStatus.WAITING
                _log(run, i, kind, StepResult.WAITING,
                     f"Waiting until {timezone.localtime(run.next_run_at):%d %b, %I:%M %p}.")
                run.save()
                return

            # Guards
            if step.get("only_if_no_reply") and _replied_since(lead, run.created_at):
                _log(run, i, kind, StepResult.SKIPPED, "Skipped — the lead has replied on WhatsApp.")
                run.current_step = i + 1
                continue
            allowed = step.get("only_if_status_in")
            if allowed and lead.status not in allowed:
                _log(run, i, kind, StepResult.SKIPPED, f"Skipped — the lead is now {lead.status}.")
                run.current_step = i + 1
                continue

            # Quiet hours hold customer messages; nothing else waits.
            if kind in Action.MESSAGING and matching.in_quiet_hours(wf, timezone.localtime(now).time()):
                run.next_run_at = matching.quiet_hours_end(wf, now)
                run.status = RunStatus.WAITING
                _log(run, i, kind, StepResult.WAITING,
                     f"Quiet hours — sending at {timezone.localtime(run.next_run_at):%d %b, %I:%M %p}.")
                run.save()
                return

            handler = HANDLERS.get(kind)
            if handler is None:
                _log(run, i, kind, StepResult.FAILED, f"Unknown step {kind!r}.")
            else:
                try:
                    result, detail = handler(run, step, lead)
                except Exception as exc:  # noqa: BLE001 — one step must not sink the run
                    logger.error("[Workflows] run %s step %s failed: %s", run.pk, i, exc, exc_info=True)
                    result, detail = StepResult.FAILED, f"Error: {exc}"
                _log(run, i, kind, result, detail)
                lead.refresh_from_db()
            run.current_step = i + 1

        _finish(run, RunStatus.COMPLETED)
