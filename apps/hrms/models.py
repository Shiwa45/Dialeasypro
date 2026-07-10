"""
TeleCRM Backend — apps/hrms/models.py

HRMS add-on module. All models live in the TENANT schema (one set per client).

Design notes
------------
* Employee extends Agent 1:1 rather than replacing it. The CRM keeps owning
  identity/auth; HRMS owns employment data. An agent without an Employee row
  simply isn't enrolled in HRMS.
* Attendance is derived from AgentStatusLog (the dialer session already records
  exactly when an agent was online), with manual check-in/out and admin
  correction as overrides. See apps/hrms/services/attendance.py.
* The incentive engine reads CRM outcomes (converted leads, connected calls,
  talk time, deal value) and produces payable earnings — this is the bridge
  between the CRM and payroll.
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.hrms.constants import (
    ApprovalStatus,
    AttendanceSource,
    AttendanceStatus,
    EmploymentType,
    ExpenseCategory,
    IncentiveMetric,
    PayslipStatus,
)


class Employee(TimeStampedModel):
    """Employment record for an Agent. One per enrolled agent."""

    agent = models.OneToOneField(
        "authentication.Agent", on_delete=models.CASCADE, related_name="employee"
    )
    employee_code = models.CharField(max_length=30, unique=True, db_index=True)
    designation = models.CharField(max_length=100, blank=True, default="")
    department = models.CharField(max_length=100, blank=True, default="")
    employment_type = models.CharField(
        max_length=20, choices=EmploymentType.CHOICES, default=EmploymentType.FULL_TIME
    )
    reporting_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports"
    )

    date_of_joining = models.DateField()
    date_of_exit = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    # ---- Statutory / payout identifiers (India) ------------
    pan = models.CharField(max_length=10, blank=True, default="")
    uan = models.CharField(max_length=12, blank=True, default="", help_text="PF Universal Account Number")
    esi_number = models.CharField(max_length=20, blank=True, default="")
    bank_account_number = models.CharField(max_length=30, blank=True, default="")
    bank_ifsc = models.CharField(max_length=11, blank=True, default="")

    class Meta:
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        ordering = ["employee_code"]

    def __str__(self):
        return f"{self.employee_code} — {self.agent.name}"

    @property
    def name(self) -> str:
        return self.agent.name


# ============================================================
# Attendance
# ============================================================

class Holiday(models.Model):
    """A company holiday. Attendance on these dates is paid without work."""

    date = models.DateField(unique=True, db_index=True)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date}: {self.name}"


class Attendance(TimeStampedModel):
    """
    One row per employee per day.

    `worked_seconds` is the authoritative time figure. When source=AUTO it is
    summed from the agent's online AgentStatusLog intervals, so attendance and
    the live monitoring dashboard can never disagree.
    """

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20, choices=AttendanceStatus.CHOICES, default=AttendanceStatus.ABSENT, db_index=True
    )
    source = models.CharField(max_length=10, choices=AttendanceSource.CHOICES, default=AttendanceSource.AUTO)

    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    worked_seconds = models.PositiveIntegerField(default=0)
    break_seconds = models.PositiveIntegerField(default=0)

    note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        unique_together = ("employee", "date")
        ordering = ["-date"]
        indexes = [models.Index(fields=["employee", "date"], name="hrms_att_emp_date_idx")]

    def __str__(self):
        return f"{self.employee.employee_code} {self.date} {self.status}"

    @property
    def worked_hours(self) -> float:
        return round(self.worked_seconds / 3600, 2)


# ============================================================
# Leave
# ============================================================

class LeaveType(TimeStampedModel):
    name = models.CharField(max_length=50, unique=True)
    annual_quota_days = models.DecimalField(
        max_digits=5, decimal_places=1, default=Decimal("0.0"),
        help_text="Days granted per calendar year. 0 = unlimited/unpaid.",
    )
    is_paid = models.BooleanField(default=True)
    carry_forward = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class LeaveBalance(TimeStampedModel):
    """Per-employee, per-type, per-year allocation and usage."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_balances")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name="balances")
    year = models.PositiveIntegerField(db_index=True)
    allocated_days = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("0.0"))
    used_days = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("0.0"))

    class Meta:
        unique_together = ("employee", "leave_type", "year")
        ordering = ["-year", "leave_type__name"]

    def __str__(self):
        return f"{self.employee.employee_code} {self.leave_type.name} {self.year}"

    @property
    def remaining_days(self) -> Decimal:
        return self.allocated_days - self.used_days


class LeaveRequest(TimeStampedModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="requests")
    start_date = models.DateField()
    end_date = models.DateField()
    days = models.DecimalField(
        max_digits=5, decimal_places=1,
        help_text="Working days requested (0.5 for a half day).",
        validators=[MinValueValidator(Decimal("0.5"))],
    )
    reason = models.CharField(max_length=300, blank=True, default="")

    status = models.CharField(
        max_length=15, choices=ApprovalStatus.CHOICES, default=ApprovalStatus.PENDING, db_index=True
    )
    decided_by = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="leave_decisions",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        ordering = ["-start_date"]
        indexes = [models.Index(fields=["employee", "status"], name="hrms_leave_emp_status_idx")]

    def __str__(self):
        return f"{self.employee.employee_code} {self.leave_type.name} {self.start_date}→{self.end_date}"


