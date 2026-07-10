"""
TeleCRM Backend — apps/core/quotas.py

Plan capacity enforcement for resources created outside a request context
(webhooks, Celery tasks, management commands) as well as inside one.

Feature *flags* answer "may this tenant use X at all?" (see permissions.py).
Quotas answer "has this tenant used up their allowance of X?" — Plan.max_leads,
max_leads_per_day, storage_gb, etc.

Counts are cached briefly. A quota is a soft ceiling: admitting a handful of
extra rows under concurrency is fine, refusing a paying tenant is not.
"""
import logging
from datetime import date

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from apps.core.constants import CacheTimeout, SubscriptionStatus
from apps.core.exceptions import PlanLimitExceededException

logger = logging.getLogger(__name__)

# Counts are re-read at most this often. Short enough to stop runaway ingestion,
# long enough that a webhook burst doesn't COUNT(*) the leads table per lead.
COUNT_TTL = 60


def current_plan():
    """
    The active Plan for the tenant of the CURRENT database schema, or None.

    Reuses the same `tenant_plan_id:{schema}` cache key as
    TenantFeatureFlagMiddleware, so `invalidate_cache()` clears both.
    """
    schema = connection.schema_name
    if not schema or schema == "public":
        return None

    cache_key = f"tenant_plan_id:{schema}"
    plan_id = cache.get(cache_key)

    if plan_id is None:
        from apps.plans.models import Subscription
        from apps.tenants.models import Tenant

        try:
            tenant = Tenant.objects.get(schema_name=schema)
        except Tenant.DoesNotExist:
            return None

        subscription = (
            Subscription.objects.filter(
                tenant=tenant, status__in=SubscriptionStatus.ACTIVE_STATUSES
            )
            .select_related("plan")
            .first()
        )
        plan = subscription.plan if subscription else None
        cache.set(cache_key, plan.pk if plan else 0, timeout=CacheTimeout.FEATURE_FLAGS)
        return plan

    if not plan_id:
        return None

    from apps.plans.models import Plan
    return Plan.objects.filter(pk=plan_id).first()


def _lead_counts() -> tuple[int, int]:
    """(total non-deleted leads, leads created today) — cached for COUNT_TTL."""
    schema = connection.schema_name
    today = timezone.localdate()

    total_key = f"quota:leads_total:{schema}"
    today_key = f"quota:leads_today:{schema}:{today.isoformat()}"

    total = cache.get(total_key)
    today_count = cache.get(today_key)

    if total is None or today_count is None:
        from apps.leads.models import Lead

        if total is None:
            total = Lead.objects.filter(is_deleted=False).count()
            cache.set(total_key, total, timeout=COUNT_TTL)
        if today_count is None:
            today_count = Lead.objects.filter(created_at__date=today).count()
            cache.set(today_key, today_count, timeout=COUNT_TTL)

    return int(total), int(today_count)


def lead_quota_error(count: int = 1) -> PlanLimitExceededException | None:
    """
    Return the exception to raise if creating `count` more leads would breach
    the plan, else None. Callers that must not blow up (webhooks) inspect this
    instead of catching.

    Tenants with no resolvable plan are not throttled — refusing their leads
    would be worse than admitting them.
    """
    plan = current_plan()
    if plan is None:
        return None

    total, today = _lead_counts()

    if plan.max_leads and total + count > plan.max_leads:
        return PlanLimitExceededException(
            limit_type="total leads", current=total, max_allowed=plan.max_leads
        )
    if plan.max_leads_per_day and today + count > plan.max_leads_per_day:
        return PlanLimitExceededException(
            limit_type="leads per day", current=today, max_allowed=plan.max_leads_per_day
        )
    return None


def enforce_lead_quota(count: int = 1):
    """Raise PlanLimitExceededException (402) if the lead caps would be breached."""
    if exc := lead_quota_error(count):
        raise exc


def note_leads_created(n: int = 1):
    """
    Nudge the cached counters after creating leads, so a burst inside one TTL
    window still converges on the cap instead of sailing past it.
    """
    schema = connection.schema_name
    today = timezone.localdate()
    for key in (f"quota:leads_total:{schema}", f"quota:leads_today:{schema}:{today.isoformat()}"):
        try:
            if cache.get(key) is not None:
                cache.incr(key, n)
        except ValueError:
            # Key expired between the get and the incr — next read recomputes.
            pass


def remaining_lead_allowance() -> int | None:
    """
    How many more leads may be created right now (None = unlimited/no plan).
    Used by bulk paths (CSV import) to truncate rather than fail row-by-row.
    """
    plan = current_plan()
    if plan is None:
        return None

    total, today = _lead_counts()
    limits = []
    if plan.max_leads:
        limits.append(plan.max_leads - total)
    if plan.max_leads_per_day:
        limits.append(plan.max_leads_per_day - today)
    if not limits:
        return None
    return max(0, min(limits))
