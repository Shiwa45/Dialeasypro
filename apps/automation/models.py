"""
TeleCRM Backend — apps/automation/models.py

Workflow     : a trigger, optional conditions and an ordered list of steps.
WorkflowRun  : one workflow running for one lead — its step pointer, its wait
               timer and the log of what each step did.

Steps, conditions and trigger options are JSON validated by
apps.automation.validation, so a new action needs no migration.
"""
from django.db import models

from apps.automation.constants import RunStatus, Trigger
from apps.core.models import TimeStampedModel


class Workflow(TimeStampedModel):
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True, default="")
    is_active = models.BooleanField(default=False, db_index=True)

    trigger = models.CharField(max_length=40, choices=Trigger.CHOICES, db_index=True)
    # Per-trigger options, e.g. {"to": ["interested"]} for a status change,
    # {"keywords": ["price"]} for a WhatsApp message, {"days": 3} for inactivity.
    trigger_config = models.JSONField(default=dict, blank=True)
    # {"sources": [...], "statuses": [...], "batches": [ids], "assigned_to": [ids, 0 = unassigned],
    #  "cities": [...], "tags": [...]} — every list given must match.
    conditions = models.JSONField(default=dict, blank=True)
    # [{"type": "send_whatsapp", "template": 4}, {"type": "wait", "amount": 2, "unit": "days"}, ...]
    steps = models.JSONField(default=list, blank=True)

    # False (default): a lead goes through this workflow once, ever.
    # True: every matching event starts a run (each event still only once).
    repeat = models.BooleanField(default=False)

    # Messages to customers are held during quiet hours (local time).
    quiet_hours_enabled = models.BooleanField(default=True)
    quiet_start = models.TimeField(default="21:00")
    quiet_end = models.TimeField(default="09:00")

    # Engine bookkeeping, e.g. the round-robin pointer per step.
    state = models.JSONField(default=dict, blank=True)

    runs_count = models.PositiveIntegerField(default=0)
    last_run_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="workflows_created",
    )

    class Meta:
        ordering = ["-is_active", "name"]

    def __str__(self):
        return f"{self.name} ({'on' if self.is_active else 'off'})"


class WorkflowRun(TimeStampedModel):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="runs")
    lead = models.ForeignKey("leads.Lead", on_delete=models.CASCADE, related_name="workflow_runs")

    # What started it. Unique per workflow: the same event never starts the
    # same workflow twice (a retried webhook, a re-saved call), and a
    # once-per-lead workflow uses "lead:<id>" so a lead goes through it once.
    event_key = models.CharField(max_length=150)
    trigger = models.CharField(max_length=40, blank=True, default="")
    context = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=12, choices=RunStatus.CHOICES, default=RunStatus.PENDING,
                              db_index=True)
    current_step = models.PositiveSmallIntegerField(default=0)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    # [{"step": 0, "type": "send_whatsapp", "result": "done", "detail": "...", "at": iso}, ...]
    log = models.JSONField(default=list, blank=True)
    has_errors = models.BooleanField(default=False)
    error = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["workflow", "event_key"], name="one_run_per_workflow_event"),
        ]
        indexes = [models.Index(fields=["status", "next_run_at"])]

    def __str__(self):
        return f"{self.workflow.name} → lead {self.lead_id} [{self.status}]"
