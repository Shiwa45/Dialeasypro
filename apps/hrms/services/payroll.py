"""
TeleCRM Backend — apps/hrms/services/payroll.py

Builds monthly payslips from: the employee's salary structure, attendance
(loss-of-pay), approved incentives, and approved expense reimbursements.

⚠️ STATUTORY DEDUCTIONS ARE NOT DERIVED HERE.
PF, ESI, professional tax and TDS depend on wage slabs, state, employee age,
declarations and exemptions, and they change with each Finance Act. Getting
them wrong is a compliance liability, not a bug. This module therefore uses the
flat monthly amounts an admin records on SalaryStructure, and applies them
verbatim. Wire a payroll/compliance provider (or have a CA sign off on a rate
table) before claiming automatic statutory computation.

Loss of pay
-----------
gross is pro-rated by payable days / total days in the month. Every day of the
month is put in exactly one bucket (attendance_breakdown):

  payable   present, paid leave, holiday, week-off, unrecorded; half a half day
  unpaid    absent, unpaid leave; the other half of a half day
  neither   before the date of joining or after the date of exit

and the counts are stored on the payslip so it shows how the pay was reached.
"""
import logging
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.hrms.constants import ApprovalStatus, AttendanceStatus, PayslipStatus
from apps.hrms.models import (
    Attendance,
    Employee,
    ExpenseClaim,
    Holiday,
    IncentiveEarning,
    LeaveRequest,
    Payslip,
    SalaryStructure,
)
from apps.hrms.services.incentives import month_bounds, month_start

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


def active_structure(employee: Employee, on: date) -> SalaryStructure | None:
    """The salary structure in force on a date (latest effective_from <= on)."""
    return (
        SalaryStructure.objects.filter(employee=employee, effective_from__lte=on)
        .order_by("-effective_from")
        .first()
    )


def payable_days(employee: Employee, period_month: date) -> tuple[Decimal, Decimal]:
    """(payable_days, total_days_in_month) from attendance rows."""
    payable, total, _ = attendance_summary(employee, period_month)
    return payable, total


# Attendance status -> breakdown bucket.
_BUCKET = {
    AttendanceStatus.PRESENT: "present",
    AttendanceStatus.HALF_DAY: "half_day",
    AttendanceStatus.ON_LEAVE: "paid_leave",
    AttendanceStatus.HOLIDAY: "holiday",
    AttendanceStatus.WEEK_OFF: "week_off",
    AttendanceStatus.ABSENT: "absent",
}


def _approved_leave_days(employee: Employee, start: date, end: date) -> dict:
    """{date: (leave type name, is_paid)} for approved leave in [start, end)."""
    days = {}
    leaves = LeaveRequest.objects.filter(
        employee=employee, status=ApprovalStatus.APPROVED,
        start_date__lt=end, end_date__gte=start,
    ).select_related("leave_type")
    for leave in leaves:
        day = max(leave.start_date, start)
        last = min(leave.end_date, end - timedelta(days=1))
        while day <= last:
            days[day] = (leave.leave_type.name, leave.leave_type.is_paid)
            day += timedelta(days=1)
    return days


