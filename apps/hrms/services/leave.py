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
    """Approve a pending request: decrement balance and write attendance."""
    if leave.status != ApprovalStatus.PENDING:
        raise ValueError(f"Leave is already {leave.status}.")

    year = leave.start_date.year
    # Lock the balance row so two approvers can't both spend the same days.
    if leave.leave_type.annual_quota_days > 0:
        balance = (
            LeaveBalance.objects.select_for_update()
            .filter(employee=leave.employee, leave_type=leave.leave_type, year=year)
            .first()
        ) or balance_for(leave.employee, leave.leave_type, year)

        if balance.remaining_days < leave.days:
            raise ValueError(
                f"Insufficient balance: {balance.remaining_days} day(s) left, "
                f"{leave.days} requested."
            )
        balance.used_days += leave.days
        balance.save(update_fields=["used_days", "updated_at"])

    # Attendance for each calendar day in the range. Only paid types are marked
    # ON_LEAVE (payable); unpaid leave stays ABSENT so payroll docks it.
    status = AttendanceStatus.ON_LEAVE if leave.leave_type.is_paid else AttendanceStatus.ABSENT
    day = leave.start_date
    while day <= leave.end_date:
        Attendance.objects.update_or_create(
            employee=leave.employee,
            date=day,
            defaults={
                "status": status,
                "source": AttendanceSource.ADMIN,
                "worked_seconds": 0,
                "note": f"{leave.leave_type.name} (leave #{leave.pk})",
            },
        )
        day += timedelta(days=1)

    leave.status = ApprovalStatus.APPROVED
    leave.decided_by = decided_by
    leave.decided_at = timezone.now()
    leave.decision_note = note[:300]
    leave.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    return leave


@transaction.atomic
def reject_leave(leave: LeaveRequest, decided_by, note: str = "") -> LeaveRequest:
    if leave.status != ApprovalStatus.PENDING:
        raise ValueError(f"Leave is already {leave.status}.")
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
        raise ValueError(f"Cannot cancel a {leave.status} leave.")

    if leave.status == ApprovalStatus.APPROVED and leave.leave_type.annual_quota_days > 0:
        balance = (
            LeaveBalance.objects.select_for_update()
            .filter(employee=leave.employee, leave_type=leave.leave_type, year=leave.start_date.year)
            .first()
        )
        if balance:
            balance.used_days = max(Decimal("0"), balance.used_days - leave.days)
            balance.save(update_fields=["used_days", "updated_at"])

        # Drop the leave attendance rows; the nightly sync will recompute them.
        Attendance.objects.filter(
            employee=leave.employee,
            date__gte=leave.start_date,
            date__lte=leave.end_date,
            note__contains=f"leave #{leave.pk}",
        ).delete()

    leave.status = ApprovalStatus.CANCELLED
    leave.save(update_fields=["status", "updated_at"])
    return leave
