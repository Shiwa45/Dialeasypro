"""
TeleCRM Backend — apps/authentication/presence.py

Live agent presence + time-accounting logic, shared by the status API, the
heartbeat endpoint, and the Celery stale-sweep task.

A transition closes the currently-open AgentStatusLog interval (recording its
duration) and opens a new one, updates the agent's AgentStatus row, and
broadcasts the change to all admin monitoring dashboards over Channels.

Presence is tied to an auto-dial session: the first online status opens a
session; going offline closes it.
"""
import logging
from datetime import timedelta

from django.db import connection
from django.utils import timezone

from apps.authentication.models import AgentStatus, AgentStatusLog
from apps.core.constants import AgentWorkStatus

logger = logging.getLogger(__name__)

# Heartbeat older than this ⇒ the session is considered dead ⇒ flip to offline.
STALE_SECONDS = 60


def set_agent_status(
    agent,
    status,
    *,
    break_reason="",
    call_id=None,
    lead_id=None,
    broadcast=True,
):
    """
    Apply a status transition for an agent. Idempotent for the same status
    (treated as a heartbeat). Returns the AgentStatus row.
    """
    if status not in AgentWorkStatus.REPORTABLE:
        raise ValueError(f"Invalid status: {status}")

    now = timezone.now()
    st, _ = AgentStatus.objects.get_or_create(
        agent=agent,
        defaults={"status": AgentWorkStatus.OFFLINE, "since": now, "last_seen": now},
    )

    changed = st.status != status
    st.last_seen = now

    if changed:
        # Close any open interval(s) for this agent.
        for log in AgentStatusLog.objects.filter(agent=agent, ended_at__isnull=True):
            log.close(now)

        # Open a new interval for online statuses (we don't log offline time).
        if status in AgentWorkStatus.ONLINE_STATUSES:
            AgentStatusLog.objects.create(
                agent=agent,
                status=status,
                started_at=now,
                break_reason=break_reason if status == AgentWorkStatus.BREAK else "",
            )

        st.status = status
        st.since = now

    # Session bookkeeping.
    if status == AgentWorkStatus.OFFLINE:
        st.session_started_at = None
        st.current_call_id = None
        st.current_lead_id = None
    else:
        if st.session_started_at is None:
            st.session_started_at = now
        st.current_call_id = call_id
        st.current_lead_id = lead_id

    st.break_reason = break_reason if status == AgentWorkStatus.BREAK else ""
    st.save()

    if broadcast and changed:
        _broadcast(st, now)

    return st


def touch_heartbeat(agent):
    """Refresh last_seen so the session isn't swept to offline. No broadcast."""
    AgentStatus.objects.filter(agent=agent).update(last_seen=timezone.now())


def compute_today_totals(agent, now=None) -> dict:
    """Seconds spent in each online status since local midnight (incl. open interval)."""
    now = now or timezone.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    totals = {
        AgentWorkStatus.AVAILABLE: 0,
        AgentWorkStatus.ON_CALL: 0,
        AgentWorkStatus.WRAP_UP: 0,
        AgentWorkStatus.BREAK: 0,
    }
    logs = AgentStatusLog.objects.filter(agent=agent, started_at__gte=start)
    for log in logs:
        end = log.ended_at or now
        begin = max(log.started_at, start)
        dur = max(0, int((end - begin).total_seconds()))
        totals[log.status] = totals.get(log.status, 0) + dur
    totals["online"] = sum(totals.values())
    return totals


def agent_live_payload(st, now=None) -> dict:
    """Build the snapshot dict sent to the admin dashboard (API + WebSocket)."""
    now = now or timezone.now()
    return {
        "agent_id": st.agent_id,
        "name": st.agent.name,
        "email": st.agent.email,
        "role": st.agent.role,
        "status": st.status,
        "status_display": dict(AgentWorkStatus.CHOICES).get(st.status, st.status),
        "since": st.since.isoformat(),
        "break_reason": st.break_reason,
        "last_seen": st.last_seen.isoformat(),
        "is_online": st.is_online,
        "current_lead_id": st.current_lead_id,
        "session_started_at": st.session_started_at.isoformat() if st.session_started_at else None,
        "totals": compute_today_totals(st.agent, now),
    }


def _broadcast(st, now=None):
    """Push a single agent's updated status to the tenant's monitoring group."""
    try:
        from apps.core.consumers import broadcast_to_monitors
        broadcast_to_monitors(
            connection.schema_name,
            "agent_status_update",
            {"agent": agent_live_payload(st, now)},
        )
    except Exception as exc:
        logger.warning(f"[Presence] broadcast failed: {exc}")


def sweep_stale(threshold_seconds=STALE_SECONDS) -> int:
    """
    Flip online agents whose heartbeat is stale to offline (crash/network drop).
    Broadcasts each change. Returns the number swept. Runs within a tenant schema.
    """
    cutoff = timezone.now() - timedelta(seconds=threshold_seconds)
    stale = (
        AgentStatus.objects.filter(last_seen__lt=cutoff)
        .exclude(status=AgentWorkStatus.OFFLINE)
        .select_related("agent")
    )
    count = 0
    for st in stale:
        set_agent_status(st.agent, AgentWorkStatus.OFFLINE)
        count += 1
    return count
