"""
TeleCRM Backend — apps/leads/followup_rules.py

Whose follow-up is it, and who is told about it.

One rule, applied everywhere a follow-up is created, moved or announced:

    An open follow-up on an assigned lead belongs to the lead's agent.

Before this, ownership was decided differently in each place and drifted:

  * A follow-up belonged to whoever CREATED it. A team lead or manager
    scheduling one on an agent's lead got the reminders themselves; the agent
    who actually had to make the call was never told.
  * The auto follow-up booked by a call outcome went to whoever made the call.
  * Reassigning a lead (bulk assign, distribution, editing the lead) left its
    open follow-ups with the previous agent, who kept getting reminders for a
    lead they could no longer open, while the new agent got none.
  * Reminders went out for deleted leads and to deactivated agents.

`deliverable()` is the safety net under all of it: reminders, the overdue
chase and the phone's reminder list only ever cover follow-ups whose
recipient still owns the lead. Even if some future code path reassigns a lead
without calling `follow_lead_owner()`, the previous agent stops being told.
"""
from django.db.models import F, OuterRef, Q, Subquery
from django.utils import timezone
from rest_framework import serializers

from apps.core.constants import AgentRole

# Roles that see every lead, so may own a follow-up on an unassigned one.
_SEES_ALL = (AgentRole.ADMIN, AgentRole.MANAGER)


def owner_for(lead, *, actor, requested=None):
    """
    Who a new follow-up on `lead` belongs to.

    - The lead's agent, if it has one. Asking for anyone else is refused
      rather than silently overridden: the follow-up would never ring for
      them, and "reassign the lead" is the honest answer.
    - On an unassigned lead: `requested` if given (managers and admins only,
      active agents only), otherwise the person scheduling it.
    """
    owner_id = lead.assigned_to_id
    requested_id = getattr(requested, "pk", requested)

    if owner_id:
        if requested_id and requested_id != owner_id:
            raise serializers.ValidationError({
                "assigned_to": "Follow-ups go to the lead's agent. Reassign the lead to change who follows up.",
            })
        return lead.assigned_to

    if requested_id and requested_id != actor.pk:
        if getattr(actor, "role", None) not in _SEES_ALL:
            raise serializers.ValidationError({
                "assigned_to": "Only a manager or admin can schedule a follow-up for someone else.",
            })
        if not getattr(requested, "is_active", False):
            raise serializers.ValidationError({"assigned_to": "That agent is not active."})
        return requested
    return actor


def deliverable(followups):
    """
    Narrow a FollowUp queryset to those whose assignee should be told.

    Live lead, active assignee, and the assignee owns the lead — or, on an
    unassigned lead, is a manager/admin who can still open it.
    """
    return followups.filter(
        lead__is_deleted=False,
        assigned_to__is_active=True,
    ).filter(
        Q(lead__assigned_to=F("assigned_to"))
        | Q(lead__assigned_to__isnull=True, assigned_to__role__in=_SEES_ALL)
    )


def follow_lead_owner(lead_ids) -> int:
    """
    Move the open follow-ups of these leads to each lead's current agent.

    Call after any change of a lead's agent. Moved follow-ups get their
    reminder re-armed for the new agent, and the previous agent's unread
    notifications about them are marked read (they point at a lead that
    person can no longer open). Returns how many follow-ups moved.
    """
    from apps.authentication.models import Notification
    from apps.leads.models import FollowUp, Lead

    ids = list(lead_ids)
    if not ids:
        return 0

    stale = (
        FollowUp.objects.filter(lead_id__in=ids, is_completed=False, lead__assigned_to__isnull=False)
        .exclude(assigned_to=F("lead__assigned_to"))
    )
    moved_ids = list(stale.values_list("pk", flat=True))
    if not moved_ids:
        return 0

    owner = Lead.objects.filter(pk=OuterRef("lead_id")).values("assigned_to")[:1]
    FollowUp.objects.filter(pk__in=moved_ids).update(
        assigned_to=Subquery(owner),
        reminder_sent=False,
        reminder_sent_at=None,
    )

    now = timezone.now()
    Notification.objects.filter(followup_id_ref__in=moved_ids, is_read=False).update(
        is_read=True, read_at=now,
    )
    return len(moved_ids)


def retire_notifications(followup_ids) -> None:
    """A finished follow-up has nothing left to tell anyone: clear its unread
    reminders from every bell, so "Overdue: …" does not linger after it is done."""
    from apps.authentication.models import Notification

    Notification.objects.filter(followup_id_ref__in=list(followup_ids), is_read=False).update(
        is_read=True, read_at=timezone.now(),
    )
