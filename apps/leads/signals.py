"""
TeleCRM Backend — apps/leads/signals.py

Django signals for the Lead lifecycle.

post_save Lead      → Sync next_followup_at, broadcast to monitoring
post_save FollowUp  → Update Lead.next_followup_at
post_save Lead      → Check plan lead limit on creation
"""
import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.leads.models import FollowUp, Lead

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Lead)
def lead_pre_save(sender, instance, **kwargs):
    """
    Before saving a Lead:
    - Normalize phone number
    - Auto-set assigned_at when assigned_to changes
    """
    from apps.core.utils import normalize_indian_phone

    if instance.phone:
        normalized = normalize_indian_phone(instance.phone)
        if normalized:
            instance.phone = normalized

    if instance.alternate_phone:
        normalized = normalize_indian_phone(instance.alternate_phone)
        if normalized:
            instance.alternate_phone = normalized

    # Track assignment timestamp
    if instance.pk:
        try:
            from django.utils import timezone
            old = Lead.objects.get(pk=instance.pk)
            if old.assigned_to_id != instance.assigned_to_id and instance.assigned_to_id:
                instance.assigned_at = timezone.now()
        except Lead.DoesNotExist:
            pass


@receiver(post_save, sender=Lead)
def lead_post_save(sender, instance, created, **kwargs):
    """
    After saving a Lead:
    1. On creation: check plan limits
    2. Broadcast status change to monitoring dashboard
    """
    if created:
        _check_lead_plan_limit(instance)

    # Broadcast to monitoring dashboard (non-blocking — best effort)
    try:
        from apps.core.consumers import broadcast_to_monitors
        from django.db import connection

        broadcast_to_monitors(
            schema_name=connection.schema_name,
            event_type="lead_updated",
            data={
                "lead_id": instance.pk,
                "status": instance.status,
                "assigned_to": instance.assigned_to_id,
                "is_new": created,
            },
        )
    except Exception:
        pass


@receiver(post_save, sender=FollowUp)
def followup_post_save(sender, instance, created, **kwargs):
    """
    After saving a FollowUp:
    Update the lead's denormalized next_followup_at field.
    This avoids expensive subqueries on the lead list view.
    """
    _sync_lead_next_followup(instance.lead)


def _sync_lead_next_followup(lead: Lead):
    """Update Lead.next_followup_at to the earliest pending follow-up."""
    from django.utils import timezone

    next_fu = FollowUp.objects.filter(
        lead=lead,
        is_completed=False,
        scheduled_at__gt=timezone.now(),
    ).order_by("scheduled_at").values_list("scheduled_at", flat=True).first()

    if lead.next_followup_at != next_fu:
        Lead.objects.filter(pk=lead.pk).update(next_followup_at=next_fu)


def _check_lead_plan_limit(lead: Lead):
    """
    Check if this tenant has exceeded their plan's max_leads limit.
    Logs a warning but does NOT block creation (to avoid disrupting sales flow).
    Sends alert to admin via WebSocket if limit is exceeded.
    """
    try:
        from apps.plans.models import Subscription
        from apps.core.constants import SubscriptionStatus
        from apps.core.consumers import broadcast_to_monitors
        from django.db import connection

        sub = Subscription.objects.filter(
            status__in=SubscriptionStatus.ACTIVE_STATUSES
        ).select_related("plan").first()

        if not sub:
            return

        current_count = Lead.objects.filter(is_deleted=False).count()
        limit = sub.plan.max_leads

        if current_count >= limit:
            logger.warning(
                f"[Signal] Tenant exceeded lead limit: {current_count}/{limit}"
            )
            broadcast_to_monitors(
                schema_name=connection.schema_name,
                event_type="system_alert",
                data={
                    "alert_type": "lead_limit_reached",
                    "current": current_count,
                    "limit": limit,
                    "message": f"Lead limit reached ({current_count}/{limit}). Please upgrade your plan.",
                },
            )
    except Exception as exc:
        logger.debug(f"[Signal] Plan limit check failed: {exc}")
