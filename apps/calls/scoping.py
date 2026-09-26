"""
TeleCRM Backend — apps/calls/scoping.py

Which calls someone may see. The same shape as leads_visible_to.

Calls, reports and the AI module used the OPPOSITE default to leads:
`if role == "agent": restrict` — so every other role saw every call. HR,
Accounts and Read-only users, documented as "not a CRM admin", could play any
customer's call recording and read any AI transcript; senior agents saw the
whole floor rather than their team. Leads have always been secure by default,
and calls now are too.
"""
from django.db.models import Q

from apps.core.constants import AgentRole


def calls_visible_to(agent, qs=None):
    """
    Admins and managers: every call.
    Senior agents: their own, and their teams'.
    Team leads (AgentTeam.is_team_lead): their own, and the teams they lead.
    Everyone else — agent, HR, accounts, read-only, unknown: their own only.
    """
    from apps.calls.models import CallLog

    if qs is None:
        qs = CallLog.objects.all()

    role = getattr(agent, "role", None)
    if role in (AgentRole.ADMIN, AgentRole.MANAGER):
        return qs
    if role == AgentRole.SENIOR_AGENT:
        return qs.filter(
            Q(agent=agent) | Q(agent__team_memberships__team__memberships__agent=agent)
        ).distinct()

    led_team_ids = list(
        agent.team_memberships.filter(is_team_lead=True).values_list("team_id", flat=True)
    ) if hasattr(agent, "team_memberships") else []
    if led_team_ids:
        return qs.filter(
            Q(agent=agent) | Q(agent__team_memberships__team_id__in=led_team_ids)
        ).distinct()

    return qs.filter(agent=agent)


def sees_everything(agent) -> bool:
    """Whether reports for this person should be tenant-wide."""
    return getattr(agent, "role", None) in (AgentRole.ADMIN, AgentRole.MANAGER)
