"""
TeleCRM Backend — apps/calls/signals.py

A new call brings its lead up to date — status, call counters, activity and
the automatic follow-up — through apps/calls/services/outcomes.py, whatever
created the call (the app, the web, a provider, a script).

Before, part of this lived here and part in the call view, and the outcome
rules ran only on creation, so an outcome set on a call afterwards changed
nothing. The outcome endpoint now calls the same service.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.calls.models import CallLog

logger = logging.getLogger(__name__)


@receiver(post_save, sender=CallLog)
def calllog_post_save(sender, instance, created, **kwargs):
    if not created or not instance.lead_id:
        return
    # Click-to-call saves the call before dialling and applies it only once
    # the dial went out (a failed dial deletes the call again).
    if getattr(instance, "_defer_outcome", False):
        return
    from apps.calls.services.outcomes import apply_call_outcome

    try:
        apply_call_outcome(instance, actor=getattr(instance, "_actor", None))
    except Exception as exc:  # noqa: BLE001 — never lose the call itself
        logger.warning(f"[Signal] Could not apply call {instance.pk} to its lead: {exc}", exc_info=True)
