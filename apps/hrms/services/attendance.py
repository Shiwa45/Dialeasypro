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

# Defaults: a day with at least this much online time counts as present; at
# least HALF_DAY_SECONDS counts as a half day. Below that, absent. Each company
# can change them on its HrmsPolicy (Settings → Policy).
FULL_DAY_SECONDS = 6 * 3600
HALF_DAY_SECONDS = 3 * 3600


def thresholds() -> tuple[int, int]:
    """(full_day_seconds, half_day_seconds) from the company's policy."""
    from apps.hrms.models import HrmsPolicy

    policy = HrmsPolicy.objects.order_by("pk").first()
    if policy is None:
        return FULL_DAY_SECONDS, HALF_DAY_SECONDS
    return int(policy.full_day_hours * 3600), int(policy.half_day_hours * 3600)


def _day_bounds(day):
    """Timezone-aware [start, end) for a local calendar date."""
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    return start, start + timedelta(days=1)


def compute_worked_seconds(agent, day, window=None) -> tuple[int, int]:
    """
    (worked_seconds, break_seconds) for an agent on a local calendar date,
    summed from their status intervals. Intervals are clipped to the day (or
    to `window`, a (start, end) pair inside it), and an interval still open
    (ended_at=None) is counted up to now.
    """
    from apps.authentication.models import AgentStatusLog

    start, end = _day_bounds(day)
    if window is not None:
        start, end = max(start, window[0]), min(end, window[1])
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


def day_off_status(day, employee, holidays=None) -> str | None:
    """HOLIDAY or WEEK_OFF when the employee was not due to work that day, else None.

    `holidays` is an optional set of dates, to save a query per day in loops.
    """
    is_holiday = (day in holidays) if holidays is not None else Holiday.objects.filter(date=day).exists()
    if is_holiday:
        return AttendanceStatus.HOLIDAY

    # Agent.working_days is [0=Mon .. 6=Sun]. Empty means "no schedule set":
    # that is Monday–Saturday, not every day — "every day" marked each Sunday
    # absent and payroll docked a day for it.
    from apps.authentication.models import DEFAULT_WORKING_DAYS

    working_days = employee.agent.working_days or DEFAULT_WORKING_DAYS
    if day.weekday() not in working_days:
        return AttendanceStatus.WEEK_OFF
    return None


def status_for(worked_seconds: int, day, employee) -> str:
    """The attendance status the worked time earns on this day."""
    off = day_off_status(day, employee)
    if off:
        return off

    full, half = thresholds()
    if worked_seconds >= full:
        return AttendanceStatus.PRESENT
    if worked_seconds >= half:
        return AttendanceStatus.HALF_DAY
    return AttendanceStatus.ABSENT


_status_for = status_for


@transaction.atomic
def sync_attendance_for(employee: Employee, day) -> Attendance | None:
    """
    Recompute one employee/day attendance row from status logs.

    Never overwrites a MANUAL or ADMIN row — those are deliberate human input.
    Returns the row, or None when the employee is on approved leave (the leave
    approval already wrote the row).
    """
    existing = Attendance.objects.filter(employee=employee, date=day).first()
    if (
        existing
        and existing.source == AttendanceSource.MANUAL
        and existing.check_in
        and existing.check_out is None
        and day < timezone.localdate()
    ):
        # Checked in, never checked out, and the day is over. Check-in marks
        # the day present while it runs; left like that, it was a full
        # present day for good, because the sync never touches MANUAL rows.
        # Close it with the time the dialer recorded.
        worked, breaks = compute_worked_seconds(employee.agent, day)
        existing.worked_seconds = worked
        existing.break_seconds = breaks
        existing.status = status_for(worked, day, employee)
        existing.note = (existing.note or "No check-out; hours from the dialer.")[:200]
        existing.save(update_fields=["worked_seconds", "break_seconds", "status", "note", "updated_at"])
        return existing
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


