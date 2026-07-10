"""
TeleCRM Backend — apps/hrms/admin.py

Note: HRMS models live in the TENANT schema, so these appear in the per-tenant
admin, not the public super-admin site.
"""
from django.contrib import admin
from unfold.admin import ModelAdmin

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


@admin.register(Employee)
class EmployeeAdmin(ModelAdmin):
    list_display = ["employee_code", "agent", "designation", "department", "employment_type", "is_active"]
    list_filter = ["is_active", "employment_type", "department"]
    search_fields = ["employee_code", "agent__name", "agent__email"]
    raw_id_fields = ["agent", "reporting_to"]


@admin.register(Attendance)
class AttendanceAdmin(ModelAdmin):
    list_display = ["employee", "date", "status", "source", "worked_hours", "break_seconds"]
    list_filter = ["status", "source", "date"]
    search_fields = ["employee__employee_code", "employee__agent__name"]
    raw_id_fields = ["employee"]
    date_hierarchy = "date"


@admin.register(Holiday)
class HolidayAdmin(ModelAdmin):
    list_display = ["date", "name"]
    ordering = ["date"]


@admin.register(LeaveType)
class LeaveTypeAdmin(ModelAdmin):
    list_display = ["name", "annual_quota_days", "is_paid", "carry_forward", "is_active"]


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(ModelAdmin):
    list_display = ["employee", "leave_type", "year", "allocated_days", "used_days", "remaining_days"]
    list_filter = ["year", "leave_type"]
    raw_id_fields = ["employee"]


@admin.register(LeaveRequest)
class LeaveRequestAdmin(ModelAdmin):
    list_display = ["employee", "leave_type", "start_date", "end_date", "days", "status"]
    list_filter = ["status", "leave_type"]
    raw_id_fields = ["employee", "decided_by"]


@admin.register(ExpenseClaim)
class ExpenseClaimAdmin(ModelAdmin):
    list_display = ["employee", "date", "category", "amount", "status", "reimbursed_in"]
    list_filter = ["status", "category"]
    raw_id_fields = ["employee", "decided_by", "reimbursed_in"]


@admin.register(IncentiveRule)
class IncentiveRuleAdmin(ModelAdmin):
    list_display = ["name", "metric", "per_unit_amount", "min_units", "max_payout", "is_active"]
    list_filter = ["metric", "is_active"]


@admin.register(IncentiveEarning)
class IncentiveEarningAdmin(ModelAdmin):
    list_display = ["employee", "rule", "period_month", "units", "amount", "paid_in"]
    list_filter = ["period_month", "rule"]
    raw_id_fields = ["employee", "rule", "paid_in"]


@admin.register(SalaryStructure)
class SalaryStructureAdmin(ModelAdmin):
    list_display = ["employee", "effective_from", "gross", "total_deductions"]
    raw_id_fields = ["employee"]


@admin.register(Payslip)
class PayslipAdmin(ModelAdmin):
    list_display = [
        "employee", "period_month", "payable_days", "gross_earnings",
        "incentives_amount", "total_deductions", "net_pay", "status",
    ]
    list_filter = ["status", "period_month"]
    raw_id_fields = ["employee"]
    readonly_fields = ["breakdown"]
