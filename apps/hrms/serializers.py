"""
TeleCRM Backend — apps/hrms/serializers.py
"""
import re
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.hrms.constants import ApprovalStatus, IncentiveMetric
from apps.hrms.models import (
    Attendance,
    Employee,
    ExpenseClaim,
    Holiday,
    HrmsPolicy,
    IncentiveEarning,
    IncentiveRule,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    Payslip,
    SalaryStructure,
)

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
ZERO = Decimal("0")


def _digits(value: str, field: str, lo: int, hi: int, label: str) -> str:
    value = re.sub(r"[\s-]", "", value or "")
    if value and not (value.isdigit() and lo <= len(value) <= hi):
        size = f"{lo}" if lo == hi else f"{lo}–{hi}"
        raise serializers.ValidationError({field: f"{label} must be {size} digits."})
    return value


class EmployeeSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="agent.name", read_only=True)
    email = serializers.EmailField(source="agent.email", read_only=True)
    role = serializers.CharField(source="agent.role", read_only=True)
    reporting_to_name = serializers.CharField(source="reporting_to.agent.name", read_only=True, default=None)
    # The CRM login can be switched off while the employee record stays
    # active (and on payroll); the roster flags that so HR can decide.
    login_active = serializers.BooleanField(source="agent.is_active", read_only=True)
    # Spaces and dashes are allowed on input and stripped in validate().
    uan = serializers.CharField(max_length=20, required=False, allow_blank=True)

    class Meta:
        model = Employee
        fields = [
            "id", "agent", "name", "email", "role", "employee_code", "designation",
            "department", "employment_type", "reporting_to", "reporting_to_name",
            "date_of_joining", "date_of_exit", "is_active", "login_active",
            "pan", "uan", "esi_number", "bank_account_number", "bank_ifsc",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {
            "agent": {"error_messages": {"unique": "This user is already enrolled as an employee."}},
        }

    def validate(self, data):
        inst = self.instance
        get = lambda f: data[f] if f in data else getattr(inst, f, None)  # noqa: E731

        if "pan" in data:
            data["pan"] = (data["pan"] or "").strip().upper()
            if data["pan"] and not PAN_RE.match(data["pan"]):
                raise serializers.ValidationError({"pan": "PAN must look like ABCDE1234F."})
        if "bank_ifsc" in data:
            data["bank_ifsc"] = (data["bank_ifsc"] or "").strip().upper()
            if data["bank_ifsc"] and not IFSC_RE.match(data["bank_ifsc"]):
                raise serializers.ValidationError(
                    {"bank_ifsc": "IFSC must be 11 characters, like SBIN0001234."}
                )
        if "uan" in data:
            data["uan"] = _digits(data["uan"], "uan", 12, 12, "UAN")
        if "esi_number" in data:
            data["esi_number"] = _digits(data["esi_number"], "esi_number", 10, 17, "ESI number")
        if "bank_account_number" in data:
            data["bank_account_number"] = _digits(
                data["bank_account_number"], "bank_account_number", 9, 18, "Bank account number"
            )

        joined, left = get("date_of_joining"), get("date_of_exit")
        if joined and left and left < joined:
            raise serializers.ValidationError({"date_of_exit": "Exit date can't be before the joining date."})

        boss = get("reporting_to")
        if boss is not None and inst is not None:
            seen, node = set(), boss
            while node is not None and node.pk not in seen:
                if node.pk == inst.pk:
                    raise serializers.ValidationError(
                        {"reporting_to": "That would make this employee report to themselves."}
                    )
                seen.add(node.pk)
                node = node.reporting_to
        return data


class AttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.agent.name", read_only=True)
    employee_code = serializers.CharField(source="employee.employee_code", read_only=True)
    worked_hours = serializers.FloatField(read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id", "employee", "employee_code", "employee_name", "date", "status",
            "source", "check_in", "check_out", "worked_seconds", "worked_hours",
            "break_seconds", "note",
        ]
        read_only_fields = ["id", "source"]
        # Uniqueness is checked in validate() with a readable message.
        validators = []

    def validate(self, data):
        inst = self.instance
        if inst is not None:
            # A correction fixes a day; it never moves the row to another
            # person or date.
            for field in ("employee", "date"):
                if field in data and data[field] != getattr(inst, field):
                    raise serializers.ValidationError({field: "Can't be changed. Add a new day instead."})
        employee = data.get("employee") or getattr(inst, "employee", None)
        day = data.get("date") or getattr(inst, "date", None)
        if inst is None:
            if employee is None or day is None:
                raise serializers.ValidationError("Employee and date are required.")
            if day > timezone.localdate():
                raise serializers.ValidationError({"date": "Can't add attendance for a future date."})
            if day < employee.date_of_joining:
                raise serializers.ValidationError({"date": "That's before the employee joined."})
            if Attendance.objects.filter(employee=employee, date=day).exists():
                raise serializers.ValidationError(
                    {"date": "This day already has a row; use Correct on it instead."}
                )
        if "worked_seconds" in data and data["worked_seconds"] > 24 * 3600:
            raise serializers.ValidationError({"worked_seconds": "More than 24 hours in a day."})
        # Changing the hours without choosing a status re-derives the status
        # (8 h 20 m used to stay ABSENT).
        if "worked_seconds" in data and "status" not in data:
            from apps.hrms.services.attendance import status_for

            data["status"] = status_for(data["worked_seconds"], day, employee)
        return data


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "date", "name"]


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = ["id", "name", "annual_quota_days", "is_paid", "carry_forward", "is_active"]
        extra_kwargs = {"name": {"validators": []}}

    def validate_annual_quota_days(self, value):
        if value < 0:
            raise serializers.ValidationError("Can't be negative. Use 0 for unlimited.")
        if value > 366:
            raise serializers.ValidationError("More days than a year has.")
        return value

    def validate_name(self, value):
        value = value.strip()
        clash = LeaveType.objects.filter(name__iexact=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        clash = clash.first()
        if clash:
            if not clash.is_active:
                raise serializers.ValidationError(
                    f"'{clash.name}' exists but is switched off. Switch it back on instead."
                )
            raise serializers.ValidationError(f"'{clash.name}' already exists.")
        return value


class LeaveBalanceSerializer(serializers.ModelSerializer):
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    remaining_days = serializers.DecimalField(max_digits=5, decimal_places=1, read_only=True)

    employee_name = serializers.CharField(source="employee.agent.name", read_only=True)
    employee_code = serializers.CharField(source="employee.employee_code", read_only=True)

    class Meta:
        model = LeaveBalance
        fields = [
            "id", "employee", "employee_name", "employee_code", "leave_type", "leave_type_name",
            "year", "allocated_days", "used_days", "remaining_days",
        ]
        # Used days only move by approving or cancelling leave; editable,
        # they could be set to anything (20 of 12, leaving −8).
        read_only_fields = ["id", "used_days"]
        validators = []

    def validate_year(self, value):
        if not 2000 <= value <= 2100:
            raise serializers.ValidationError("Enter a year between 2000 and 2100.")
        return value

    def validate_allocated_days(self, value):
        if value < 0:
            raise serializers.ValidationError("Can't be negative.")
        if value > 366:
            raise serializers.ValidationError("More days than a year has.")
        return value

    def validate(self, data):
        if self.instance is not None and "allocated_days" in data:
            if data["allocated_days"] < self.instance.used_days:
                raise serializers.ValidationError({
                    "allocated_days": f"{self.instance.used_days} day(s) are already used; "
                                      f"allocate at least that.",
                })
        return data


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.agent.name", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id", "employee", "employee_name", "leave_type", "leave_type_name",
            "start_date", "end_date", "days", "half_day", "charged_days", "reason", "status",
            "decided_by", "decided_at", "decision_note", "created_at",
        ]
        # `employee` is set by the view: the requester's own record, or the
        # one HR picked (`employee` in the request body, HR only).
        # `days` is counted by the server from the dates, holidays and
        # week-offs; a value sent by the client is ignored.
        read_only_fields = [
            "id", "employee", "days", "charged_days", "status", "decided_by", "decided_at",
            "decision_note", "created_at",
        ]

    def validate(self, data):
        start, end = data.get("start_date"), data.get("end_date")
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date cannot precede start date."})
        if data.get("half_day") and start and end and start != end:
            raise serializers.ValidationError({"half_day": "A half day must start and end on the same date."})
        return data


class ExpenseClaimSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.agent.name", read_only=True)

    class Meta:
        model = ExpenseClaim
        fields = [
            "id", "employee", "employee_name", "date", "category", "amount",
            "description", "receipt", "status", "decided_by", "decided_at",
            "decision_note", "reimbursed_in", "created_at",
        ]
        # `employee` is the claimant's own record, set by the view — see
        # LeaveRequestSerializer. Required here, it refused every claim.
        read_only_fields = [
            "id", "employee", "status", "decided_by", "decided_at", "decision_note",
            "reimbursed_in", "created_at",
        ]

    def validate(self, data):
        policy = HrmsPolicy.current()
        day = data.get("date") or getattr(self.instance, "date", None)
        amount = data.get("amount") or getattr(self.instance, "amount", None)
        receipt = data.get("receipt") or getattr(self.instance, "receipt", None)
        if day and day > timezone.localdate():
            raise serializers.ValidationError({"date": "An expense can't be dated in the future."})
        if day and day < timezone.localdate() - timedelta(days=366):
            raise serializers.ValidationError({"date": "That's more than a year ago."})
        if amount is not None and amount > policy.expense_max_amount:
            raise serializers.ValidationError(
                {"amount": f"The most one claim can be is ₹{policy.expense_max_amount:,}."}
            )
        threshold = policy.expense_receipt_above
        if threshold is not None and amount is not None and amount > threshold and not receipt:
            raise serializers.ValidationError(
                {"receipt": f"Attach a receipt for claims above ₹{threshold:,}."}
            )
        return data


class IncentiveRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncentiveRule
        fields = [
            "id", "name", "metric", "per_unit_amount", "min_units",
            "max_payout", "applies_to_roles", "is_active",
        ]

    def validate(self, data):
        from apps.core.constants import AgentRole

        get = lambda f: data[f] if f in data else getattr(self.instance, f, None)  # noqa: E731
        for field in ("per_unit_amount", "min_units", "max_payout"):
            value = data.get(field)
            if value is not None and value < 0:
                raise serializers.ValidationError({field: "Can't be negative."})
        metric, rate = get("metric"), get("per_unit_amount")
        if metric in IncentiveMetric.PERCENTAGE_METRICS and rate is not None and rate > 100:
            raise serializers.ValidationError({"per_unit_amount": "A revenue share can't be over 100%."})
        if "applies_to_roles" in data:
            roles = data["applies_to_roles"] or []
            valid = {code for code, _ in AgentRole.CHOICES}
            if not isinstance(roles, list) or any(r not in valid for r in roles):
                bad = [r for r in (roles if isinstance(roles, list) else [roles]) if r not in valid]
                raise serializers.ValidationError(
                    {"applies_to_roles": f"Unknown role(s): {', '.join(map(str, bad))}."}
                )
        return data


class IncentiveEarningSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.agent.name", read_only=True)
    rule_name = serializers.CharField(source="rule.name", read_only=True)
    metric = serializers.CharField(source="rule.metric", read_only=True)

    class Meta:
        model = IncentiveEarning
        fields = [
            "id", "employee", "employee_name", "rule", "rule_name", "metric",
            "period_month", "units", "amount", "paid_in",
        ]


