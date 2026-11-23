"""
TeleCRM Backend — apps/automation/tasks.py

run_workflow    — run one workflow run's next steps (queued by the engine).
workflows_tick  — every minute, for every tenant: resume runs whose wait is
                  over, and pick up runs whose first hand-off was lost.
workflows_scan  — every 15 minutes, for every tenant: missed follow-ups and
                  inactive leads.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.db import connection
from django.utils import timezone

from apps.core.tasks import PublicSchemaTask, TenantAwareTask

logger = logging.getLogger(__name__)


@shared_task(base=TenantAwareTask, bind=True, max_retries=2, default_retry_delay=60)
def run_workflow(self, schema_name: str, run_id: int):
    from apps.automation.services.engine import advance

    advance(run_id)


def _tick_one(schema_name: str) -> int:
    from apps.automation.constants import RunStatus
    from apps.automation.models import WorkflowRun
    prev = connection.schema_name
    try:
        connection.set_schema(schema_name)
        now = timezone.now()
        due = list(
            WorkflowRun.objects.filter(status=RunStatus.WAITING, next_run_at__lte=now)
            .values_list("pk", flat=True)[:500]
        ) + list(
            WorkflowRun.objects.filter(status=RunStatus.PENDING, created_at__lte=now - timedelta(minutes=5))
            .values_list("pk", flat=True)[:200]
        )
        for pk in due:
            run_workflow.apply_async(args=[schema_name, pk], queue="default")
        return len(due)
    finally:
        connection.set_schema(prev)


def _scan_one(schema_name: str) -> int:
    from apps.automation.services.scans import run_scans

    prev = connection.schema_name
    try:
        connection.set_schema(schema_name)
        return run_scans()
    finally:
        connection.set_schema(prev)


@shared_task(base=PublicSchemaTask, bind=True)
def workflows_tick(self):
    from apps.core.utils import run_for_all_tenants

    results = run_for_all_tenants(_tick_one)
    return sum(v for v in results.values() if isinstance(v, int))


@shared_task(base=PublicSchemaTask, bind=True)
def workflows_scan(self):
    from apps.core.utils import run_for_all_tenants

    results = run_for_all_tenants(_scan_one)
    return sum(v for v in results.values() if isinstance(v, int))
