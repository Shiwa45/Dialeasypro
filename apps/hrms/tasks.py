"""
TeleCRM Backend — apps/hrms/tasks.py

Nightly HRMS jobs. Both are no-ops for tenants without the HRMS module, so the
beat schedule can run them unconditionally.
"""
import logging

from celery import shared_task
from django.db import connection
from django.utils import timezone

from apps.core.tasks import PublicSchemaTask

logger = logging.getLogger(__name__)


def _tenant_has_hrms(schema_name: str) -> bool:
    """Skip tenants who haven't bought the module."""
    from apps.core.constants import FeatureKey
    from apps.core.middleware import TenantFeatureFlagMiddleware
    from apps.tenants.models import Tenant

    try:
        tenant = Tenant.objects.get(schema_name=schema_name)
    except Tenant.DoesNotExist:
        return False
    mw = TenantFeatureFlagMiddleware(lambda r: None)
    return bool(mw._get_tenant_features(tenant).get(FeatureKey.HRMS_ATTENDANCE, False))


@shared_task(base=PublicSchemaTask, bind=True)
def sync_attendance_all_tenants(self, day=None):
    """
    Recompute yesterday's attendance from dialer session logs, for every tenant
    on the HRMS module. Runs after midnight so the day's status intervals are
    all closed.
    """
    from apps.core.utils import run_for_all_tenants

    results = run_for_all_tenants(_sync_one_tenant, day)
    total = sum(v for v in results.values() if isinstance(v, int))
    logger.info(f"[HRMS] attendance sync wrote {total} row(s)")
    return {"rows": total}


def _sync_one_tenant(schema_name: str, day=None) -> int:
    from datetime import timedelta

    from apps.hrms.services.attendance import sync_attendance_for_date

    if not _tenant_has_hrms(schema_name):
        return 0

    prev = connection.schema_name
    try:
        connection.set_schema(schema_name)
        target = day or (timezone.localdate() - timedelta(days=1))
        return sync_attendance_for_date(target)
    finally:
        connection.set_schema(prev)


@shared_task(base=PublicSchemaTask, bind=True)
def recompute_incentives_all_tenants(self, month=None):
    """
    Refresh the current month's incentive earnings so agents see live progress
    against their targets. Earnings already rolled into a payslip are frozen.
    """
    from apps.core.utils import run_for_all_tenants

    results = run_for_all_tenants(_incentives_one_tenant, month)
    return {"tenants": len([v for v in results.values() if v])}


def _incentives_one_tenant(schema_name: str, month=None):
    from apps.hrms.services.incentives import compute_all_earnings

    if not _tenant_has_hrms(schema_name):
        return None

    prev = connection.schema_name
    try:
        connection.set_schema(schema_name)
        return compute_all_earnings(month or timezone.localdate())
    except Exception as exc:
        logger.error(f"[HRMS] incentive recompute failed for {schema_name}: {exc}")
        return None
    finally:
        connection.set_schema(prev)
