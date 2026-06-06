"""
TeleCRM Backend — apps/plans/tasks.py

Celery tasks for plan and billing management.
"""
import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.tasks import PublicSchemaTask

logger = logging.getLogger(__name__)


@shared_task(base=PublicSchemaTask, bind=True)
def check_trial_expirations(self):
    """
    Daily task: Check all tenants in trial and:
    1. Send warning emails (7 days, 3 days, 1 day before expiry)
    2. Suspend tenants whose trial has expired

    Runs every day at 9 AM IST (configured in config/celery.py beat_schedule)
    """
    from apps.core.constants import SubscriptionStatus
    from apps.tenants.models import Tenant
    from apps.tenants.tasks import send_trial_expiry_warning

    now = timezone.now()
    logger.info(f"[Task] Checking trial expirations at {now}")

    # Get all trial tenants
    trial_tenants = Tenant.objects.filter(
        subscription_status=SubscriptionStatus.TRIAL,
        is_active=True,
        trial_ends_at__isnull=False,
    ).exclude(schema_name="public")

    suspended_count = 0
    warned_count = 0

    for tenant in trial_tenants:
        days_remaining = tenant.trial_days_remaining

        if days_remaining <= 0:
            # Trial expired — suspend
            tenant.suspend(reason="Trial period expired")
            suspended_count += 1
            logger.info(f"[Task] Suspended expired trial: {tenant.schema_name}")

            # Send expiry notification
            _send_trial_expired_email.apply_async(
                kwargs={"tenant_id": tenant.pk},
                queue="notifications",
            )

        elif days_remaining in [7, 3, 1]:
            # Send warning at 7 days, 3 days, 1 day
            send_trial_expiry_warning.apply_async(
                kwargs={
                    "tenant_id": tenant.pk,
                    "days_remaining": days_remaining,
                },
                queue="notifications",
            )
            warned_count += 1

    logger.info(
        f"[Task] Trial check complete: {suspended_count} suspended, {warned_count} warned"
    )
    return {"suspended": suspended_count, "warned": warned_count}


@shared_task(base=PublicSchemaTask, bind=True, max_retries=2)
def _send_trial_expired_email(self, tenant_id: int):
    """Send trial expired email to tenant."""
    try:
        from apps.tenants.models import Tenant
        from django.core.mail import send_mail

        tenant = Tenant.objects.get(pk=tenant_id)
        upgrade_url = (
            f"https://{tenant.schema_name}.{settings.BASE_DOMAIN}/crm/billing/"
        )

        send_mail(
            subject="Your TeleCRM trial has expired — Reactivate now",
            message=(
                f"Hi {tenant.primary_contact_name},\n\n"
                f"Your TeleCRM trial has expired and your account has been suspended.\n\n"
                f"To continue using TeleCRM, please upgrade your plan:\n{upgrade_url}\n\n"
                f"Need help? Contact us at {settings.SUPPORT_EMAIL}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[tenant.primary_contact_email],
            fail_silently=True,
        )
    except Exception as exc:
        logger.error(f"[Task] _send_trial_expired_email failed: {exc}")
        raise self.retry(exc=exc, countdown=300)
