"""
TeleCRM Backend — apps/hrms/views.py

HRMS API. Every endpoint is plan-gated on its HRMS feature key, so the module
is only reachable for tenants who bought it (see ModuleKey.HRMS).

Scoping: employees read/write their own rows; managers and admins see the whole
org. Payroll is admin-only.
"""
import logging
from datetime import date, datetime

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import (
    HasFeatureAccess,
    IsAuthenticatedAgent,
    IsManagerOrAdmin,
    IsTenantAdmin,
)
from apps.core.constants import FeatureKey
from apps.core.pagination import StandardResultsSetPagination
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
from apps.hrms.permissions import employee_for, is_hr_manager, scope_to_visible
from apps.hrms.serializers import (
    AttendanceSerializer,
    EmployeeSerializer,
    ExpenseClaimSerializer,
    HolidaySerializer,
    IncentiveEarningSerializer,
    IncentiveRuleSerializer,
    LeaveBalanceSerializer,
    LeaveRequestSerializer,
    LeaveTypeSerializer,
    PayslipSerializer,
    SalaryStructureSerializer,
)
from apps.hrms.services import leave as leave_svc

logger = logging.getLogger(__name__)


def _parse_month(value, default=None) -> date:
    """Accept 'YYYY-MM' or 'YYYY-MM-DD'; return the first of that month."""
    if not value:
        return (default or timezone.localdate()).replace(day=1)
    for fmt in ("%Y-%m", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().replace(day=1)
        except ValueError:
            continue
    raise ValueError(f"Invalid month '{value}'. Use YYYY-MM.")


def _require_employee(request) -> Employee:
    employee = employee_for(request.user)
    if employee is None:
        raise ValueError("You are not enrolled in HRMS. Ask your admin to add an employee record.")
    return employee


# ============================================================
# Employees
# ============================================================

class EmployeeListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/hrms/employees/ — admin manages the employee roster."""

    serializer_class = EmployeeSerializer
    pagination_class = StandardResultsSetPagination
    required_feature = FeatureKey.HRMS_ATTENDANCE

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsTenantAdmin(), HasFeatureAccess()]
        return [IsAuthenticatedAgent(), HasFeatureAccess()]

    def get_queryset(self):
        qs = Employee.objects.select_related("agent", "reporting_to__agent")
        if not is_hr_manager(self.request.user):
            qs = qs.filter(agent=self.request.user)
        if self.request.query_params.get("active") == "true":
            qs = qs.filter(is_active=True)
        return qs


class EmployeeDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EmployeeSerializer
    permission_classes = [IsTenantAdmin, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_ATTENDANCE

    def get_queryset(self):
        return Employee.objects.select_related("agent")


class MyEmployeeView(APIView):
    """GET /api/v1/hrms/me/ — the caller's own employment record."""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_ATTENDANCE

    def get(self, request):
        employee = employee_for(request.user)
        if employee is None:
            return Response({"enrolled": False}, status=status.HTTP_200_OK)
        return Response({"enrolled": True, **EmployeeSerializer(employee).data})


# ============================================================
# Attendance
# ============================================================

class AttendanceListView(generics.ListAPIView):
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Attendance.objects.select_related("employee__agent")
        qs = scope_to_visible(qs, self.request.user)
        p = self.request.query_params
        if employee_id := p.get("employee"):
            qs = qs.filter(employee_id=employee_id)
        if date_from := p.get("date_from"):
            qs = qs.filter(date__gte=date_from)
        if date_to := p.get("date_to"):
            qs = qs.filter(date__lte=date_to)
        if status_filter := p.get("status"):
            qs = qs.filter(status=status_filter)
        return qs.order_by("-date")


class CheckInView(APIView):
    """POST /api/v1/hrms/attendance/check-in/"""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_ATTENDANCE

    def post(self, request):
        from apps.hrms.services.attendance import mark_check_in

        try:
            employee = _require_employee(request)
        except ValueError as exc:
            return Response({"error": "not_enrolled", "message": str(exc)}, status=400)
        return Response(AttendanceSerializer(mark_check_in(employee)).data)


class CheckOutView(APIView):
    """POST /api/v1/hrms/attendance/check-out/"""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_ATTENDANCE

    def post(self, request):
        from apps.hrms.services.attendance import mark_check_out

        try:
            employee = _require_employee(request)
        except ValueError as exc:
            return Response({"error": "not_enrolled", "message": str(exc)}, status=400)
        return Response(AttendanceSerializer(mark_check_out(employee)).data)


class AttendanceSyncView(APIView):
    """
    POST /api/v1/hrms/attendance/sync/ {"date": "YYYY-MM-DD"}
    Recompute attendance from dialer session logs for a date (admin).
    """

    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_ATTENDANCE

    def post(self, request):
        from apps.hrms.services.attendance import sync_attendance_for_date

        raw = request.data.get("date")
        try:
            day = datetime.strptime(raw, "%Y-%m-%d").date() if raw else timezone.localdate()
        except ValueError:
            return Response({"error": "invalid_date", "message": "Use YYYY-MM-DD."}, status=400)

        written = sync_attendance_for_date(day)
        return Response({"date": day.isoformat(), "rows_written": written})


class HolidayListCreateView(generics.ListCreateAPIView):
    serializer_class = HolidaySerializer
    queryset = Holiday.objects.all()
    pagination_class = None
    required_feature = FeatureKey.HRMS_ATTENDANCE

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsTenantAdmin(), HasFeatureAccess()]
        return [IsAuthenticatedAgent(), HasFeatureAccess()]


