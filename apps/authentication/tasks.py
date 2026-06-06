"""
TeleCRM Backend — apps/authentication/tasks.py

Celery tasks for agent-related operations.

send_agent_welcome_email    : Welcome email when a new agent is created
send_followup_reminders     : Daily follow-up reminders per tenant
send_daily_performance_summary : Daily performance stats to managers
cleanup_expired_sessions    : Housekeeping — invalidate stale sessions
"""
import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.tasks import PublicSchemaTask, TenantAwareTask

logger = logging.getLogger(__name__)


@shared_task(base=TenantAwareTask, bind=True, max_retries=3)
def send_agent_welcome_email(self, schema_name: str, agent_id: int):
    """
    Send a welcome email to a newly created agent.
    Includes their login URL and temporary credential instructions.
    """
    try:
        from apps.authentication.models import Agent
        from django.core.mail import send_mail

        # schema_name already set by TenantAwareTask.__call__
        try:
            agent = Agent.objects.get(pk=agent_id)
        except Agent.DoesNotExist:
            logger.warning(f"[Task] Agent {agent_id} not found in {schema_name}")
            return

        login_url = f"https://{schema_name}.{settings.BASE_DOMAIN}/crm/login/"

        send_mail(
            subject="Welcome to TeleCRM — Your account is ready",
            message=(
                f"Hi {agent.name},\n\n"
                f"Your TeleCRM agent account has been created.\n\n"
                f"Login URL: {login_url}\n"
                f"Email: {agent.email}\n"
                f"Password: You'll receive your temporary password separately.\n\n"
                f"Please change your password on first login.\n\n"
                f"Need help? Contact your team admin."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[agent.email],
            fail_silently=True,
        )

        logger.info(
            f"[Task] Welcome email sent to agent {agent.email} ({schema_name})"
        )

    except Exception as exc:
        logger.error(f"[Task] send_agent_welcome_email failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@shared_task(base=TenantAwareTask, bind=True)
def send_followup_reminders(self, schema_name: str):
    """
    Send follow-up reminders to agents for leads due today.
    Runs daily per tenant at 8:30 AM IST (configured in celery beat schedule).

    Queries the leads app for pending follow-ups and notifies:
    1. Push notification via FCM (Firebase)
    2. WebSocket notification if agent is online
    """
    logger.info(f"[Task] Sending follow-up reminders for {schema_name}")

    try:
        # This will be populated in Phase 2 when the leads app is built
        # Placeholder implementation
        from apps.authentication.models import Agent

        active_agents = Agent.objects.filter(is_active=True).count()
        logger.info(
            f"[Task] Follow-up reminder task ran for {schema_name} — "
            f"{active_agents} active agents"
        )

    except Exception as exc:
        logger.error(f"[Task] send_followup_reminders failed for {schema_name}: {exc}")


@shared_task(base=TenantAwareTask, bind=True)
def send_daily_performance_summary(self, schema_name: str):
    """
    Send daily performance summary email to managers/admins.
    Includes: calls made, leads created, conversions, vs. previous day.
    Runs daily at 7 PM IST.
    """
    logger.info(f"[Task] Sending daily performance summary for {schema_name}")

    try:
        from apps.authentication.models import Agent
        from apps.core.constants import AgentRole

        managers = Agent.objects.filter(
            role__in=[AgentRole.ADMIN, AgentRole.MANAGER],
            is_active=True,
        )

        if not managers.exists():
            return

        # Placeholder — Phase 2 will inject actual stats from leads/calls
        today = timezone.now().date()
        for manager in managers:
            logger.debug(
                f"[Task] Would send summary to {manager.email} for {today}"
            )

    except Exception as exc:
        logger.error(
            f"[Task] send_daily_performance_summary failed for {schema_name}: {exc}"
        )


@shared_task(base=PublicSchemaTask, bind=True)
def cleanup_expired_sessions(self):
    """
    Housekeeping task: mark stale login sessions as inactive.
    Sessions older than 30 days with no activity are cleaned up.
    Runs weekly.
    """
    from datetime import timedelta
    from apps.core.utils import get_all_tenant_schemas, run_for_all_tenants
    from django.db import connection

    logger.info("[Task] Cleaning up expired login sessions")

    def cleanup_schema(schema_name: str):
        previous = connection.schema_name
        try:
            connection.set_schema(schema_name)
            from apps.authentication.models import AgentLoginSession

            cutoff = timezone.now() - timedelta(days=30)
            count = AgentLoginSession.objects.filter(
                is_active=True,
                login_time__lt=cutoff,
            ).update(is_active=False, logout_time=timezone.now())

            if count:
                logger.info(
                    f"[Task] Cleaned {count} stale sessions in {schema_name}"
                )
            return {"cleaned": count}
        except Exception as exc:
            return {"error": str(exc)}
        finally:
            connection.set_schema(previous)

    schemas = get_all_tenant_schemas()
    results = run_for_all_tenants(cleanup_schema)

    total_cleaned = sum(
        v.get("cleaned", 0) for v in results.values() if isinstance(v, dict)
    )
    logger.info(f"[Task] Session cleanup complete: {total_cleaned} sessions closed")
    return {"total_cleaned": total_cleaned}


@shared_task(base=PublicSchemaTask, bind=True)
def dispatch_followup_reminders(self):
    """
    Beat-scheduled dispatcher: queues follow-up reminders for every active tenant.
    Also triggers lead-specific follow-up reminders via leads app task.
    """
    from apps.core.utils import get_all_tenant_schemas
    schemas = get_all_tenant_schemas()
    logger.info(f"[Task] Dispatching follow-up reminders to {len(schemas)} tenants")
    for schema_name in schemas:
        send_followup_reminders.apply_async(
            args=[schema_name], queue="notifications"
        )
        # Also trigger leads-app follow-up reminder task
        try:
            from apps.leads.tasks import send_followup_reminders_for_tenant
            send_followup_reminders_for_tenant.apply_async(
                args=[schema_name], queue="notifications"
            )
        except ImportError:
            pass
    return {"dispatched": len(schemas)}


@shared_task(base=PublicSchemaTask, bind=True)
def dispatch_performance_summaries(self):
    """
    Beat-scheduled dispatcher: triggers daily performance summary for every tenant.
    """
    from apps.core.utils import get_all_tenant_schemas
    schemas = get_all_tenant_schemas()
    logger.info(f"[Task] Dispatching performance summaries to {len(schemas)} tenants")
    for schema_name in schemas:
        send_daily_performance_summary.apply_async(
            args=[schema_name], queue="notifications"
        )
    return {"dispatched": len(schemas)}


@shared_task(base=PublicSchemaTask, bind=True)
def cleanup_expired_jwt_blacklist(self):
    """
    Remove expired tokens from the JWT blacklist table.
    simplejwt's OutstandingToken/BlacklistedToken accumulate — prune weekly.
    """
    try:
        from django.utils import timezone
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

        deleted_count, _ = OutstandingToken.objects.filter(
            expires_at__lt=timezone.now()
        ).delete()
        logger.info(f"[Task] JWT blacklist cleanup: removed {deleted_count} expired tokens")
        return {"deleted": deleted_count}
    except Exception as exc:
        logger.error(f"[Task] cleanup_expired_jwt_blacklist failed: {exc}")
        return {"error": str(exc)}
