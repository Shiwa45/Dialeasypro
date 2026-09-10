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

from apps.authentication.permissions import HasFeatureAccess, IsAuthenticatedAgent
from apps.core.capabilities import Cap
from apps.core.constants import FeatureKey
from apps.core.permissions import HasCapability
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
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_VIEW
    capability_by_method = {"POST": Cap.HRMS_MANAGE}

    def get_queryset(self):
        qs = Employee.objects.select_related("agent", "reporting_to__agent")
        if not is_hr_manager(self.request.user):
            qs = qs.filter(agent=self.request.user)
        if self.request.query_params.get("active") == "true":
            qs = qs.filter(is_active=True)
        return qs


class EmployeeDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_MANAGE

    def get_queryset(self):
        return Employee.objects.select_related("agent")

    def perform_destroy(self, instance):
        """
        Exit an employee rather than deleting the row.

        A hard delete would cascade through Attendance, LeaveRequest,
        ExpenseClaim, IncentiveEarning and Payslip — taking finalized payslips
        and approved claims with it. Those are records a company has to be able
        to produce years later, so leaving is a state change, not a deletion.
        """
        instance.is_active = False
        if instance.date_of_exit is None:
            instance.date_of_exit = timezone.localdate()
        instance.save(update_fields=["is_active", "date_of_exit"])


class MyEmployeeView(APIView):
    """GET /api/v1/hrms/me/ — the caller's own employment record."""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_VIEW

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
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_VIEW
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

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_VIEW

    def post(self, request):
        from apps.hrms.services.attendance import mark_check_in

        try:
            employee = _require_employee(request)
        except ValueError as exc:
            return Response({"error": "not_enrolled", "message": str(exc)}, status=400)
        return Response(AttendanceSerializer(mark_check_in(employee)).data)


class CheckOutView(APIView):
    """POST /api/v1/hrms/attendance/check-out/"""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_VIEW

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

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_MANAGE

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
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_VIEW
    capability_by_method = {"POST": Cap.HRMS_MANAGE}


class HolidayDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = HolidaySerializer
    queryset = Holiday.objects.all()
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_MANAGE


# ============================================================
# Leave
# ============================================================

class LeaveTypeListCreateView(generics.ListCreateAPIView):
    serializer_class = LeaveTypeSerializer
    queryset = LeaveType.objects.filter(is_active=True)
    pagination_class = None
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_LEAVE
    required_capability = Cap.HRMS_VIEW
    capability_by_method = {"POST": Cap.HRMS_MANAGE}


class LeaveTypeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    PATCH/DELETE an existing leave type. Deletion is a soft `is_active=False`
    flip via the serializer, not a real delete — a leave type may already be
    referenced by LeaveBalance/LeaveRequest rows, and removing it would orphan
    them or make historical requests unrenderable.
    """

    serializer_class = LeaveTypeSerializer
    queryset = LeaveType.objects.all()
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_LEAVE
    required_capability = Cap.HRMS_MANAGE

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class LeaveBalanceListView(generics.ListAPIView):
    serializer_class = LeaveBalanceSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_LEAVE
    required_capability = Cap.HRMS_VIEW
    pagination_class = None

    def get_queryset(self):
        qs = LeaveBalance.objects.select_related("leave_type", "employee__agent")
        qs = scope_to_visible(qs, self.request.user)
        year = self.request.query_params.get("year") or timezone.localdate().year
        return qs.filter(year=year)


class LeaveRequestListCreateView(generics.ListCreateAPIView):
    serializer_class = LeaveRequestSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_LEAVE
    required_capability = Cap.HRMS_VIEW
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

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_LEAVE
    required_capability = Cap.HRMS_VIEW

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
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_EXPENSES
    required_capability = Cap.HRMS_VIEW
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

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_EXPENSES
    required_capability = Cap.HRMS_APPROVE

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
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.INCENTIVE_ENGINE
    required_capability = Cap.HRMS_INCENTIVES
    pagination_class = None


class IncentiveRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    PATCH/DELETE an existing rule. Deletion is soft (`is_active=False`) —
    IncentiveEarning rows reference their rule by FK and are a paid-out
    historical record; a hard delete would either cascade them away or leave
    a dangling reference depending on the FK's on_delete, neither of which is
    acceptable for something that already appears on a payslip.
    """

    serializer_class = IncentiveRuleSerializer
    queryset = IncentiveRule.objects.all()
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.INCENTIVE_ENGINE
    required_capability = Cap.HRMS_INCENTIVES

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class IncentiveEarningListView(generics.ListAPIView):
    serializer_class = IncentiveEarningSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.INCENTIVE_ENGINE
    required_capability = Cap.HRMS_VIEW
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

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.INCENTIVE_ENGINE
    required_capability = Cap.HRMS_INCENTIVES

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
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_PAYROLL
    required_capability = Cap.HRMS_PAYROLL
    pagination_class = None

    def get_queryset(self):
        qs = SalaryStructure.objects.select_related("employee__agent")
        if employee_id := self.request.query_params.get("employee"):
            qs = qs.filter(employee_id=employee_id)
        return qs