class SalaryStructureSerializer(serializers.ModelSerializer):
    gross = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_deductions = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = SalaryStructure
        fields = [
            "id", "employee", "effective_from", "basic", "hra", "special_allowance",
            "other_allowances", "pf_employee", "esi_employee", "professional_tax",
            "tds", "gross", "total_deductions",
        ]
        validators = []  # (employee, effective_from) is checked in validate()

    _MONEY = ("basic", "hra", "special_allowance", "other_allowances",
              "pf_employee", "esi_employee", "professional_tax", "tds")

    def validate(self, data):
        for field in self._MONEY:
            if field in data and data[field] < 0:
                raise serializers.ValidationError({field: "Can't be negative."})
        get = lambda f: data[f] if f in data else getattr(self.instance, f, ZERO)  # noqa: E731
        gross = sum((get(f) for f in self._MONEY[:4]), ZERO)
        deductions = sum((get(f) for f in self._MONEY[4:]), ZERO)
        if gross <= 0:
            raise serializers.ValidationError({"basic": "Enter the salary (gross can't be ₹0)."})
        if deductions > gross:
            raise serializers.ValidationError(
                {"tds": f"Deductions (₹{deductions:,}) are more than the gross salary (₹{gross:,})."}
            )
        employee = get("employee")
        start = get("effective_from")
        if employee and start:
            clash = SalaryStructure.objects.filter(employee=employee, effective_from=start)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {"effective_from": "There is already a structure from this date. Edit that one."}
                )
        return data


class PayslipSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.agent.name", read_only=True)
    employee_code = serializers.CharField(source="employee.employee_code", read_only=True)

    # A payslip is a document an employee keeps and hands to a bank or a
    # landlord. Designation, department, joining date and PAN are what makes
    # it one; without them the UI could only print a name and a number.
    designation = serializers.CharField(source="employee.designation", read_only=True)
    department = serializers.CharField(source="employee.department", read_only=True)
    date_of_joining = serializers.DateField(source="employee.date_of_joining", read_only=True)
    pan = serializers.CharField(source="employee.pan", read_only=True)
    uan = serializers.CharField(source="employee.uan", read_only=True)
    bank_account_masked = serializers.SerializerMethodField()
    bank_ifsc = serializers.CharField(source="employee.bank_ifsc", read_only=True)

    class Meta:
        model = Payslip
        fields = [
            "id", "employee", "employee_code", "employee_name", "period_month",
            "payable_days", "total_days", "gross_earnings", "incentives_amount",
            "reimbursements_amount", "total_deductions", "net_pay", "breakdown",
            "status", "finalized_at", "paid_at",
            "designation", "department", "date_of_joining", "pan", "uan",
            "bank_account_masked", "bank_ifsc",
        ]
        read_only_fields = fields

    def get_bank_account_masked(self, obj) -> str:
        """Last four digits only. Payroll staff read this list too, and the
        full account number is not needed to recognise which account was
        paid."""
        number = (obj.employee.bank_account_number or "").strip()
        if not number:
            return ""
        return "XXXX" + number[-4:] if len(number) > 4 else number


class HrmsPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = HrmsPolicy
        fields = ["full_day_hours", "half_day_hours", "expense_max_amount", "expense_receipt_above"]

    def validate(self, data):
        get = lambda f: data[f] if f in data else getattr(self.instance, f, None)  # noqa: E731
        full, half = get("full_day_hours"), get("half_day_hours")
        if full is not None and full > 24:
            raise serializers.ValidationError({"full_day_hours": "A day has 24 hours."})
        if full is not None and half is not None and half >= full:
            raise serializers.ValidationError(
                {"half_day_hours": "Must be less than the hours for a full day."}
            )
        if (amt := data.get("expense_max_amount")) is not None and amt <= 0:
            raise serializers.ValidationError({"expense_max_amount": "Must be more than ₹0."})
        if (amt := data.get("expense_receipt_above")) is not None and amt < 0:
            raise serializers.ValidationError({"expense_receipt_above": "Can't be negative."})
        return data
