"""
TeleCRM Backend — apps/calls/signals.py

Signals for call lifecycle:
- After a CallLog is created, log activity on the lead
- After a CallLog is saved with disposition, auto-schedule follow-up
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.calls.models import CallLog

logger = logging.getLogger(__name__)


@receiver(post_save, sender=CallLog)
def calllog_post_save(sender, instance, created, **kwargs):
    """Auto-schedule follow-up when disposition has auto_followup_hours set."""
    if not created or not instance.disposition:
        return
    if not instance.disposition.auto_followup_hours or not instance.lead:
        return
    try:
        from datetime import timedelta
        from django.utils import timezone
        from apps.leads.models import FollowUp
        scheduled = timezone.now() + timedelta(hours=instance.disposition.auto_followup_hours)
        FollowUp.objects.create(
            lead=instance.lead,
            assigned_to=instance.agent,
            followup_type="call",
            scheduled_at=scheduled,
            notes=f"Auto-scheduled after call disposition: {instance.disposition.name}",
        )
        logger.debug(f"[Signal] Auto follow-up created for lead {instance.lead_id}")
    except Exception as exc:
        logger.warning(f"[Signal] Auto follow-up failed: {exc}")
