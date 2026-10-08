"""
What a call does to its lead — in one place.

Three different things used to be mixed together:

* **Call status** — was the call answered? A fact, from the phone's call log
  or the provider. A disposition used to overwrite it, so a 0-second call
  given "Connected – Interested" was stored as connected.
* **Disposition** — what happened on this call. Each one now belongs to a
  group (connected / not connected) and must match the call status.
* **Lead status** — where the lead stands in the pipeline. An outcome only
  moves it forward (a "Call back" no longer drops a lead in Negotiation to
  Follow-up), except outcomes that close it (Not interested, Lost, Invalid).

`apply_call_outcome` is called when a call is logged and when an outcome is
set on a call afterwards (click-to-call, Call back, provider calls). It is
safe to run twice: the lead's call counters are recomputed from its calls,
not incremented.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Count, Max, Q
from django.utils import timezone

from apps.core.constants import DispositionCategory, LeadStatus

logger = logging.getLogger(__name__)


class OutcomeMismatch(ValueError):
    """The outcome belongs to the other group than the call status."""


def check_outcome_matches(disposition, is_connected: bool) -> None:
    if disposition is None:
        return
    connected_outcome = disposition.category == DispositionCategory.CONNECTED
    if connected_outcome and not is_connected:
        raise OutcomeMismatch(
            f'"{disposition.name}" is an outcome for answered calls, but this call was not answered.'
        )
    if not connected_outcome and is_connected:
        raise OutcomeMismatch(
            f'"{disposition.name}" is an outcome for unanswered calls, but this call was answered.'
        )


def next_status(current: str, target: str, connected: bool) -> tuple[str | None, bool]:
    """
    The status a lead should move to after a call, or None to leave it.
    Returns (status, reopened).

    * Converted and Duplicate never change.
    * A closing outcome (Not interested, Lost, Invalid) applies at any open stage.
    * A closed lead is reopened only by an answered call whose outcome names a
      pipeline stage; the reopen is reported so it can be logged.
    * Otherwise the lead only moves forward. Any dialled call lifts it to at
      least Attempted, any answered call to at least Contacted.
    """
    rank = LeadStatus.STAGE_RANK
    if current in LeadStatus.LOCKED_STATUSES:
        return None, False

    if target in LeadStatus.CLOSED_STATUSES:
        return (target if target != current else None), False

    if current in LeadStatus.CLOSED_STATUSES:
        if connected and target in rank:
            return target, True
        return None, False

    floor = LeadStatus.CONTACTED if connected else LeadStatus.ATTEMPTED
    best = current
    for candidate in (target, floor):
        if candidate in rank and rank[candidate] > rank.get(best, -1):
            best = candidate
    # Interested and Follow-up are the same stage: an outcome may switch
    # between them ("Call back later" on an Interested lead).
    if (
        target in rank and target != current and current in rank
        and rank[target] == rank[current] and rank[target] >= rank[best]
    ):
        best = target
    return (best if best != current else None), False


def refresh_lead_call_stats(lead) -> list[str]:
    """
    Recompute the lead's call figures from its calls. Contact count and
    "last contacted" count ANSWERED calls only — they used to go up on every
    unanswered dial too.
    """
    from apps.calls.models import CallLog

    calls = CallLog.objects.filter(lead=lead)
    agg = calls.aggregate(
        dials=Count("id"),
        connected=Count("id", filter=Q(is_connected=True)),
        last_dial=Max("started_at"),
        last_connected=Max("started_at", filter=Q(is_connected=True)),
    )
    latest = calls.order_by("-started_at").only("is_connected").first()
    latest_outcome = (
        calls.filter(disposition__isnull=False).order_by("-started_at").only("disposition_id").first()
    )

    lead.dial_attempts = agg["dials"] or 0
    lead.connected_calls = agg["connected"] or 0
    lead.contact_count = lead.connected_calls
    if agg["last_dial"] and (not lead.last_dialed_at or agg["last_dial"] > lead.last_dialed_at):
        lead.last_dialed_at = agg["last_dial"]
    lead.last_connected_at = agg["last_connected"]
    if agg["last_connected"] and (not lead.last_contacted_at or agg["last_connected"] > lead.last_contacted_at):
        # Never moved backwards: a WhatsApp reply also sets this.
        lead.last_contacted_at = agg["last_connected"]
    lead.last_call_connected = latest.is_connected if latest else None
    lead.last_disposition_id = latest_outcome.disposition_id if latest_outcome else None
    return [
        "dial_attempts", "connected_calls", "contact_count", "last_dialed_at",
        "last_connected_at", "last_contacted_at", "last_call_connected", "last_disposition",
    ]


def _replace_auto_followups(lead, note: str) -> None:
    from apps.leads.followup_rules import retire_notifications
    from apps.leads.models import FollowUp

    open_auto = list(
        FollowUp.objects.filter(lead=lead, is_auto=True, is_completed=False).values_list("pk", flat=True)
    )
    if open_auto:
        FollowUp.objects.filter(pk__in=open_auto).update(
            is_completed=True, completed_at=timezone.now(), completion_notes=note,
        )
        retire_notifications(open_auto)


def apply_call_outcome(call, *, actor=None, new_dial: bool = True, followup_at=None) -> None:
    """
    Bring the call's lead up to date with this call.

    new_dial=False when an outcome is set on a call that already counted as
    a dial (click-to-call, then "Set outcome").

    followup_at: when the agent said to call back (an answered call). It is
    booked as an ordinary follow-up — answered-call outcomes never book one
    automatically.
    """
    from apps.leads.models import FollowUp, Lead, LeadActivity

    if not call.lead_id:
        return
    lead = Lead.objects.get(pk=call.lead_id)
    actor = actor or call.agent
    disposition = call.disposition if call.disposition_id else None

    fields = refresh_lead_call_stats(lead)
    old_status = lead.status

    if new_dial:
        # A dialled lead is worked: it must never be served again as fresh,
        # and the queue lock it was pulled under is released.
        lead.has_been_worked = True
        lead.locked_by = None
        lead.locked_at = None
        lead.lock_expires_at = None
        lead.locked_queue = None
        fields += ["has_been_worked", "locked_by", "locked_at", "lock_expires_at", "locked_queue"]

    target = (disposition.lead_status if disposition else "") or ""
    status, reopened = next_status(old_status, target, call.is_connected)
    if status:
        lead.status = status
        fields.append("status")
        if not lead.has_been_worked:
            lead.has_been_worked = True
            fields.append("has_been_worked")

    if disposition is not None and disposition.sets_dnd and not lead.is_dnd:
        lead.is_dnd = True
        fields.append("is_dnd")

    lead.save(update_fields=sorted(set(fields)))

    # ---- Activity: one line that says what happened -------------------
    parts = ["Call", "connected" if call.is_connected else "not connected"]
    if disposition is not None:
        parts.append(disposition.name)
    if call.is_connected and call.duration_seconds:
        parts.append(call.duration_display)
    description = " · ".join(parts)
    if status:
        description += f" → status {dict(LeadStatus.CHOICES).get(status, status)}"
        if reopened:
            description += " (reopened by this call)"
    if disposition is not None and disposition.sets_dnd:
        description += " · marked Do Not Disturb"
    if call.notes:
        description += f". {call.notes}"
    LeadActivity.objects.create(
        lead=lead,
        activity_type="call",
        description=description[:1000],
        performed_by=actor,
        meta={
            "call_id": str(call.pk), "duration": call.duration_seconds,
            "connected": call.is_connected,
            "disposition": disposition.slug if disposition else None,
            **({"old_status": old_status, "new_status": status} if status else {}),
        },
    )

    # ---- Follow-ups -------------------------------------------------------
    # Only an outcome with auto_followup_hours books a follow-up on its own —
    # by default Busy, Call back later and Voicemail; "Interested", "Ringing"
    # and the rest used to book one too, for every such lead. At most one
    # automatic follow-up is open per lead. A time the agent gives
    # (followup_at) replaces it. Once the lead has been reached, or closed, a
    # pending automatic one is retired.
    if disposition is None and followup_at is None:
        return
    assignee = lead.assigned_to_id or call.agent_id  # the lead's agent, not necessarily the caller
    closes = (status or lead.status) in LeadStatus.FINAL_STATUSES or (disposition is not None and disposition.sets_dnd)
    retry_hours = disposition.auto_followup_hours if disposition is not None else None
    label = disposition.name if disposition is not None else "call"
    if closes or call.is_connected or retry_hours or followup_at:
        _replace_auto_followups(lead, f"Replaced after call outcome: {label}")
    if not closes and retry_hours and not followup_at:
        FollowUp.objects.create(
            lead=lead, assigned_to_id=assignee, followup_type="call",
            scheduled_at=timezone.now() + timedelta(hours=retry_hours),
            notes=f"Auto-scheduled after call outcome: {label}",
            is_auto=True,
        )
    if followup_at and not closes:
        FollowUp.objects.create(
            lead=lead, assigned_to_id=assignee, followup_type="call",
            scheduled_at=followup_at,
            notes=f"Call back — {label}" + (f": {call.notes}" if call.notes else ""),
            is_auto=False,
        )
    lead.refresh_next_followup()
