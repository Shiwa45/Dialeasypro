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
#
# Per status, because the app cannot always heartbeat. During a call the
# phone's own dialer is on screen and Android freezes the app within seconds,
# so a flat 60 seconds turned every call longer than a minute into "offline"
# — as did a break with the phone locked. The daily login report is built
# from these intervals, so they have to survive a normal working day.
STALE_SECONDS = 60  # fallback for any status not listed below
STALE_AFTER = {
    AgentWorkStatus.AVAILABLE: 3 * 60,
    AgentWorkStatus.WRAP_UP: 15 * 60,
    AgentWorkStatus.ON_CALL: 2 * 60 * 60,
    AgentWorkStatus.BREAK: 90 * 60,
}


def set_agent_status(
    agent,
    status,
    *,
    break_reason="",
    call_id=None,
    lead_id=None,
    broadcast=True,
    at=None,
):
    """
    Apply a status transition for an agent. Idempotent for the same status
    (treated as a heartbeat). Returns the AgentStatus row.

    `at` backdates the transition — the stale sweep closes a vanished agent's
    interval when they were last seen, not when the sweep happened to run.
    """
    if status not in AgentWorkStatus.REPORTABLE:
        raise ValueError(f"Invalid status: {status}")

    now = at or timezone.now()
    st, _ = AgentStatus.objects.get_or_create(
        agent=agent,
        defaults={"status": AgentWorkStatus.OFFLINE, "since": now, "last_seen": now},
    )

    changed = st.status != status
    if at is None:
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


def touch_heartbeat(agent, status=None, break_reason=""):
    """
    Refresh last_seen so the session isn't swept to offline.

    The app also says what it believes its status is. If the server disagrees —
    most often because the agent was swept offline while the phone was frozen
    during a call or a locked-screen break — the app's status is applied. The
    app only reports changes, so without this an agent who came back stayed
    "offline" on the board, working, until their status next changed.
    """
    if status and status in AgentWorkStatus.REPORTABLE:
        current = (
            AgentStatus.objects.filter(agent=agent).values_list("status", flat=True).first()
        )
        if current != status:
            set_agent_status(agent, status, break_reason=break_reason)
            return
    AgentStatus.objects.filter(agent=agent).update(last_seen=timezone.now())


def status_totals(logs, start, end) -> dict:
    """
    Seconds in each online status within [start, end), from AgentStatusLog rows.
    An open interval runs to `end`; intervals are clipped to the window, so one
    that started before midnight still counts the part after it.
    """
    totals = {
        AgentWorkStatus.AVAILABLE: 0,
        AgentWorkStatus.ON_CALL: 0,
        AgentWorkStatus.WRAP_UP: 0,
        AgentWorkStatus.BREAK: 0,
    }
    for log in logs:
        begin = max(log.started_at, start)
        finish = min(log.ended_at or end, end)
        dur = int((finish - begin).total_seconds())
        if dur > 0:
            totals[log.status] = totals.get(log.status, 0) + dur
    totals["online"] = sum(totals.values())
    return totals


def compute_today_totals(agent, now=None) -> dict:
    """Seconds spent in each online status since local midnight (incl. open interval)."""
    now = now or timezone.now()
    # timezone.now() is UTC, so replacing the time on it gives UTC midnight —
    # 05:30 in Asia/Kolkata. "Today" therefore started this morning at half
    # five and, for anyone looking before that, still included last night.
    # Localise first so the day boundary is the tenant's, as the docstring
    # has always claimed.
    start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    # Everything that overlaps today — including an interval still open from
    # before midnight, which `started_at >= start` used to drop entirely.
    from django.db.models import Q

    logs = AgentStatusLog.objects.filter(agent=agent, started_at__lt=now).filter(
        Q(ended_at__isnull=True) | Q(ended_at__gt=start)
    )
    return status_totals(logs, start, now)


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
    now = timezone.now()
    candidates = (
        AgentStatus.objects.filter(last_seen__lt=now - timedelta(seconds=threshold_seconds))
        .exclude(status=AgentWorkStatus.OFFLINE)
        .select_related("agent")
    )
    count = 0
    for st in candidates:
        allowed = STALE_AFTER.get(st.status, threshold_seconds)
        if (now - st.last_seen).total_seconds() < allowed:
            continue
        # Close at the last sign of life: the time after it was not worked.
        set_agent_status(st.agent, AgentWorkStatus.OFFLINE, at=st.last_seen)
        count += 1
    return count
