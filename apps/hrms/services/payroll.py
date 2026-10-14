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
  neither   before the date of joining or after the date of exit, and days
            after the run date ("upcoming")

Each day is paid at the salary structure in force that day.

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


def _structure_picker(employee: Employee):
    """
    A function day -> SalaryStructure | None, from one query.

    Each day is paid at the structure in force that day, so a raise from the
    15th pays the new rate from the 15th. Days before the first structure are
    paid at that first structure: it was usually entered a few days after the
    joining date, and refusing the whole month (the old behaviour) left a new
    joiner's first month unpayable.
    """
    structures = list(
        SalaryStructure.objects.filter(employee=employee).order_by("effective_from")
    )

    def pick(day: date) -> SalaryStructure | None:
        if not structures:
            return None
        chosen = structures[0]
        for s in structures:
            if s.effective_from <= day:
                chosen = s
            else:
                break
        return chosen

    return pick


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

# Bucket -> (paid share of the day, docked share of the day, share worked).
_WEIGHTS = {
    "present": (1, 0, 1),
    "half_day": (Decimal("0.5"), Decimal("0.5"), Decimal("0.5")),
    "paid_leave": (1, 0, 0),
    "unpaid_leave": (0, 1, 0),
    "absent": (0, 1, 0),
    "holiday": (1, 0, 0),
    "week_off": (1, 0, 0),
    "unrecorded": (1, 0, 0),
    "not_employed": (0, 0, 0),
    "upcoming": (0, 0, 0),
}

HALF = Decimal("0.5")


def _approved_leave_days(employee: Employee, start: date, end: date) -> dict:
    """{date: (leave type name, is_paid, half_day)} for approved leave in [start, end)."""
    days = {}
    leaves = LeaveRequest.objects.filter(
        employee=employee, status=ApprovalStatus.APPROVED,
        start_date__lt=end, end_date__gte=start,
    ).select_related("leave_type")
    for leave in leaves:
        day = max(leave.start_date, start)
        last = min(leave.end_date, end - timedelta(days=1))
        while day <= last:
            days[day] = (leave.leave_type.name, leave.leave_type.is_paid, leave.half_day)
            day += timedelta(days=1)
    return days


def _classify_days(employee: Employee, period_month: date, today: date | None = None):
    """
    Every day of the month with its bucket and weights.

    Returns (counts, paid_leave_by_type, days) where days is a list of
    (date, bucket, paid_share, docked_share, worked_share).
    """
    from apps.hrms.services.attendance import day_off_status

    today = today or timezone.localdate()
    start, end = month_bounds(period_month)
    rows = {
        r.date: r
        for r in Attendance.objects.filter(employee=employee, date__gte=start, date__lt=end)
    }
    leave_days = _approved_leave_days(employee, start, end)
    holidays = set(Holiday.objects.filter(date__gte=start, date__lt=end).values_list("date", flat=True))

    counts = {
        "present": 0, "half_day": 0, "paid_leave": 0, "unpaid_leave": 0, "absent": 0,
        "holiday": 0, "week_off": 0, "unrecorded": 0, "not_employed": 0,
        "upcoming": 0, "half_day_leave": 0,
    }
    paid_leave_by_type: dict[str, float] = {}
    out = []

    day = start
    while day < end:
        row = rows.get(day)
        leave_name, leave_paid, leave_half = leave_days.get(day, (None, None, False))
        status = row.status if row else None
        off = day_off_status(day, employee, holidays=holidays)

        if day < employee.date_of_joining or (employee.date_of_exit and day > employee.date_of_exit):
            bucket = "not_employed"
        elif day > today:
            # Still to come. Paying these as "no record" paid a whole month
            # to someone the payroll was run for on the 9th.
            bucket = "upcoming"
        elif leave_half and leave_paid is not None and not off:
            # Half-day leave: the attendance row is left as worked, and the
            # leave covers the other half.
            bucket = "half_day_leave"
        elif row is None:
            # No record: a day off is a day off, approved leave is leave, and
            # anything else is an unsynced working day.
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

        if bucket == "half_day_leave":
            # What the row says was worked: a present day stays whole, a
            # half day or a missing row is the other half, absent is none.
            if row is None or status == AttendanceStatus.HALF_DAY:
                worked = HALF
            elif status == AttendanceStatus.PRESENT:
                worked = Decimal(1)
            else:
                worked = Decimal(0)
            if leave_paid:
                paid = min(Decimal(1), worked + HALF)
                name = leave_name or "Leave"
                paid_leave_by_type[name] = paid_leave_by_type.get(name, 0) + 0.5
            else:
                paid = worked
            weights = (paid, Decimal(1) - paid, worked)
        else:
            weights = tuple(Decimal(w) for w in _WEIGHTS[bucket])
            if bucket == "paid_leave":
                name = leave_name or "Leave"
                paid_leave_by_type[name] = paid_leave_by_type.get(name, 0) + 1

        counts[bucket] += 1
        out.append((day, bucket, *weights))
        day += timedelta(days=1)

    return counts, paid_leave_by_type, out