def sync_attendance_for_date(day, stats: dict | None = None) -> int:
    """
    Recompute every active employee's attendance for a date. Returns the rows
    rebuilt from the dialer; rows kept as they were (corrected by hand,
    checked in, or on leave) are counted in stats["kept"] when given.
    """
    count = kept = 0
    for employee in Employee.objects.filter(is_active=True).select_related("agent"):
        try:
            before = Attendance.objects.filter(employee=employee, date=day).values_list(
                "source", "status").first()
            row = sync_attendance_for(employee, day)
            if row is None:
                continue
            if before and (before[0] != AttendanceSource.AUTO or before[1] == AttendanceStatus.ON_LEAVE):
                kept += 1
            else:
                count += 1
        except Exception as exc:  # one bad employee must not abort the batch
            logger.error(f"[HRMS] attendance sync failed for {employee.employee_code}: {exc}")
    if stats is not None:
        stats["kept"] = kept
    return count


def resync_auto_rows(day) -> int:
    """Rebuild the dialer-derived rows for a date (e.g. after a holiday changes)."""
    if day > timezone.localdate():
        return 0
    count = 0
    for row in Attendance.objects.filter(date=day, source=AttendanceSource.AUTO).select_related(
        "employee__agent"
    ):
        sync_attendance_for(row.employee, day)
        count += 1
    return count


def mark_check_in(employee: Employee, at=None) -> Attendance:
    """
    Manual check-in. Promotes the row to MANUAL so auto-sync won't clobber it.

    Sets the status, which is the whole point and is what was missing: the
    model defaults status to ABSENT, this function never touched it, and it
    was not even in update_fields. So an agent tapping "check in" created an
    ABSENT row with a check-in time on it, and the CRM dutifully showed them
    absent.

    Promoting the row to MANUAL at the same time made it permanent —
    sync_attendance_for refuses to recompute anything that is not AUTO, so
    the derived path could never correct it either. The agent stayed absent
    for the rest of the day no matter how long they worked.

    Checking in claims presence for the day. Check-out recomputes from the
    hours actually worked and will downgrade to half-day or absent if the
    span does not justify it.
    """
    at = at or timezone.now()
    day = timezone.localdate(at)
    row, _ = Attendance.objects.get_or_create(employee=employee, date=day)

    # Approved leave is a decision somebody already made. If an agent on
    # leave opens the app and taps check in, do not silently overturn it —
    # return the row as it stands and let a human sort it out.
    if row.status == AttendanceStatus.ON_LEAVE:
        return row

    if row.check_in is None:
        row.check_in = at
    row.status = AttendanceStatus.PRESENT
    row.source = AttendanceSource.MANUAL
    row.save(update_fields=["check_in", "status", "source", "updated_at"])
    return row


def mark_check_out(employee: Employee, at=None) -> Attendance:
    """
    Manual check-out. Worked time = check_out - check_in, minus recorded breaks.

    A check-out with no check-in falls back to the time derived from the
    agent's status logs rather than leaving the row at its ABSENT default.
    Somebody who dialled all morning and only remembered to press the button
    on the way out should not be recorded as absent.
    """
    at = at or timezone.now()
    day = timezone.localdate(at)
    row, _ = Attendance.objects.get_or_create(employee=employee, date=day)

    if row.status == AttendanceStatus.ON_LEAVE:
        return row

    row.check_out = at
    row.source = AttendanceSource.MANUAL
    if row.check_in:
        # Breaks taken in the dialer between check-in and check-out.
        _, breaks = compute_worked_seconds(employee.agent, day, window=(row.check_in, at))
        row.break_seconds = breaks
        span = int((at - row.check_in).total_seconds())
        row.worked_seconds = max(0, span - breaks)
    else:
        worked, breaks = compute_worked_seconds(employee.agent, day)
        row.worked_seconds = worked
        row.break_seconds = breaks
    row.status = status_for(row.worked_seconds, day, employee)
    row.save(update_fields=[
        "check_out", "source", "worked_seconds", "break_seconds", "status", "updated_at",
    ])
    return row