def attendance_breakdown(employee: Employee, period_month: date) -> dict:
    """
    Every day of the month, counted once, for the payslip.

    Unpaid leave is stored as an ABSENT attendance row (so it is docked); the
    approved leave requests tell it apart from a plain absence here.

    Days with no attendance row are PAID, deliberately: a missing row means
    the day was never synced, and docking pay for our own gap is worse than
    paying for it. A missing row on a holiday or week-off is simply that day
    off; only missing WORKING days are reported as unrecorded, so HR can sync
    or correct them before finalizing.

    Days before the date of joining or after the date of exit are not paid:
    they used to be credited as "unrecorded", so someone who joined on the
    15th was paid for the whole month.
    """
    from apps.hrms.services.attendance import day_off_status

    start, end = month_bounds(period_month)
    total = monthrange(start.year, start.month)[1]
    rows = {
        r.date: r
        for r in Attendance.objects.filter(employee=employee, date__gte=start, date__lt=end)
    }
    leave_days = _approved_leave_days(employee, start, end)
    holidays = set(Holiday.objects.filter(date__gte=start, date__lt=end).values_list("date", flat=True))

    counts = {
        "present": 0, "half_day": 0, "paid_leave": 0, "unpaid_leave": 0, "absent": 0,
        "holiday": 0, "week_off": 0, "unrecorded": 0, "not_employed": 0,
    }
    paid_leave_by_type: dict[str, float] = {}

    day = start
    while day < end:
        row = rows.get(day)
        leave_name, leave_paid = leave_days.get(day, (None, None))
        status = row.status if row else None

        if day < employee.date_of_joining or (employee.date_of_exit and day > employee.date_of_exit):
            bucket = "not_employed"
        elif row is None:
            # No record: a day off is a day off, approved leave is leave, and
            # anything else is an unsynced working day.
            off = day_off_status(day, employee, holidays=holidays)
            if off:
                bucket = _BUCKET[off]
            elif leave_paid is None:
                bucket = "unrecorded"
            else:
                bucket = "paid_leave" if leave_paid else "unpaid_leave"
        elif status == AttendanceStatus.ABSENT:
            bucket = "unpaid_leave" if leave_paid is False else "absent"
        else:
            bucket = _BUCKET.get(status, "absent")

        if bucket == "paid_leave":
            name = leave_name or "Leave"
            paid_leave_by_type[name] = paid_leave_by_type.get(name, 0) + 1
        counts[bucket] += 1
        day += timedelta(days=1)

    half = Decimal(counts["half_day"]) / 2
    payable = (
        Decimal(counts["present"] + counts["paid_leave"] + counts["holiday"]
                + counts["week_off"] + counts["unrecorded"])
        + half
    )
    lop = Decimal(counts["absent"] + counts["unpaid_leave"]) + half
    employed = total - counts["not_employed"]

    if counts["unrecorded"]:
        logger.warning(
            f"[HRMS] {employee.employee_code} {period_month:%Y-%m}: "
            f"{counts['unrecorded']} working day(s) without attendance — credited as payable. "
            f"Run `sync_attendance` for the period to correct this."
        )

    return {
        **counts,
        "total_days": total,
        "employed_days": employed,
        "working_days": employed - counts["holiday"] - counts["week_off"],
        "days_worked": str(Decimal(counts["present"]) + half),
        "paid_leave_by_type": paid_leave_by_type,
        "lop_days": str(lop),
        "payable_days": str(payable),
    }


def attendance_summary(employee: Employee, period_month: date) -> tuple[Decimal, Decimal, int]:
    """(payable_days, total_days_in_month, unrecorded_working_days)."""
    b = attendance_breakdown(employee, period_month)
    return Decimal(b["payable_days"]), Decimal(b["total_days"]), b["unrecorded"]


