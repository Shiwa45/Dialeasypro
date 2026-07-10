"""
TeleCRM Backend — apps/hrms/serializers.py
"""
from datetime import timedelta
from decimal import Decimal

from rest_framework import serializers

from apps.hrms.constants import ApprovalStatus
from apps.hrms.models import (
    Attendance,
    Employee,
    ExpenseClaim,
    Holiday,
    IncentiveEarning,
    IncentiveRule,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    Payslip,
    SalaryStructure,
)


class EmployeeSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="agent.name", read_only=True)
    email = serializers.EmailField(source="agent.email", read_only=True)
    role = serializers.CharField(source="agent.role", read_only=True)
    reporting_to_name = serializers.CharField(source="reporting_to.agent.name", read_only=True, default=None)

    class Meta:
        model = Employee
        fields = [
            "id", "agent", "name", "email", "role", "employee_code", "designation",
            "department", "employment_type", "reporting_to", "reporting_to_name",
            "date_of_joining", "date_of_exit", "is_active",
            "pan", "uan", "esi_number", "bank_account_number", "bank_ifsc",
        ]
        read_only_fields = ["id"]


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


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "date", "name"]


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = ["id", "name", "annual_quota_days", "is_paid", "carry_forward", "is_active"]


class LeaveBalanceSerializer(serializers.ModelSerializer):
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    remaining_days = serializers.DecimalField(max_digits=5, decimal_places=1, read_only=True)

    class Meta:
        model = LeaveBalance
        fields = [
            "id", "employee", "leave_type", "leave_type_name", "year",
            "allocated_days", "used_days", "remaining_days",
        ]


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.agent.name", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id", "employee", "employee_name", "leave_type", "leave_type_name",
            "start_date", "end_date", "days", "reason", "status",
            "decided_by", "decided_at", "decision_note", "created_at",
        ]
        read_only_fields = ["id", "status", "decided_by", "decided_at", "decision_note", "created_at"]

    def validate(self, data):
        start, end = data.get("start_date"), data.get("end_date")
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date cannot precede start date."})

        # Requested days can never exceed the calendar span of the range.
        if start and end and (days := data.get("days")):
            span = Decimal((end - start).days + 1)
            if days > span:
                raise serializers.ValidationError(
                    {"days": f"{days} day(s) requested but the range only spans {span}."}
                )
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
        read_only_fields = [
            "id", "status", "decided_by", "decided_at", "decision_note",
            "reimbursed_in", "created_at",
        ]


class IncentiveRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncentiveRule
        fields = [
            "id", "name", "metric", "per_unit_amount", "min_units",
            "max_payout", "applies_to_roles", "is_active",
        ]


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


class PayslipSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.agent.name", read_only=True)
    employee_code = serializers.CharField(source="employee.employee_code", read_only=True)

    class Meta:
        model = Payslip
        fields = [
            "id", "employee", "employee_code", "employee_name", "period_month",
            "payable_days", "total_days", "gross_earnings", "incentives_amount",
            "reimbursements_amount", "total_deductions", "net_pay", "breakdown",
            "status", "finalized_at", "paid_at",
        ]
        read_only_fields = fields
