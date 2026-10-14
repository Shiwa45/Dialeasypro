"""
TeleCRM Backend — apps/hrms/services/leave.py

Leave application and approval.

Approving leave must do three things atomically: mark the request approved,
decrement the balance, and write ON_LEAVE attendance rows for the date range.
If any step fails the whole thing rolls back — a decremented balance with no
attendance (or vice versa) is worse than a failed approval.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.hrms.constants import ApprovalStatus, AttendanceSource, AttendanceStatus
from apps.hrms.models import Attendance, LeaveBalance, LeaveRequest

logger = logging.getLogger(__name__)


def balance_for(employee, leave_type, year: int) -> LeaveBalance:
    """Get (or open) the employee's balance row, seeded from the type's quota."""
    balance, created = LeaveBalance.objects.get_or_create(
        employee=employee,
        leave_type=leave_type,
        year=year,
        defaults={"allocated_days": leave_type.annual_quota_days},
    )
    return balance


def has_sufficient_balance(employee, leave_type, year: int, days: Decimal) -> bool:
    """A quota of 0 means the type is unlimited/unpaid — always allowed."""
    if leave_type.annual_quota_days == 0:
        return True
    return balance_for(employee, leave_type, year).remaining_days >= days


class LeaveError(ValueError):
    """A leave request that can't be made or decided. `field` names the input at fault."""

    def __init__(self, message, field="non_field_errors"):
        super().__init__(message)
        self.field = field


def leave_working_days(employee, start, end) -> list:
    """The days in [start, end] the employee was due to work (no holidays or week-offs)."""
    from apps.hrms.models import Holiday
    from apps.hrms.services.attendance import day_off_status

    holidays = set(Holiday.objects.filter(date__gte=start, date__lte=end).values_list("date", flat=True))
    days, day = [], start
    while day <= end:
        if not day_off_status(day, employee, holidays=holidays):
            days.append(day)
        day += timedelta(days=1)
    return days


def days_by_year(employee, start, end, half_day=False) -> dict:
    """{year: Decimal days} the range takes from each year's balance."""
    out: dict[int, Decimal] = {}
    for day in leave_working_days(employee, start, end):
        out[day.year] = out.get(day.year, Decimal("0")) + (Decimal("0.5") if half_day else Decimal("1"))
    return out


def _fmt_days(dates) -> str:
    return ", ".join(d.strftime("%d %b %Y") for d in dates)


def worked_days_in(employee, start, end) -> list:
    """Days in the range on which attendance shows the employee worked."""
    return list(
        Attendance.objects.filter(
            employee=employee, date__gte=start, date__lte=end,
            status__in=[AttendanceStatus.PRESENT, AttendanceStatus.HALF_DAY],
        ).order_by("date").values_list("date", flat=True)
    )


def _check_payroll_open(employee, start, end, verb: str):
    from apps.hrms.services.payroll import locked_days

    months = locked_days(employee, start, end)
    if months:
        names = ", ".join(m.strftime("%B %Y") for m in months)
        raise LeaveError(
            f"Can't {verb} this leave: payroll for {names} is already finalized. "
            f"Reopen that payslip first."
        )


def validate_request(employee, leave_type, start, end, half_day=False, today=None) -> dict:
    """
    Check a new request and return {year: days}. Raises LeaveError.

    The number of days is always counted here from the dates; it used to be
    typed in, so a six-day leave could be charged as half a day.
    """
    today = today or timezone.localdate()
    if end < start:
        raise LeaveError("End date cannot precede start date.", "end_date")
    if half_day and start != end:
        raise LeaveError("A half day must start and end on the same date.", "half_day")
    if not leave_type.is_active:
        raise LeaveError(f"{leave_type.name} is switched off.", "leave_type")
    if start < employee.date_of_joining:
        raise LeaveError(
            f"{employee.agent.name} joined on {employee.date_of_joining:%d %b %Y}; "
            f"leave can't start before that.", "start_date",
        )
    if employee.date_of_exit and end > employee.date_of_exit:
        raise LeaveError(
            f"{employee.agent.name} leaves on {employee.date_of_exit:%d %b %Y}; "
            f"leave can't run past that.", "end_date",
        )
    if end > today + timedelta(days=366):
        raise LeaveError("Leave can be applied at most a year ahead.", "end_date")

    per_year = days_by_year(employee, start, end, half_day)
    if not per_year:
        raise LeaveError("There are no working days in these dates (only holidays or week-offs).", "start_date")

    if overlapping_requests(employee, start, end).exists():
        raise LeaveError(
            "There is already a pending or approved leave overlapping these dates.", "start_date"
        )
    _check_payroll_open(employee, start, end, "apply for")

    if not half_day:
        worked = worked_days_in(employee, start, end)
        if worked:
            raise LeaveError(
                f"Attendance shows work on {_fmt_days(worked)}. Leave those days out, "
                f"or correct the attendance first.", "start_date",
            )

    if leave_type.annual_quota_days > 0:
        for year, days in sorted(per_year.items()):
            if not has_sufficient_balance(employee, leave_type, year, days):
                left = balance_for(employee, leave_type, year).remaining_days
                raise LeaveError(
                    f"Insufficient {leave_type.name} balance for {year}: {left} day(s) left, "
                    f"{days} needed.", "leave_type",
                )
    return per_year


