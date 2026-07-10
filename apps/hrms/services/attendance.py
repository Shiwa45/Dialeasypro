"""
TeleCRM Backend — apps/hrms/services/attendance.py

Derives attendance from data the CRM already captures.

AgentStatusLog records exactly when an agent was online during an auto-dial
session (available / on_call / wrap_up / break). Summing those intervals for a
day gives worked time without asking anyone to clock in — and guarantees the
HRMS timesheet and the Live Agents dashboard never disagree.

Manual check-in/out and admin corrections override the derived value; a row is
only recomputed while its source is AUTO.
"""
import logging
from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.constants import AgentWorkStatus
from apps.hrms.constants import AttendanceSource, AttendanceStatus
from apps.hrms.models import Attendance, Employee, Holiday

logger = logging.getLogger(__name__)

# A day with at least this much online time counts as present; at least
# HALF_DAY_SECONDS counts as a half day. Below that, absent.
FULL_DAY_SECONDS = 6 * 3600
HALF_DAY_SECONDS = 3 * 3600


def _day_bounds(day):
    """Timezone-aware [start, end) for a local calendar date."""
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    return start, start + timedelta(days=1)


def compute_worked_seconds(agent, day) -> tuple[int, int]:
    """
    (worked_seconds, break_seconds) for an agent on a local calendar date,
    summed from their status intervals. Intervals are clipped to the day, and
    an interval still open (ended_at=None) is counted up to now.
    """
    from apps.authentication.models import AgentStatusLog

    start, end = _day_bounds(day)
    now = timezone.now()

    worked = break_secs = 0
    logs = AgentStatusLog.objects.filter(agent=agent, started_at__lt=end).exclude(
        ended_at__lte=start
    )
    for log in logs:
        lo = max(log.started_at, start)
        hi = min(log.ended_at or now, end)
        seconds = int((hi - lo).total_seconds())
        if seconds <= 0:
            continue
        if log.status == AgentWorkStatus.BREAK:
            break_secs += seconds
        elif log.status in AgentWorkStatus.ONLINE_STATUSES:
            worked += seconds

    return worked, break_secs


def _status_for(worked_seconds: int, day, employee) -> str:
    if Holiday.objects.filter(date=day).exists():
        return AttendanceStatus.HOLIDAY

    working_days = employee.agent.working_days or []
    # Agent.working_days is [0=Mon .. 6=Sun]. Empty means "no schedule set" —
    # treat every day as a working day rather than marking everything a week off.
    if working_days and day.weekday() not in working_days:
        return AttendanceStatus.WEEK_OFF

    if worked_seconds >= FULL_DAY_SECONDS:
        return AttendanceStatus.PRESENT
    if worked_seconds >= HALF_DAY_SECONDS:
        return AttendanceStatus.HALF_DAY
    return AttendanceStatus.ABSENT


@transaction.atomic
def sync_attendance_for(employee: Employee, day) -> Attendance | None:
    """
    Recompute one employee/day attendance row from status logs.

    Never overwrites a MANUAL or ADMIN row — those are deliberate human input.
    Returns the row, or None when the employee is on approved leave (the leave
    approval already wrote the row).
    """
    existing = Attendance.objects.filter(employee=employee, date=day).first()
    if existing and existing.source != AttendanceSource.AUTO:
        return existing
    if existing and existing.status == AttendanceStatus.ON_LEAVE:
        return existing

    worked, breaks = compute_worked_seconds(employee.agent, day)
    status = _status_for(worked, day, employee)

    row, _ = Attendance.objects.update_or_create(
        employee=employee,
        date=day,
        defaults={
            "status": status,
            "source": AttendanceSource.AUTO,
            "worked_seconds": worked,
            "break_seconds": breaks,
        },
    )
    return row


def sync_attendance_for_date(day) -> int:
    """Recompute every active employee's attendance for a date. Returns rows written."""
    count = 0
    for employee in Employee.objects.filter(is_active=True).select_related("agent"):
        try:
            if sync_attendance_for(employee, day):
                count += 1
        except Exception as exc:  # one bad employee must not abort the batch
            logger.error(f"[HRMS] attendance sync failed for {employee.employee_code}: {exc}")
    return count


def mark_check_in(employee: Employee, at=None) -> Attendance:
    """Manual check-in. Promotes the row to MANUAL so auto-sync won't clobber it."""
    at = at or timezone.now()
    day = timezone.localdate(at)
    row, _ = Attendance.objects.get_or_create(employee=employee, date=day)
    if row.check_in is None:
        row.check_in = at
    row.source = AttendanceSource.MANUAL
    row.save(update_fields=["check_in", "source", "updated_at"])
    return row


def mark_check_out(employee: Employee, at=None) -> Attendance:
    """Manual check-out. Worked time = check_out - check_in, minus recorded breaks."""
    at = at or timezone.now()
    day = timezone.localdate(at)
    row, _ = Attendance.objects.get_or_create(employee=employee, date=day)
    row.check_out = at
    row.source = AttendanceSource.MANUAL
    if row.check_in:
        span = int((at - row.check_in).total_seconds())
        row.worked_seconds = max(0, span - row.break_seconds)
        row.status = _status_for(row.worked_seconds, day, employee)
    row.save(update_fields=["check_out", "source", "worked_seconds", "status", "updated_at"])
    return row
