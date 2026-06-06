"""
TeleCRM Backend — apps/authentication/signals.py

Django signals for Agent lifecycle events.

post_save (Agent, created=True) → Send welcome email to new agents
                                 → Broadcast new agent to monitoring dashboard
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.authentication.models import Agent

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Agent)
def agent_post_save(sender, instance, created, **kwargs):
    """
    Fires whenever an Agent is saved.
    On creation: sends welcome email, broadcasts to monitoring dashboard.
    """
    if not created:
        return

    # Skip the initial tenant admin creation (handled by tenant signal instead)
    if instance.is_tenant_admin and instance.must_change_password:
        # The tenant welcome email already includes credentials — don't double-send
        return

    logger.info(f"[Signal] New agent created: {instance.email}")

    # Send welcome email to the new agent
    try:
        from apps.authentication.tasks import send_agent_welcome_email
        from django.db import connection

        send_agent_welcome_email.apply_async(
            kwargs={
                "schema_name": connection.schema_name,
                "agent_id": instance.pk,
            },
            countdown=3,
            queue="notifications",
        )
    except Exception as exc:
        logger.warning(f"[Signal] Could not queue agent welcome email: {exc}")

    # Broadcast new agent to the monitoring dashboard via WebSocket
    try:
        from apps.core.consumers import broadcast_to_monitors
        from django.db import connection

        broadcast_to_monitors(
            schema_name=connection.schema_name,
            event_type="agent_created",
            data={
                "agent_id": instance.pk,
                "name": instance.name,
                "email": instance.email,
                "role": instance.role,
            },
        )
    except Exception as exc:
        logger.debug(f"[Signal] WebSocket broadcast failed: {exc}")
