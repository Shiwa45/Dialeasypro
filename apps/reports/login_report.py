"""
TeleCRM Backend — apps/reports/login_report.py

The agent login report: for every agent, for every day, when they came
online, when they were last seen, and how the time in between was spent —
available (idle), on call, wrap-up and break — with their calls alongside.

Built from AgentStatusLog, the same intervals the Live Agents board reads, so
today's row is live: an agent still online is counted up to this moment.
Days are the tenant's local days (IST), not UTC ones.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.authentication.models import Agent, AgentStatus, AgentStatusLog
from apps.authentication.presence import status_totals
from apps.core.constants import AgentWorkStatus

MAX_DAYS = 31

COLUMNS = [
    ("date", "Date"),
    ("name", "Agent"),
    ("role", "Role"),
    ("first_online", "First online"),
    ("last_seen", "Last seen"),
    ("online_seconds", "Logged in (h:mm)"),
    ("available_seconds", "Idle / available (h:mm)"),
    ("on_call_seconds", "On call (h:mm)"),
    ("wrap_up_seconds", "Wrap-up (h:mm)"),
    ("break_seconds", "Break (h:mm)"),
    ("break_count", "Breaks"),
    ("break_reasons", "Break reasons"),
    ("calls", "Calls"),
    ("connected_calls", "Connected"),
    ("occupancy", "Occupancy %"),
]


def csv_cell(key: str, value):
    """A report value as a spreadsheet reader wants it: 14:22, not an ISO
    timestamp with microseconds; 3:05, not 11131 seconds."""
    if value is None:
        return ""
    if key in ("first_online", "last_seen"):
        return datetime.fromisoformat(value).strftime("%H:%M")
    if key.endswith("_seconds"):
        minutes = int(value) // 60
        return f"{minutes // 60}:{minutes % 60:02d}"
    return value


def _day_bounds(day: date):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    return start, start + timedelta(days=1)


def build_login_report(date_from: date, date_to: date, now=None) -> list[dict]:
    """
    One row per (day, active agent), newest day first. An agent with no
    activity on a day still gets a row — "never logged in" is part of the
    report, not a gap in it.
    """
    now = now or timezone.now()
    range_start, _ = _day_bounds(date_from)
    _, range_end = _day_bounds(date_to)

    agents = list(Agent.objects.filter(is_active=True).order_by("name"))
    live = dict(AgentStatus.objects.values_list("agent_id", "status"))

    logs_by_agent = defaultdict(list)
    for log in AgentStatusLog.objects.filter(
        started_at__lt=min(range_end, now),
    ).filter(Q(ended_at__isnull=True) | Q(ended_at__gt=range_start)).order_by("started_at"):
        logs_by_agent[log.agent_id].append(log)

    from apps.calls.models import CallLog

    calls = defaultdict(lambda: {"calls": 0, "connected": 0})
    for row in (
        CallLog.objects.filter(started_at__gte=range_start, started_at__lt=range_end)
        .values("agent_id", "started_at__date")
        .annotate(n=Count("id"), connected=Count("id", filter=Q(is_connected=True)))
    ):
        # started_at__date is evaluated in the current (local) time zone.
        calls[(row["agent_id"], row["started_at__date"])] = {
            "calls": row["n"], "connected": row["connected"],
        }

    rows = []
    day = date_to
    while day >= date_from:
        start, end = _day_bounds(day)
        window_end = min(end, now)
        for agent in agents:
            day_logs = [
                log for log in logs_by_agent.get(agent.id, [])
                if log.started_at < window_end and (log.ended_at is None or log.ended_at > start)
            ]
            totals = status_totals(day_logs, start, max(window_end, start))
            first = min((max(l.started_at, start) for l in day_logs), default=None)
            still_open = any(l.ended_at is None for l in day_logs)
            last = None
            if day_logs:
                closed = [min(l.ended_at, end) for l in day_logs if l.ended_at]
                last = window_end if still_open or not closed else max(closed)
            breaks = [l for l in day_logs if l.status == AgentWorkStatus.BREAK]
            reasons = defaultdict(int)
            for b in breaks:
                reasons[b.break_reason or "Unspecified"] += 1
            c = calls.get((agent.id, day), {"calls": 0, "connected": 0})
            online = totals["online"]
            is_today = day == timezone.localdate(now)
            status_now = live.get(agent.id, AgentWorkStatus.OFFLINE) if is_today else None
            # "Online now" needs both an open interval and a live status —
            # the two are kept in step, and the row must not contradict itself.
            online_now = bool(is_today and still_open and status_now != AgentWorkStatus.OFFLINE)
            rows.append({
                "date": day.isoformat(),
                "agent_id": agent.id,
                "name": agent.name,
                "role": agent.role,
                "status_now": status_now,
                "online_now": online_now,
                "first_online": timezone.localtime(first).isoformat() if first else None,
                "last_seen": timezone.localtime(last).isoformat() if last else None,
                "online_seconds": online,
                "available_seconds": totals[AgentWorkStatus.AVAILABLE],
                "on_call_seconds": totals[AgentWorkStatus.ON_CALL],
                "wrap_up_seconds": totals[AgentWorkStatus.WRAP_UP],
                "break_seconds": totals[AgentWorkStatus.BREAK],
                "break_count": len(breaks),
                "break_reasons": "; ".join(f"{r} ×{n}" for r, n in sorted(reasons.items())),
                "calls": c["calls"],
                "connected_calls": c["connected"],
                "occupancy": round(totals[AgentWorkStatus.ON_CALL] / online * 100) if online else 0,
            })
        day -= timedelta(days=1)
    return rows