class PayslipListView(generics.ListAPIView):
    serializer_class = PayslipSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_PAYROLL
    required_capability = Cap.HRMS_VIEW
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

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_PAYROLL
    required_capability = Cap.HRMS_PAYROLL

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

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_PAYROLL
    required_capability = Cap.HRMS_PAYROLL

    def post(self, request, pk):
        slip = Payslip.objects.filter(pk=pk).first()
        if slip is None:
            return Response({"error": "not_found"}, status=404)
        slip.finalize()
        return Response(PayslipSerializer(slip).data)


class PayslipMarkPaidView(APIView):
    """
    POST /api/v1/hrms/payslips/{id}/mark-paid/

    Separate from finalize deliberately: finalizing freezes the numbers,
    marking paid records that money actually left. A slip can sit finalized for
    days while a bank transfer clears, and conflating the two loses that.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_PAYROLL
    required_capability = Cap.HRMS_PAYROLL

    def post(self, request, pk):
        from apps.hrms.constants import PayslipStatus

        slip = Payslip.objects.filter(pk=pk).first()
        if slip is None:
            return Response({"error": "not_found"}, status=404)
        if slip.status == PayslipStatus.DRAFT:
            return Response(
                {"error": "not_finalized",
                 "message": "Finalize the payslip before marking it paid."},
                status=400,
            )
        slip.status = PayslipStatus.PAID
        slip.paid_at = timezone.now()
        slip.save(update_fields=["status", "paid_at"])
        return Response(PayslipSerializer(slip).data)


class PayslipDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/hrms/payslips/{id}/ — one slip including its `breakdown` JSON.

    Scoped like the list: an employee may open their own slip, never a peer's.
    """

    serializer_class = PayslipSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_PAYROLL
    required_capability = Cap.HRMS_VIEW

    def get_queryset(self):
        qs = Payslip.objects.select_related("employee__agent")
        if not is_hr_manager(self.request.user):
            employee = employee_for(self.request.user)
            qs = qs.filter(employee=employee) if employee else qs.none()
        return qs


# ============================================================
# Attendance correction
# ============================================================

class AttendanceDetailView(generics.RetrieveUpdateAPIView):
    """
    GET/PATCH /api/v1/hrms/attendance/{id}/

    The admin correction path. AttendanceSource.ADMIN existed in constants from
    the start but nothing could ever set it — the nightly dialer sync wrote
    AUTO and check-in wrote MANUAL, so a wrong row could only be fixed in the
    Django admin. Any edit here stamps source=ADMIN so a corrected row is
    always distinguishable from a derived one, and the next sync knows to leave
    it alone.
    """

    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_VIEW
    capability_by_method = {"PATCH": Cap.HRMS_MANAGE, "PUT": Cap.HRMS_MANAGE}

    def get_queryset(self):
        return scope_to_visible(
            Attendance.objects.select_related("employee__agent"), self.request.user
        )

    def perform_update(self, serializer):
        from apps.hrms.constants import AttendanceSource

        serializer.save(source=AttendanceSource.ADMIN)


# ============================================================
# Leave balance allocation
# ============================================================