def overlapping_requests(employee, start_date, end_date, exclude_pk=None):
    """Open or approved requests that clash with the range."""
    qs = LeaveRequest.objects.filter(
        employee=employee,
        status__in=[ApprovalStatus.PENDING, ApprovalStatus.APPROVED],
        start_date__lte=end_date,
        end_date__gte=start_date,
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs


@transaction.atomic
def approve_leave(leave: LeaveRequest, decided_by, note: str = "") -> LeaveRequest:
    """Approve a pending request: charge each year's balance and write attendance."""
    if leave.status != ApprovalStatus.PENDING:
        raise LeaveError(f"Leave is already {leave.status}.")

    employee = leave.employee
    _check_payroll_open(employee, leave.start_date, leave.end_date, "approve")

    # Counted again from the dates: a holiday may have been added since.
    per_year = days_by_year(employee, leave.start_date, leave.end_date, leave.half_day)
    if not per_year:
        raise LeaveError("There are no working days left in these dates.")

    if not leave.half_day:
        worked = worked_days_in(employee, leave.start_date, leave.end_date)
        if worked:
            raise LeaveError(
                f"{employee.agent.name} worked on {_fmt_days(worked)}. Approving would erase "
                f"that work — ask them to shorten the leave, or correct the attendance first."
            )

    if leave.leave_type.annual_quota_days > 0:
        for year, days in sorted(per_year.items()):
            # Lock the balance row so two approvers can't both spend the same days.
            balance = (
                LeaveBalance.objects.select_for_update()
                .filter(employee=employee, leave_type=leave.leave_type, year=year)
                .first()
            ) or balance_for(employee, leave.leave_type, year)
            if balance.remaining_days < days:
                raise LeaveError(
                    f"Insufficient balance for {year}: {balance.remaining_days} day(s) left, "
                    f"{days} requested."
                )
            balance.used_days += days
            balance.save(update_fields=["used_days", "updated_at"])

    # A half day leaves the attendance row alone: the employee works the
    # other half, and payroll adds the leave's half to whatever was worked.
    if not leave.half_day:
        # Only paid types are marked ON_LEAVE (payable); unpaid leave stays
        # ABSENT so payroll docks it. Holidays and week-offs inside the range
        # stay days off.
        from apps.hrms.services.attendance import day_off_status

        status = AttendanceStatus.ON_LEAVE if leave.leave_type.is_paid else AttendanceStatus.ABSENT
        day = leave.start_date
        while day <= leave.end_date:
            day_status = day_off_status(day, employee) or status
            Attendance.objects.update_or_create(
                employee=employee,
                date=day,
                defaults={
                    "status": day_status,
                    "source": AttendanceSource.ADMIN,
                    "worked_seconds": 0,
                    "note": f"{leave.leave_type.name} (leave #{leave.pk})",
                },
            )
            day += timedelta(days=1)

    leave.days = sum(per_year.values(), Decimal("0"))
    leave.charged_days = (
        {str(y): str(d) for y, d in per_year.items()}
        if leave.leave_type.annual_quota_days > 0 else {}
    )
    leave.status = ApprovalStatus.APPROVED
    leave.decided_by = decided_by
    leave.decided_at = timezone.now()
    leave.decision_note = note[:300]
    leave.save(update_fields=[
        "days", "charged_days", "status", "decided_by", "decided_at", "decision_note", "updated_at",
    ])
    return leave


@transaction.atomic
def reject_leave(leave: LeaveRequest, decided_by, note: str = "") -> LeaveRequest:
    if leave.status != ApprovalStatus.PENDING:
        raise LeaveError(f"Leave is already {leave.status}.")
    leave.status = ApprovalStatus.REJECTED
    leave.decided_by = decided_by
    leave.decided_at = timezone.now()
    leave.decision_note = note[:300]
    leave.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    return leave


@transaction.atomic
def cancel_leave(leave: LeaveRequest) -> LeaveRequest:
    """Cancel a request, refunding balance and clearing attendance if approved."""
    if leave.status not in (ApprovalStatus.PENDING, ApprovalStatus.APPROVED):
        raise LeaveError(f"Cannot cancel a {leave.status} leave.")

    if leave.status == ApprovalStatus.APPROVED:
        # The finalized payslip was built from this leave; cancelling it
        # would leave the slip disagreeing with the records.
        _check_payroll_open(leave.employee, leave.start_date, leave.end_date, "cancel")

        if leave.leave_type.annual_quota_days > 0:
            charged = leave.charged_days or {str(leave.start_date.year): str(leave.days)}
            for year, days in charged.items():
                balance = (
                    LeaveBalance.objects.select_for_update()
                    .filter(employee=leave.employee, leave_type=leave.leave_type, year=int(year))
                    .first()
                )
                if balance:
                    balance.used_days = max(Decimal("0"), balance.used_days - Decimal(days))
                    balance.save(update_fields=["used_days", "updated_at"])

        # Drop the leave attendance rows and rebuild the past ones from the
        # dialer (the nightly sync only looks at yesterday).
        rows = Attendance.objects.filter(
            employee=leave.employee,
            date__gte=leave.start_date,
            date__lte=leave.end_date,
            note__contains=f"leave #{leave.pk}",
        )
        dates = list(rows.values_list("date", flat=True))
        rows.delete()
        from apps.hrms.services.attendance import sync_attendance_for

        today = timezone.localdate()
        for day in dates:
            if day < today:
                sync_attendance_for(leave.employee, day)

    leave.status = ApprovalStatus.CANCELLED
    leave.save(update_fields=["status", "updated_at"])
    return leave