def attendance_breakdown(employee: Employee, period_month: date, today: date | None = None) -> dict:
    """
    Every day of the month, counted once, for the payslip.

    Unpaid leave is stored as an ABSENT attendance row (so it is docked); the
    approved leave requests tell it apart from a plain absence here.

    Days with no attendance row are PAID, deliberately: a missing row means
    the day was never synced, and docking pay for our own gap is worse than
    paying for it. A missing row on a holiday or week-off is simply that day
    off; only missing WORKING days are reported as unrecorded, so HR can sync
    or correct them before finalizing.

    Days after today are "upcoming" and neither paid nor docked: a payroll run
    in the middle of a month is a preview of what has been earned so far.

    Days before the date of joining or after the date of exit are not paid.
    """
    counts, paid_leave_by_type, days = _classify_days(employee, period_month, today)
    start, _ = month_bounds(period_month)
    total = monthrange(start.year, start.month)[1]

    payable = sum((d[2] for d in days), Decimal(0))
    lop = sum((d[3] for d in days), Decimal(0))
    worked = sum((d[4] for d in days), Decimal(0))
    employed = total - counts["not_employed"]

    if counts["unrecorded"]:
        logger.warning(
            f"[HRMS] {employee.employee_code} {period_month:%Y-%m}: "
            f"{counts['unrecorded']} working day(s) without attendance — credited as payable. "
            f"Run `sync_attendance` for the period to correct this."
        )

    def fmt(d: Decimal) -> str:
        return str(int(d)) if d == d.to_integral_value() else str(d.quantize(Decimal("0.1")))

    return {
        **counts,
        "total_days": total,
        "employed_days": employed,
        "working_days": employed - counts["holiday"] - counts["week_off"] - counts["upcoming"],
        "days_worked": fmt(worked),
        "paid_leave_by_type": paid_leave_by_type,
        "lop_days": fmt(lop),
        "payable_days": fmt(payable),
    }


def attendance_summary(employee: Employee, period_month: date) -> tuple[Decimal, Decimal, int]:
    """(payable_days, total_days_in_month, unrecorded_working_days)."""
    b = attendance_breakdown(employee, period_month)
    return Decimal(b["payable_days"]), Decimal(b["total_days"]), b["unrecorded"]


class NoSalaryStructure(ValueError):
    """The employee has no salary structure at all."""


_EARNING_FIELDS = ("basic", "hra", "special_allowance", "other_allowances")
_DEDUCTION_FIELDS = ("pf_employee", "esi_employee", "professional_tax", "tds")