# ============================================================
# Expenses
# ============================================================

class ExpenseClaim(TimeStampedModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="expense_claims")
    date = models.DateField()
    category = models.CharField(max_length=20, choices=ExpenseCategory.CHOICES)
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    description = models.CharField(max_length=300, blank=True, default="")
    receipt = models.FileField(upload_to="hrms/receipts/", null=True, blank=True)

    status = models.CharField(
        max_length=15, choices=ApprovalStatus.CHOICES, default=ApprovalStatus.PENDING, db_index=True
    )
    decided_by = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="expense_decisions",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=300, blank=True, default="")
    reimbursed_in = models.ForeignKey(
        "hrms.Payslip", on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses"
    )

    class Meta:
        ordering = ["-date"]
        indexes = [models.Index(fields=["employee", "status"], name="hrms_exp_emp_status_idx")]

    def __str__(self):
        return f"{self.employee.employee_code} {self.category} ₹{self.amount}"


# ============================================================
# Incentives — the CRM ↔ payroll bridge
# ============================================================

class IncentiveRule(TimeStampedModel):
    """
    Pays an agent based on a CRM outcome over a month.

    per_unit_amount is money-per-unit for count metrics, and a PERCENTAGE for
    revenue (see IncentiveMetric.PERCENTAGE_METRICS).
    """

    name = models.CharField(max_length=100)
    metric = models.CharField(max_length=30, choices=IncentiveMetric.CHOICES, db_index=True)
    per_unit_amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="₹ per unit; for the revenue metric this is a percentage.",
    )
    min_units = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Threshold that must be met before anything is paid.",
    )
    max_payout = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Optional cap on the payout per period.",
    )
    applies_to_roles = models.JSONField(
        default=list, blank=True,
        help_text="Agent roles this rule covers. Empty = all roles.",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.metric})"

    def compute_payout(self, units: Decimal) -> Decimal:
        """Money earned for `units` of the metric. Never negative."""
        if units < self.min_units:
            return Decimal("0.00")
        if self.metric in IncentiveMetric.PERCENTAGE_METRICS:
            payout = units * self.per_unit_amount / Decimal("100")
        else:
            payout = units * self.per_unit_amount
        if self.max_payout is not None:
            payout = min(payout, self.max_payout)
        return max(Decimal("0.00"), payout.quantize(Decimal("0.01")))


class IncentiveEarning(TimeStampedModel):
    """A computed, idempotent payout for one employee / rule / month."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="incentive_earnings")
    rule = models.ForeignKey(IncentiveRule, on_delete=models.CASCADE, related_name="earnings")
    period_month = models.DateField(
        db_index=True, help_text="First day of the month this covers."
    )
    units = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    paid_in = models.ForeignKey(
        "hrms.Payslip", on_delete=models.SET_NULL, null=True, blank=True, related_name="incentives"
    )

    class Meta:
        unique_together = ("employee", "rule", "period_month")
        ordering = ["-period_month"]

    def __str__(self):
        return f"{self.employee.employee_code} {self.rule.name} {self.period_month:%Y-%m} ₹{self.amount}"


# ============================================================
# Payroll
# ============================================================

class SalaryStructure(TimeStampedModel):
    """
    An employee's salary components, effective from a date. The newest
    structure with effective_from <= period start applies to that payroll run.
    """

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="salary_structures")
    effective_from = models.DateField(db_index=True)

    basic = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    hra = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    special_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    other_allowances = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    # Deductions are stored as flat monthly amounts. Statutory rates vary by
    # wage slab and state, so they are NOT auto-derived here — see the module
    # docstring in services/payroll.py.
    pf_employee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    esi_employee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    professional_tax = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    tds = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        unique_together = ("employee", "effective_from")
        ordering = ["-effective_from"]

    def __str__(self):
        return f"{self.employee.employee_code} from {self.effective_from}"

    @property
    def gross(self) -> Decimal:
        return self.basic + self.hra + self.special_allowance + self.other_allowances

    @property
    def total_deductions(self) -> Decimal:
        return self.pf_employee + self.esi_employee + self.professional_tax + self.tds


class Payslip(TimeStampedModel):
    """A finalized monthly payout for one employee. Amounts are snapshots."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="payslips")
    period_month = models.DateField(db_index=True, help_text="First day of the month.")

    payable_days = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("0.0"))
    total_days = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("0.0"))

    gross_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    incentives_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    reimbursements_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    breakdown = models.JSONField(default=dict, blank=True, help_text="Component-wise snapshot.")
    status = models.CharField(
        max_length=15, choices=PayslipStatus.CHOICES, default=PayslipStatus.DRAFT, db_index=True
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("employee", "period_month")
        ordering = ["-period_month"]

    def __str__(self):
        return f"{self.employee.employee_code} {self.period_month:%Y-%m} ₹{self.net_pay}"

    def finalize(self):
        self.status = PayslipStatus.FINALIZED
        self.finalized_at = timezone.now()
        self.save(update_fields=["status", "finalized_at"])
