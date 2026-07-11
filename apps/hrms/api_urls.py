"""
TeleCRM Backend — apps/hrms/api_urls.py
Mounted at: /api/v1/hrms/
"""
from django.urls import path, re_path

from apps.hrms.views import (
    AttendanceListView,
    AttendanceSyncView,
    CheckInView,
    CheckOutView,
    EmployeeDetailView,
    EmployeeListCreateView,
    ExpenseClaimListCreateView,
    ExpenseDecisionView,
    HolidayDetailView,
    HolidayListCreateView,
    IncentiveComputeView,
    IncentiveEarningListView,
    IncentiveRuleDetailView,
    IncentiveRuleListCreateView,
    LeaveBalanceListView,
    LeaveDecisionView,
    LeaveRequestListCreateView,
    LeaveTypeDetailView,
    LeaveTypeListCreateView,
    MyEmployeeView,
    PayrollRunView,
    PayslipFinalizeView,
    PayslipListView,
    SalaryStructureListCreateView,
)

urlpatterns = [
    # Employees
    path("me/", MyEmployeeView.as_view(), name="api_hrms_me"),
    path("employees/", EmployeeListCreateView.as_view(), name="api_hrms_employees"),
    path("employees/<int:pk>/", EmployeeDetailView.as_view(), name="api_hrms_employee_detail"),

    # Attendance
    path("attendance/", AttendanceListView.as_view(), name="api_hrms_attendance"),
    path("attendance/check-in/", CheckInView.as_view(), name="api_hrms_check_in"),
    path("attendance/check-out/", CheckOutView.as_view(), name="api_hrms_check_out"),
    path("attendance/sync/", AttendanceSyncView.as_view(), name="api_hrms_attendance_sync"),
    path("holidays/", HolidayListCreateView.as_view(), name="api_hrms_holidays"),
    path("holidays/<int:pk>/", HolidayDetailView.as_view(), name="api_hrms_holiday_detail"),

    # Leave
    path("leave-types/", LeaveTypeListCreateView.as_view(), name="api_hrms_leave_types"),
    path("leave-types/<int:pk>/", LeaveTypeDetailView.as_view(), name="api_hrms_leave_type_detail"),
    path("leave-balances/", LeaveBalanceListView.as_view(), name="api_hrms_leave_balances"),
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
    path("payslips/<int:pk>/finalize/", PayslipFinalizeView.as_view(), name="api_hrms_payslip_finalize"),
    path("payroll/run/", PayrollRunView.as_view(), name="api_hrms_payroll_run"),
]