@transaction.atomic
def build_payslip(employee: Employee, period_month: date, *, recompute: bool = False,
                  today: date | None = None) -> Payslip:
    """
    Create or refresh a DRAFT payslip. Finalized/paid payslips are never
    modified — reopen the slip deliberately first.
    """
    from apps.hrms.services.incentives import compute_earnings_for

    period_month = month_start(period_month)
    start, end = month_bounds(period_month)

    slip = Payslip.objects.filter(employee=employee, period_month=period_month).first()
    if slip and slip.status != PayslipStatus.DRAFT and not recompute:
        return slip
    if slip and slip.status != PayslipStatus.DRAFT and recompute:
        raise ValueError(
            f"Payslip {slip.pk} is {slip.status}; refusing to recompute a finalized payslip."
        )

    pick = _structure_picker(employee)
    if pick(start) is None:
        raise NoSalaryStructure(
            f"{employee.employee_code} has no salary structure. Add one in Settings → Salary structures."
        )

    counts, paid_leave_by_type, day_rows = _classify_days(employee, period_month, today)
    days = attendance_breakdown(employee, period_month, today)
    days_payable = Decimal(days["payable_days"])
    days_total = Decimal(days["total_days"])
    days_unrecorded = days["unrecorded"]
    ratio = (days_payable / days_total) if days_total else Decimal("0")

    # Group the paid and docked shares by the structure in force each day.
    per_structure: dict[int, dict] = {}
    for day, bucket, paid_w, lop_w, _ in day_rows:
        s = pick(day)
        entry = per_structure.setdefault(
            s.pk, {"structure": s, "paid": Decimal(0), "lop": Decimal(0), "days": 0}
        )
        entry["paid"] += paid_w
        entry["lop"] += lop_w
        if bucket not in ("not_employed",):
            entry["days"] += 1

    earnings = {f: Decimal(0) for f in _EARNING_FIELDS}
    lop_amount = Decimal(0)
    for entry in per_structure.values():
        s = entry["structure"]
        for f in _EARNING_FIELDS:
            earnings[f] += getattr(s, f) * entry["paid"] / days_total
        lop_amount += s.gross * entry["lop"] / days_total
    earnings = {f: v.quantize(TWO_PLACES) for f, v in earnings.items()}
    gross = sum(earnings.values(), Decimal(0)).quantize(TWO_PLACES)

    # Rates shown on the slip and deductions: the structure in force on the
    # last day employed this month.
    last_day = min(end - timedelta(days=1), employee.date_of_exit or end)
    structure = pick(last_day)
    used = [e for e in per_structure.values() if e["days"]]
    structure_ids = sorted({e["structure"].pk for e in used} | {structure.pk})

    # The flat monthly deductions come out of the wages earned this month and
    # never more. The recorded amount is kept in the breakdown so the
    # shortfall is visible.
    deductions_recorded = structure.total_deductions.quantize(TWO_PLACES)
    deductions = min(deductions_recorded, gross)

    # Incentives are recomputed now, so a draft built earlier in the month
    # never freezes them: an earning linked to a DRAFT slip is still live.
    compute_earnings_for(employee, period_month)

    # "Not yet paid, OR already linked to THIS slip."
    linked_here = Q(paid_in__isnull=True)
    if slip is not None:
        linked_here |= Q(paid_in=slip)
    incentives = list(IncentiveEarning.objects.filter(
        linked_here, employee=employee, period_month=period_month, rule__is_active=True,
    ))
    incentives_amount = sum((e.amount for e in incentives), Decimal("0.00"))

    # Approved claims dated up to the month's end that no other slip has
    # paid. Claims dated in an earlier month count too: one approved after
    # that month was finalized used to stay unpaid forever.
    claimed_here = Q(reimbursed_in__isnull=True)
    if slip is not None:
        claimed_here |= Q(reimbursed_in=slip)
    reimbursements = list(ExpenseClaim.objects.filter(
        claimed_here,
        employee=employee,
        status=ApprovalStatus.APPROVED,
        date__lt=end,
    ))
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
            "structure_ids": structure_ids,
            "structures": [
                {
                    "id": e["structure"].pk,
                    "effective_from": e["structure"].effective_from.isoformat(),
                    "gross": str(e["structure"].gross),
                    "days": e["days"],
                }
                for e in sorted(used, key=lambda x: x["structure"].effective_from)
            ],
            "lop_ratio": str(ratio.quantize(Decimal("0.0001"))),
            # Paid without an attendance record — see attendance_breakdown().
            "unrecorded_days": days_unrecorded,
            # Days after the run date: not paid yet. A slip with any of these
            # can't be finalized; run payroll again once the month is over.
            "upcoming_days": days["upcoming"],
            "built_on": (today or timezone.localdate()).isoformat(),
            # How the payable days were reached, day by day.
            "attendance": days,
            # Pay lost to absence and unpaid leave.
            "lop_amount": str(lop_amount.quantize(TWO_PLACES)),
            # The monthly rates the earned amounts were pro-rated from.
            "earnings_full": {f: str(getattr(structure, f)) for f in _EARNING_FIELDS},
            "earnings": {f: str(v) for f, v in earnings.items()},
            "deductions": {f: str(getattr(structure, f)) for f in _DEDUCTION_FIELDS},
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

    # Link the components so they can't be paid twice in another month, and
    # release anything this slip no longer includes.
    IncentiveEarning.objects.filter(paid_in=slip).exclude(
        pk__in=[e.pk for e in incentives]
    ).update(paid_in=None)
    IncentiveEarning.objects.filter(
        pk__in=[e.pk for e in incentives], paid_in__isnull=True
    ).update(paid_in=slip)
    ExpenseClaim.objects.filter(reimbursed_in=slip).exclude(
        pk__in=[e.pk for e in reimbursements]
    ).update(reimbursed_in=None)
    ExpenseClaim.objects.filter(
        pk__in=[e.pk for e in reimbursements], reimbursed_in__isnull=True
    ).update(reimbursed_in=slip)

    return slip