@transaction.atomic
def build_payslip(employee: Employee, period_month: date, *, recompute: bool = False) -> Payslip:
    """
    Create or refresh a DRAFT payslip. Finalized/paid payslips are never
    modified — call with a fresh period or reopen the slip deliberately.
    """
    period_month = month_start(period_month)

    slip = Payslip.objects.filter(employee=employee, period_month=period_month).first()
    if slip and slip.status != PayslipStatus.DRAFT and not recompute:
        return slip
    if slip and slip.status != PayslipStatus.DRAFT and recompute:
        raise ValueError(
            f"Payslip {slip.pk} is {slip.status}; refusing to recompute a finalized payslip."
        )

    structure = active_structure(employee, period_month)
    if structure is None:
        raise ValueError(
            f"{employee.employee_code} has no salary structure effective on {period_month}."
        )

    days = attendance_breakdown(employee, period_month)
    days_payable = Decimal(days["payable_days"])
    days_total = Decimal(days["total_days"])
    days_unrecorded = days["unrecorded"]
    ratio = (days_payable / days_total) if days_total else Decimal("0")

    gross_full = structure.gross
    gross = (gross_full * ratio).quantize(TWO_PLACES)
    # The flat monthly deductions come out of the wages earned this month and
    # never more. Gross is pro-rated by days worked but the deductions were
    # taken whole, so a short month produced a NEGATIVE net pay — and ate the
    # employee's incentives and expense reimbursements on the way down. The
    # recorded amount is kept in the breakdown so the shortfall is visible.
    deductions_recorded = structure.total_deductions.quantize(TWO_PLACES)
    deductions = min(deductions_recorded, gross)

    # "Not yet paid, OR already linked to THIS slip."
    #
    # Filtering on reimbursed_in__isnull=True alone was correct on the first
    # build and wrong on every rebuild: the first pass links the claims to the
    # slip, so a recompute found none and silently dropped them from net pay
    # while leaving them attached to the slip — money owed, marked reimbursed,
    # and absent from the payslip. Incentives are scoped the same way so an
    # earning belonging to a different slip can never be counted here.
    linked_here = Q(paid_in__isnull=True)
    if slip is not None:
        linked_here |= Q(paid_in=slip)
    incentives = IncentiveEarning.objects.filter(
        linked_here, employee=employee, period_month=period_month,
    )
    incentives_amount = sum((e.amount for e in incentives), Decimal("0.00"))

    claimed_here = Q(reimbursed_in__isnull=True)
    if slip is not None:
        claimed_here |= Q(reimbursed_in=slip)
    reimbursements = ExpenseClaim.objects.filter(
        claimed_here,
        employee=employee,
        status=ApprovalStatus.APPROVED,
        date__gte=period_month,
        date__lt=month_bounds(period_month)[1],
    )
    reimb_amount = sum((e.amount for e in reimbursements), Decimal("0.00"))

    net = (gross + incentives_amount + reimb_amount - deductions).quantize(TWO_PLACES)

    defaults = {
        "payable_days": days_payable,
        "total_days": days_total,
        "gross_earnings": gross,
        "incentives_amount": incentives_amount,
        "reimbursements_amount": reimb_amount,
        "total_deductions": deductions,
        "net_pay": net,
        "status": PayslipStatus.DRAFT,
        "breakdown": {
            "structure_id": structure.pk,
            "lop_ratio": str(ratio.quantize(Decimal("0.0001"))),
            # Paid without an attendance record — see attendance_breakdown().
            "unrecorded_days": days_unrecorded,
            # How the payable days were reached, day by day.
            "attendance": days,
            # Pay lost to absence and unpaid leave (monthly gross − earned).
            "lop_amount": str(gross_full.quantize(TWO_PLACES) - gross),
            # The monthly rates the earned amounts were pro-rated from.
            "earnings_full": {
                "basic": str(structure.basic),
                "hra": str(structure.hra),
                "special_allowance": str(structure.special_allowance),
                "other_allowances": str(structure.other_allowances),
            },
            "earnings": {
                "basic": str((structure.basic * ratio).quantize(TWO_PLACES)),
                "hra": str((structure.hra * ratio).quantize(TWO_PLACES)),
                "special_allowance": str((structure.special_allowance * ratio).quantize(TWO_PLACES)),
                "other_allowances": str((structure.other_allowances * ratio).quantize(TWO_PLACES)),
            },
            "deductions": {
                "pf_employee": str(structure.pf_employee),
                "esi_employee": str(structure.esi_employee),
                "professional_tax": str(structure.professional_tax),
                "tds": str(structure.tds),
            },
            "deductions_recorded": str(deductions_recorded),
            "deductions_capped": deductions < deductions_recorded,
            "statutory_note": (
                "Deductions are the flat amounts recorded on the salary structure; "
                "they are not derived from statutory slabs."
            ),
        },
    }

    slip, _ = Payslip.objects.update_or_create(
        employee=employee, period_month=period_month, defaults=defaults
    )

    # Link the components so they can't be paid twice in another month.
    # Re-read by pk: `incentives`/`reimbursements` are lazy querysets whose Q
    # references the slip that may not have existed when they were built.
    IncentiveEarning.objects.filter(
        pk__in=[e.pk for e in incentives], paid_in__isnull=True
    ).update(paid_in=slip)
    ExpenseClaim.objects.filter(
        pk__in=[e.pk for e in reimbursements], reimbursed_in__isnull=True
    ).update(reimbursed_in=slip)

    return slip


def employees_on_payroll(period_month: date):
    """
    Everyone employed for at least one day of the month.

    Active employees who had joined by the month's end, plus anyone who left
    during it — marking a leaver inactive used to drop their final month's
    salary from the run entirely.
    """
    start, end = month_bounds(period_month)
    return (
        Employee.objects.filter(date_of_joining__lt=end)
        .filter(Q(is_active=True) | Q(date_of_exit__gte=start))
        .exclude(date_of_exit__lt=start)
        .select_related("agent")
    )


def run_payroll(period_month: date) -> dict:
    """Build draft payslips for everyone on the month's payroll. Errors are collected, not raised."""
    period_month = month_start(period_month)
    start, end = month_bounds(period_month)
    built, errors, unrecorded, pending_leave = 0, [], [], []

    for employee in employees_on_payroll(period_month):
        try:
            slip = build_payslip(employee, period_month)
            built += 1
            days = (slip.breakdown or {}).get("unrecorded_days", 0)
            if days:
                unrecorded.append({"employee_code": employee.employee_code,
                                   "name": employee.agent.name, "days": days})
        except Exception as exc:
            errors.append(f"{employee.employee_code}: {exc}")
            logger.error(f"[HRMS] payroll failed for {employee.employee_code}: {exc}")
            continue

        # Leave still waiting for a decision is paid as whatever attendance
        # says (usually absent). Approving it later changes the pay, so HR
        # should decide it before finalizing.
        waiting = LeaveRequest.objects.filter(
            employee=employee, status=ApprovalStatus.PENDING,
            start_date__lt=end, end_date__gte=start,
        ).count()
        if waiting:
            pending_leave.append({"employee_code": employee.employee_code,
                                  "name": employee.agent.name, "requests": waiting})

    return {
        "period": period_month.isoformat(), "payslips": built, "errors": errors,
        # Employees paid for days that have no attendance record, so HR can
        # sync or correct attendance before finalizing.
        "unrecorded": unrecorded,
        "pending_leave": pending_leave,
    }
