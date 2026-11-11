"""
TeleCRM Backend — apps/calls/figures.py

An agent's call figures — calls, connected, talk time — defined once.

The Calls page, Live Agents and the Login report each counted these their own
way: talk time was the connected calls' durations on one screen and the time
spent in the dialer's "on call" status (dialling and ringing included) on the
others, so the same agent showed three different numbers. Every screen now
takes them from here, from the call records.
"""
from django.db.models import Count, Q, Sum

FIELDS = ("calls", "connected", "talk_seconds")


def call_figures(qs) -> dict:
    """Calls, connected calls and talk time (connected calls only — providers
    report ring time as the duration of unanswered calls too)."""
    row = qs.aggregate(
        calls=Count("id"),
        connected=Count("id", filter=Q(is_connected=True)),
        talk_seconds=Sum("duration_seconds", filter=Q(is_connected=True)),
    )
    return {k: row[k] or 0 for k in FIELDS}


def call_figures_by_agent_day(qs) -> dict:
    """{(agent_id, local date): figures}. started_at__date is evaluated in the
    current (tenant-local) time zone, the same day every screen uses."""
    out = {}
    for row in (
        qs.values("agent_id", "started_at__date")
        .annotate(
            calls=Count("id"),
            connected=Count("id", filter=Q(is_connected=True)),
            talk_seconds=Sum("duration_seconds", filter=Q(is_connected=True)),
        )
    ):
        out[(row["agent_id"], row["started_at__date"])] = {k: row[k] or 0 for k in FIELDS}
    return out
