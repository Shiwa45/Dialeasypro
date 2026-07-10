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
gross is pro-rated by payable days / total days in the month. Absent days are
unpaid; present, on-leave (paid types), holidays and week-offs are payable.
Half days count as 0.5.
"""
import logging
from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.hrms.constants import ApprovalStatus, AttendanceStatus, PayslipStatus
from apps.hrms.models import (
    Attendance,
    Employee,
    ExpenseClaim,
    IncentiveEarning,
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
    start, end = month_bounds(period_month)
    total = Decimal(monthrange(start.year, start.month)[1])

    rows = Attendance.objects.filter(employee=employee, date__gte=start, date__lt=end)

    payable = Decimal("0")
    counted = 0
    for row in rows:
        counted += 1
        if row.status == AttendanceStatus.HALF_DAY:
            payable += Decimal("0.5")
        elif row.status in AttendanceStatus.PAID_STATUSES:
            payable += Decimal("1")

    # Days with no attendance row at all haven't been synced. Treating them as
    # absent would silently underpay, so credit them and surface the gap.
    missing = total - Decimal(counted)
    if missing > 0:
        logger.warning(
            f"[HRMS] {employee.employee_code} {period_month:%Y-%m}: "
            f"{missing} day(s) without attendance — credited as payable. "
            f"Run `sync_attendance` for the period to correct this."
        )
        payable += missing

    return min(payable, total), total


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

    days_payable, days_total = payable_days(employee, period_month)
    ratio = (days_payable / days_total) if days_total else Decimal("0")

    gross_full = structure.gross
    gross = (gross_full * ratio).quantize(TWO_PLACES)
    deductions = structure.total_deductions.quantize(TWO_PLACES)

    incentives = IncentiveEarning.objects.filter(
        employee=employee, period_month=period_month
    )
    incentives_amount = sum((e.amount for e in incentives), Decimal("0.00"))

    reimbursements = ExpenseClaim.objects.filter(
        employee=employee,
        status=ApprovalStatus.APPROVED,
        reimbursed_in__isnull=True,
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
    incentives.filter(paid_in__isnull=True).update(paid_in=slip)
    reimbursements.update(reimbursed_in=slip)

    return slip


def run_payroll(period_month: date) -> dict:
    """Build draft payslips for every active employee. Errors are collected, not raised."""
    period_month = month_start(period_month)
    built, errors = 0, []

    for employee in Employee.objects.filter(is_active=True).select_related("agent"):
        try:
            build_payslip(employee, period_month)
            built += 1
        except Exception as exc:
            errors.append(f"{employee.employee_code}: {exc}")
            logger.error(f"[HRMS] payroll failed for {employee.employee_code}: {exc}")

    return {"period": period_month.isoformat(), "payslips": built, "errors": errors}