def finalize_blockers(slip: Payslip, today: date | None = None) -> str | None:
    """Why this slip can't be finalized yet, or None."""
    today = today or timezone.localdate()
    if slip.status != PayslipStatus.DRAFT:
        return f"This payslip is already {slip.status}."
    _, end = month_bounds(slip.period_month)
    last = end - timedelta(days=1)
    if today < last:
        return (
            f"{slip.period_month:%B %Y} isn't over yet. Run payroll again on or after "
            f"{last:%d %b} and finalize then."
        )
    upcoming = (slip.breakdown or {}).get("upcoming_days", 0)
    if upcoming:
        return (
            f"This draft was built before the month ended and leaves {upcoming} day(s) unpaid. "
            f"Run payroll again, then finalize."
        )
    return None


def finalized_month_for(employee: Employee, day: date) -> Payslip | None:
    """The finalized or paid payslip covering this day, if any."""
    return (
        Payslip.objects.filter(employee=employee, period_month=month_start(day))
        .exclude(status=PayslipStatus.DRAFT)
        .first()
    )


def locked_days(employee: Employee, start: date, end: date) -> list[date]:
    """Months in [start, end] that already have a finalized or paid payslip (first days)."""
    months = set()
    day = month_start(start)
    while day <= end:
        months.add(day)
        day = month_bounds(day)[1]
    return sorted(
        Payslip.objects.filter(employee=employee, period_month__in=months)
        .exclude(status=PayslipStatus.DRAFT)
        .values_list("period_month", flat=True)
    )


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


def run_payroll(period_month: date, today: date | None = None) -> dict:
    """Build draft payslips for everyone on the month's payroll. Errors are collected, not raised."""
    period_month = month_start(period_month)
    start, end = month_bounds(period_month)
    built, errors, unrecorded, pending_leave, missing = 0, [], [], [], []
    upcoming = 0

    for employee in employees_on_payroll(period_month):
        try:
            slip = build_payslip(employee, period_month, today=today)
            built += 1
            days = (slip.breakdown or {}).get("unrecorded_days", 0)
            if days:
                unrecorded.append({"employee_code": employee.employee_code,
                                   "name": employee.agent.name, "days": days})
            upcoming = max(upcoming, (slip.breakdown or {}).get("upcoming_days", 0))
        except NoSalaryStructure:
            # Not an error in the run: nobody has set this person's pay yet.
            # Listed on its own so HR knows exactly what to add.
            missing.append({"employee_code": employee.employee_code,
                            "name": employee.agent.name, "is_active": employee.is_active})
            continue
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
        # Employees with no salary structure at all — no payslip was made.
        "missing_structure": missing,
        # Days of the month still to come (a mid-month run is a preview).
        "upcoming_days": upcoming,
    }
