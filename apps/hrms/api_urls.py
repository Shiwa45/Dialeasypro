"""
TeleCRM Backend — apps/hrms/api_urls.py
Mounted at: /api/v1/hrms/
"""
from django.urls import path, re_path

from apps.hrms.views import (
    AttendanceDetailView,
    AttendanceListView,
    AttendanceSyncView,
    BulkAllocateLeaveView,
    CheckInView,
    CheckOutView,
    EmployeeDetailView,
    EmployeeListCreateView,
    ExpenseClaimListCreateView,
    ExpenseDecisionView,
    HolidayDetailView,
    HolidayListCreateView,
    HRMSDashboardView,
    IncentiveComputeView,
    IncentiveEarningListView,
    IncentiveRuleDetailView,
    IncentiveRuleListCreateView,
    LeaveBalanceListView,
    LeaveBalanceManageView,
    LeaveDecisionView,
    LeaveRequestListCreateView,
    LeaveTypeDetailView,
    LeaveTypeListCreateView,
    MyEmployeeView,
    PayrollRunView,
    PayslipDetailView,
    PayslipFinalizeView,
    PayslipListView,
    PayslipMarkPaidView,
    SalaryStructureListCreateView,
)

urlpatterns = [
    # Dashboard
    path("dashboard/", HRMSDashboardView.as_view(), name="api_hrms_dashboard"),

    # Employees
    path("me/", MyEmployeeView.as_view(), name="api_hrms_me"),
    path("employees/", EmployeeListCreateView.as_view(), name="api_hrms_employees"),
    path("employees/<int:pk>/", EmployeeDetailView.as_view(), name="api_hrms_employee_detail"),

    # Attendance
    path("attendance/", AttendanceListView.as_view(), name="api_hrms_attendance"),
    path("attendance/check-in/", CheckInView.as_view(), name="api_hrms_check_in"),
    path("attendance/check-out/", CheckOutView.as_view(), name="api_hrms_check_out"),
    path("attendance/sync/", AttendanceSyncView.as_view(), name="api_hrms_attendance_sync"),
    path("attendance/<int:pk>/", AttendanceDetailView.as_view(), name="api_hrms_attendance_detail"),
    path("holidays/", HolidayListCreateView.as_view(), name="api_hrms_holidays"),
    path("holidays/<int:pk>/", HolidayDetailView.as_view(), name="api_hrms_holiday_detail"),

    # Leave
    path("leave-types/", LeaveTypeListCreateView.as_view(), name="api_hrms_leave_types"),
    path("leave-types/<int:pk>/", LeaveTypeDetailView.as_view(), name="api_hrms_leave_type_detail"),
    path("leave-balances/", LeaveBalanceListView.as_view(), name="api_hrms_leave_balances"),
    path("leave-balances/allocate/", LeaveBalanceManageView.as_view(), name="api_hrms_leave_balance_allocate"),
    path("leave-balances/bulk-allocate/", BulkAllocateLeaveView.as_view(), name="api_hrms_leave_bulk_allocate"),
    path("leave-balances/<int:pk>/", LeaveBalanceManageView.as_view(), name="api_hrms_leave_balance_detail"),
    path("leave/", LeaveRequestListCreateView.as_view(), name="api_hrms_leave"),
    re_path(
        r"^leave/(?P<pk>\d+)/(?P<action>approve|reject|cancel)/$",
        LeaveDecisionView.as_view(), name="api_hrms_leave_decision",
    ),

    # Expenses
    path("expenses/", ExpenseClaimListCreateView.as_view(), name="api_hrms_expenses"),
    re_path(
        r"^expenses/(?P<pk>\d+)/(?P<action>approve|reject)/$",
        ExpenseDecisionView.as_view(), name="api_hrms_expense_decision",
    ),

    # Incentives
    path("incentive-rules/", IncentiveRuleListCreateView.as_view(), name="api_hrms_incentive_rules"),
    path("incentive-rules/<int:pk>/", IncentiveRuleDetailView.as_view(), name="api_hrms_incentive_rule_detail"),
    path("incentives/", IncentiveEarningListView.as_view(), name="api_hrms_incentives"),
    path("incentives/compute/", IncentiveComputeView.as_view(), name="api_hrms_incentive_compute"),

    # Payroll
    path("salary-structures/", SalaryStructureListCreateView.as_view(), name="api_hrms_salary_structures"),
    path("payslips/", PayslipListView.as_view(), name="api_hrms_payslips"),
    path("payslips/<int:pk>/", PayslipDetailView.as_view(), name="api_hrms_payslip_detail"),
    path("payslips/<int:pk>/finalize/", PayslipFinalizeView.as_view(), name="api_hrms_payslip_finalize"),
    path("payslips/<int:pk>/mark-paid/", PayslipMarkPaidView.as_view(), name="api_hrms_payslip_mark_paid"),
    path("payroll/run/", PayrollRunView.as_view(), name="api_hrms_payroll_run"),
]