# ============================================================
# Leave
# ============================================================

class LeaveTypeListCreateView(generics.ListCreateAPIView):
    serializer_class = LeaveTypeSerializer
    queryset = LeaveType.objects.filter(is_active=True)
    pagination_class = None
    required_feature = FeatureKey.HRMS_LEAVE

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsTenantAdmin(), HasFeatureAccess()]
        return [IsAuthenticatedAgent(), HasFeatureAccess()]


class LeaveBalanceListView(generics.ListAPIView):
    serializer_class = LeaveBalanceSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_LEAVE
    pagination_class = None

    def get_queryset(self):
        qs = LeaveBalance.objects.select_related("leave_type", "employee__agent")
        qs = scope_to_visible(qs, self.request.user)
        year = self.request.query_params.get("year") or timezone.localdate().year
        return qs.filter(year=year)


class LeaveRequestListCreateView(generics.ListCreateAPIView):
    serializer_class = LeaveRequestSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_LEAVE
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = LeaveRequest.objects.select_related("employee__agent", "leave_type")
        qs = scope_to_visible(qs, self.request.user)
        if status_filter := self.request.query_params.get("status"):
            qs = qs.filter(status=status_filter)
        return qs

    def perform_create(self, serializer):
        employee = _require_employee(self.request)
        leave_type = serializer.validated_data["leave_type"]
        days = serializer.validated_data["days"]
        start = serializer.validated_data["start_date"]
        end = serializer.validated_data["end_date"]

        if leave_svc.overlapping_requests(employee, start, end).exists():
            raise ValidationError(
                {"start_date": "You already have a pending or approved leave overlapping these dates."}
            )
        if not leave_svc.has_sufficient_balance(employee, leave_type, start.year, days):
            balance = leave_svc.balance_for(employee, leave_type, start.year)
            raise ValidationError(
                {"days": f"Insufficient balance: {balance.remaining_days} day(s) remaining."}
            )
        serializer.save(employee=employee)


class LeaveDecisionView(APIView):
    """POST /api/v1/hrms/leave/{id}/{approve|reject|cancel}/"""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_LEAVE

    def post(self, request, pk, action):
        leave = LeaveRequest.objects.filter(pk=pk).select_related("employee__agent", "leave_type").first()
        if leave is None:
            return Response({"error": "not_found"}, status=404)

        note = (request.data.get("note") or "")[:300]

        if action == "cancel":
            # Own request, or a manager cancelling on someone's behalf.
            own = employee_for(request.user) == leave.employee
            if not (own or is_hr_manager(request.user)):
                return Response({"error": "forbidden"}, status=403)
            fn = leave_svc.cancel_leave
            args = (leave,)
        else:
            if not is_hr_manager(request.user):
                return Response(
                    {"error": "forbidden", "message": "Only managers can decide leave."}, status=403
                )
            fn = leave_svc.approve_leave if action == "approve" else leave_svc.reject_leave
            args = (leave, request.user, note)

        try:
            fn(*args)
        except ValueError as exc:
            return Response({"error": "invalid_transition", "message": str(exc)}, status=400)

        leave.refresh_from_db()
        return Response(LeaveRequestSerializer(leave).data)


# ============================================================
# Expenses
# ============================================================

class ExpenseClaimListCreateView(generics.ListCreateAPIView):
    serializer_class = ExpenseClaimSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_EXPENSES
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = ExpenseClaim.objects.select_related("employee__agent")
        qs = scope_to_visible(qs, self.request.user)
        if status_filter := self.request.query_params.get("status"):
            qs = qs.filter(status=status_filter)
        return qs

    def perform_create(self, serializer):
        serializer.save(employee=_require_employee(self.request))


