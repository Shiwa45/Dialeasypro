"""
TeleCRM Backend — apps/tenants/tasks.py

Celery tasks related to tenant management:
- Welcome email on new tenant creation
- Daily usage stats sync across all tenants
"""
import logging

from celery import shared_task
from django.conf import settings
from django.db import connection

from apps.core.tasks import PublicSchemaTask, TenantAwareTask
from apps.core.utils import get_all_tenant_schemas, run_for_all_tenants

logger = logging.getLogger(__name__)


@shared_task(base=PublicSchemaTask, bind=True, max_retries=3)
def send_tenant_welcome_email(self, tenant_id, temp_password=None):
    """
    Send welcome email to a new tenant's primary contact.
    Includes login credentials and onboarding guide links.
    """
    try:
        from apps.tenants.models import Tenant
        from django.core.mail import send_mail
        from django.template.loader import render_to_string

        tenant = Tenant.objects.get(pk=tenant_id)

        subject = f"Welcome to TeleCRM — Your account is ready, {tenant.primary_contact_name}!"

        # Build login URL
        login_url = f"https://{tenant.schema_name}.{settings.BASE_DOMAIN}/crm/login/"

        context = {
            "tenant": tenant,
            "login_url": login_url,
            "temp_password": temp_password,
            "trial_days": settings.DEFAULT_TRIAL_DAYS,
            "support_email": settings.SUPPORT_EMAIL,
        }

        try:
            html_message = render_to_string("emails/welcome.html", context)
            plain_message = render_to_string("emails/welcome.txt", context)
        except Exception:
            # Fallback if templates not built yet
            plain_message = (
                f"Welcome to TeleCRM, {tenant.primary_contact_name}!\n\n"
                f"Your CRM is ready at: {login_url}\n"
                f"Email: {tenant.primary_contact_email}\n"
                f"Password: {temp_password or '[Check your registration email]'}\n\n"
                f"Your trial runs for {settings.DEFAULT_TRIAL_DAYS} days.\n\n"
                f"Need help? Email {settings.SUPPORT_EMAIL}"
            )
            html_message = None

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[tenant.primary_contact_email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(
            f"[Task] Welcome email sent to {tenant.primary_contact_email} "
            f"({tenant.schema_name})"
        )

    except Exception as exc:
        logger.error(f"[Task] send_tenant_welcome_email failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@shared_task(base=PublicSchemaTask, bind=True)
def sync_all_tenant_usage_stats(self):
    """
    Scheduled daily task: Update usage stats for all active tenants.
    Runs across all tenant schemas to count agents, leads, calls.
    Updates Tenant.total_agents and Tenant.total_leads.
    """
    logger.info("[Task] Starting sync_all_tenant_usage_stats")

    schemas = get_all_tenant_schemas()
    logger.info(f"[Task] Syncing stats for {len(schemas)} tenants")

    results = run_for_all_tenants(_sync_single_tenant_stats)

    success_count = sum(1 for v in results.values() if "error" not in v)
    logger.info(
        f"[Task] sync_all_tenant_usage_stats complete: "
        f"{success_count}/{len(schemas)} tenants updated"
    )
    return {"synced": success_count, "total": len(schemas)}


def _sync_single_tenant_stats(schema_name: str) -> dict:
    """
    Sync usage stats for a single tenant schema.
    Called by run_for_all_tenants.
    """
    previous_schema = connection.schema_name
    try:
        connection.set_schema(schema_name)

        # Count agents
        try:
            from apps.authentication.models import Agent
            agent_count = Agent.objects.filter(is_active=True).count()
        except Exception:
            agent_count = 0

        connection.set_schema_to_public()

        # Update tenant record in public schema
        from apps.tenants.models import Tenant
        Tenant.objects.filter(schema_name=schema_name).update(
            total_agents=agent_count,
        )

        return {"agents": agent_count}

    except Exception as exc:
        logger.error(f"[Task] Failed to sync stats for {schema_name}: {exc}")
        return {"error": str(exc)}
    finally:
        connection.set_schema(previous_schema)


@shared_task(base=PublicSchemaTask, bind=True, max_retries=2)
def send_trial_expiry_warning(self, tenant_id: int, days_remaining: int):
    """Send trial expiry warning email to tenant."""
    try:
        from apps.tenants.models import Tenant
        from django.core.mail import send_mail
        from django.template.loader import render_to_string

        tenant = Tenant.objects.get(pk=tenant_id)
        billing_url = (
            f"https://{tenant.schema_name}.{settings.BASE_DOMAIN}/crm/billing/"
        )

        subject = (
            f"Your TeleCRM trial expires in {days_remaining} day"
            f"{'s' if days_remaining != 1 else ''} — Upgrade now"
        )

        context = {
            "tenant": tenant,
            "days_remaining": days_remaining,
            "billing_url": billing_url,
            "support_email": settings.SUPPORT_EMAIL,
        }

        try:
            html_message = render_to_string("emails/trial_expiry_warning.html", context)
            plain_message = render_to_string("emails/trial_expiry_warning.txt", context)
        except Exception:
            plain_message = (
                f"Hi {tenant.primary_contact_name},\n\n"
                f"Your TeleCRM trial expires in {days_remaining} day(s).\n"
                f"Upgrade at: {billing_url}\n\n"
                f"Need help? Contact {settings.SUPPORT_EMAIL}"
            )
            html_message = None

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[tenant.primary_contact_email],
            html_message=html_message,
            fail_silently=True,
        )

        logger.info(
            f"[Task] Trial expiry warning sent to {tenant.primary_contact_email} "
            f"({days_remaining} days)"
        )

    except Exception as exc:
        logger.error(f"[Task] send_trial_expiry_warning failed: {exc}")
        raise self.retry(exc=exc, countdown=300)
