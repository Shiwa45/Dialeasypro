"""
TeleCRM Backend — apps/plans/signals.py

Signals that sync subscription status changes back to the Tenant model.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.plans.models import Subscription

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Subscription)
def sync_subscription_to_tenant(sender, instance, created, **kwargs):
    """
    Keep Tenant.subscription_status in sync with the active Subscription status.
    This allows quick filtering without joining to Subscription table.
    """
    try:
        tenant = instance.tenant
        if tenant.subscription_status != instance.status:
            tenant.subscription_status = instance.status
            tenant.plan = instance.plan
            tenant.save(update_fields=["subscription_status", "plan"])

            # Invalidate feature flag cache for this tenant
            from apps.core.middleware import TenantFeatureFlagMiddleware
            TenantFeatureFlagMiddleware.invalidate_cache(tenant.schema_name)

            logger.info(
                f"[Signal] Tenant {tenant.schema_name} subscription_status → {instance.status}"
            )
    except Exception as exc:
        logger.error(f"[Signal] sync_subscription_to_tenant failed: {exc}")