class ExpenseDecisionView(APIView):
    """POST /api/v1/hrms/expenses/{id}/{approve|reject}/ — manager only."""

    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_EXPENSES

    def post(self, request, pk, action):
        claim = ExpenseClaim.objects.filter(pk=pk).first()
        if claim is None:
            return Response({"error": "not_found"}, status=404)
        if claim.status != ApprovalStatus.PENDING:
            return Response(
                {"error": "invalid_transition", "message": f"Claim is already {claim.status}."},
                status=400,
            )

        claim.status = ApprovalStatus.APPROVED if action == "approve" else ApprovalStatus.REJECTED
        claim.decided_by = request.user
        claim.decided_at = timezone.now()
        claim.decision_note = (request.data.get("note") or "")[:300]
        claim.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
        return Response(ExpenseClaimSerializer(claim).data)


# ============================================================
# Incentives
# ============================================================

class IncentiveRuleListCreateView(generics.ListCreateAPIView):
    serializer_class = IncentiveRuleSerializer
    queryset = IncentiveRule.objects.all()
    permission_classes = [IsTenantAdmin, HasFeatureAccess]
    required_feature = FeatureKey.INCENTIVE_ENGINE
    pagination_class = None


class IncentiveEarningListView(generics.ListAPIView):
    serializer_class = IncentiveEarningSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.INCENTIVE_ENGINE
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = IncentiveEarning.objects.select_related("employee__agent", "rule")
        qs = scope_to_visible(qs, self.request.user)
        if month := self.request.query_params.get("month"):
            try:
                qs = qs.filter(period_month=_parse_month(month))
            except ValueError:
                return qs.none()
        return qs


class IncentiveComputeView(APIView):
    """POST /api/v1/hrms/incentives/compute/ {"month": "YYYY-MM"} — admin."""

    permission_classes = [IsTenantAdmin, HasFeatureAccess]
    required_feature = FeatureKey.INCENTIVE_ENGINE

    def post(self, request):
        from apps.hrms.services.incentives import compute_all_earnings

        try:
            month = _parse_month(request.data.get("month"))
        except ValueError as exc:
            return Response({"error": "invalid_month", "message": str(exc)}, status=400)
        return Response(compute_all_earnings(month))


# ============================================================
# Payroll (admin only — salary data must never leak to peers)
# ============================================================

class SalaryStructureListCreateView(generics.ListCreateAPIView):
    serializer_class = SalaryStructureSerializer
    permission_classes = [IsTenantAdmin, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_PAYROLL
    pagination_class = None

    def get_queryset(self):
        qs = SalaryStructure.objects.select_related("employee__agent")
        if employee_id := self.request.query_params.get("employee"):
            qs = qs.filter(employee_id=employee_id)
        return qs


class PayslipListView(generics.ListAPIView):
    serializer_class = PayslipSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_PAYROLL
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        # Employees may read their OWN payslips; admins read all.
        qs = Payslip.objects.select_related("employee__agent")
        if not is_hr_manager(self.request.user):
            employee = employee_for(self.request.user)
            qs = qs.filter(employee=employee) if employee else qs.none()
        if month := self.request.query_params.get("month"):
            try:
                qs = qs.filter(period_month=_parse_month(month))
            except ValueError:
                return qs.none()
        return qs


class PayrollRunView(APIView):
    """POST /api/v1/hrms/payroll/run/ {"month": "YYYY-MM"} — builds draft payslips."""

    permission_classes = [IsTenantAdmin, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_PAYROLL

    def post(self, request):
        from apps.hrms.services.payroll import run_payroll

        try:
            month = _parse_month(request.data.get("month"))
        except ValueError as exc:
            return Response({"error": "invalid_month", "message": str(exc)}, status=400)

        result = run_payroll(month)
        return Response(result, status=200 if not result["errors"] else 207)


class PayslipFinalizeView(APIView):
    """POST /api/v1/hrms/payslips/{id}/finalize/"""

    permission_classes = [IsTenantAdmin, HasFeatureAccess]
    required_feature = FeatureKey.HRMS_PAYROLL

    def post(self, request, pk):
        slip = Payslip.objects.filter(pk=pk).first()
        if slip is None:
            return Response({"error": "not_found"}, status=404)
        slip.finalize()
        return Response(PayslipSerializer(slip).data)