class LeaveBalanceManageView(APIView):
    """
    POST /api/v1/hrms/leave-balances/
        {"employee": 1, "leave_type": 2, "year": 2026, "allocated_days": "12.0"}

    Upserts one allocation. Without this, balances only ever appeared through
    whatever the leave service happened to create on first use, so an admin had
    no way to grant someone their annual quota.

    PATCH /api/v1/hrms/leave-balances/{id}/ adjusts an existing row.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_LEAVE
    required_capability = Cap.HRMS_MANAGE

    def post(self, request):
        serializer = LeaveBalanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        obj, _created = LeaveBalance.objects.update_or_create(
            employee=data["employee"],
            leave_type=data["leave_type"],
            year=data["year"],
            defaults={"allocated_days": data.get("allocated_days", 0)},
        )
        return Response(LeaveBalanceSerializer(obj).data, status=201)

    def patch(self, request, pk):
        obj = LeaveBalance.objects.filter(pk=pk).first()
        if obj is None:
            return Response({"error": "not_found"}, status=404)
        serializer = LeaveBalanceSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        deleted, _ = LeaveBalance.objects.filter(pk=pk).delete()
        return Response(status=204 if deleted else 404)


class BulkAllocateLeaveView(APIView):
    """
    POST /api/v1/hrms/leave-balances/bulk-allocate/ {"year": 2026}

    Grants every active employee each active leave type's annual quota for the
    year. This is the January-1st chore; doing it employee-by-employee through
    the single endpoint is what makes people skip it.

    Idempotent: re-running tops an existing row UP to the quota but never
    reduces one that was manually raised, and never touches used_days.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_LEAVE
    required_capability = Cap.HRMS_MANAGE

    def post(self, request):
        year = int(request.data.get("year") or timezone.localdate().year)
        employees = Employee.objects.filter(is_active=True)
        types = LeaveType.objects.filter(is_active=True)

        created = updated = 0
        for employee in employees:
            for leave_type in types:
                obj, was_created = LeaveBalance.objects.get_or_create(
                    employee=employee, leave_type=leave_type, year=year,
                    defaults={"allocated_days": leave_type.annual_quota_days},
                )
                if was_created:
                    created += 1
                elif obj.allocated_days < leave_type.annual_quota_days:
                    obj.allocated_days = leave_type.annual_quota_days
                    obj.save(update_fields=["allocated_days"])
                    updated += 1

        return Response({
            "year": year,
            "employees": employees.count(),
            "leave_types": types.count(),
            "created": created,
            "topped_up": updated,
        })


# ============================================================
# Dashboard
# ============================================================

class HRMSDashboardView(APIView):
    """
    GET /api/v1/hrms/dashboard/?month=YYYY-MM

    The numbers an HR lead opens the module to see. Computed in one place so
    the web app doesn't fan out into six list calls and add them up client-side
    (which it would otherwise have to, and would get wrong on page 2).
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_VIEW_ALL

    def get(self, request):
        from django.db.models import Count, Sum

        from apps.hrms.constants import AttendanceStatus

        today = timezone.localdate()
        try:
            month = _parse_month(request.query_params.get("month"))
        except ValueError as exc:
            return Response({"error": "invalid_month", "message": str(exc)}, status=400)

        employees = Employee.objects.filter(is_active=True)
        headcount = employees.count()

        today_rows = Attendance.objects.filter(date=today)
        by_status = dict(
            today_rows.values_list("status").annotate(n=Count("id")).values_list("status", "n")
        )

        payroll = Payslip.objects.filter(period_month=month).aggregate(
            gross=Sum("gross_earnings"),
            net=Sum("net_pay"),
            incentives=Sum("incentives_amount"),
            n=Count("id"),
        )

        return Response({
            "month": month.isoformat(),
            "headcount": headcount,
            "attendance_today": {
                "present": by_status.get(AttendanceStatus.PRESENT, 0),
                "absent": by_status.get(AttendanceStatus.ABSENT, 0),
                "half_day": by_status.get(AttendanceStatus.HALF_DAY, 0),
                "on_leave": by_status.get(AttendanceStatus.ON_LEAVE, 0),
                # Nobody has a row until the nightly sync runs, so "not marked"
                # is a real state and worth showing rather than folding into absent.
                "not_marked": max(0, headcount - today_rows.count()),
            },
            "pending": {
                "leave": LeaveRequest.objects.filter(status=ApprovalStatus.PENDING).count(),
                "expenses": ExpenseClaim.objects.filter(status=ApprovalStatus.PENDING).count(),
            },
            "payroll": {
                "payslips": payroll["n"] or 0,
                "gross": str(payroll["gross"] or 0),
                "net": str(payroll["net"] or 0),
                "incentives": str(payroll["incentives"] or 0),
            },
            "birthdays_this_month": [],  # reserved: Agent has no DOB field yet
        })
