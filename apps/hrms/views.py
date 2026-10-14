"""
TeleCRM Backend — apps/hrms/views.py

HRMS API. Every endpoint is plan-gated on its HRMS feature key, so the module
is only reachable for tenants who bought it (see ModuleKey.HRMS).

Scoping: employees read/write their own rows; managers and admins see the whole
org. Payroll is admin-only.
"""
import logging
from datetime import date, datetime

from decimal import Decimal

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import APIException, ValidationError
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
    HrmsPolicy,
    IncentiveEarning,
    IncentiveRule,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    Payslip,
    SalaryStructure,
)
from apps.hrms.permissions import (
    can_manage, employee_for, is_hr_manager, is_self_approval, scope_to_visible,
)
from apps.hrms.serializers import (
    AttendanceSerializer,
    EmployeeSerializer,
    ExpenseClaimSerializer,
    HolidaySerializer,
    HrmsPolicySerializer,
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


class Refused(APIException):
    """A 400 with a plain message and an error code, e.g. Refused("...", code="in_use")."""

    status_code = 400
    default_code = "invalid_request"


class NotEnrolled(APIException):
    status_code = 400
    default_code = "not_enrolled"
    default_detail = "You are not enrolled in HRMS. Ask your admin to add an employee record."


def _require_employee(request) -> Employee:
    """The caller's own Employee row. Raises a 400 (it used to be a 500) when there is none."""
    employee = employee_for(request.user)
    if employee is None:
        raise NotEnrolled()
    return employee


def _target_employee(request) -> Employee:
    """
    Who a new leave request or claim is for: `employee` in the body when the
    caller manages HRMS (HR filing on someone's behalf), else the caller.
    """
    raw = request.data.get("employee")
    # Anyone else's `employee` is ignored: their request is always their own.
    if raw not in (None, "") and can_manage(request.user):
        employee = Employee.objects.filter(pk=raw).select_related("agent").first()
        if employee is None:
            raise ValidationError({"employee": "No such employee."})
        if not employee.is_active:
            raise ValidationError({"employee": f"{employee.agent.name} has left."})
        return employee
    return _require_employee(request)


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

class AttendanceListView(generics.ListCreateAPIView):
    """GET the attendance list; POST adds a missing day (HR)."""

    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_VIEW
    capability_by_method = {"POST": Cap.HRMS_MANAGE}
    pagination_class = StandardResultsSetPagination

    def perform_create(self, serializer):
        from apps.hrms.constants import AttendanceSource

        serializer.save(source=AttendanceSource.ADMIN)

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

        employee = _require_employee(request)
        return Response(AttendanceSerializer(mark_check_in(employee)).data)


class CheckOutView(APIView):
    """POST /api/v1/hrms/attendance/check-out/"""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_VIEW

    def post(self, request):
        from apps.hrms.services.attendance import mark_check_out

        employee = _require_employee(request)
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
        if day > timezone.localdate():
            return Response({"error": "invalid_date", "message": "Can't sync a future date."}, status=400)

        stats = {}
        written = sync_attendance_for_date(day, stats)
        # rows_written counts only rows rebuilt from the dialer; rows kept
        # (corrected by hand, checked in, on leave) are reported separately.
        return Response({"date": day.isoformat(), "rows_written": written, "kept": stats.get("kept", 0)})


def _resync_holiday(*days):
    """
    A holiday added, moved or removed changes that day's attendance. The
    rows derived from the dialer are rebuilt now; they used to stay ABSENT
    (and docked) until someone synced the date by hand.
    """
    from apps.hrms.services.attendance import resync_auto_rows

    for day in {d for d in days if d}:
        resync_auto_rows(day)


class HolidayListCreateView(generics.ListCreateAPIView):
    serializer_class = HolidaySerializer
    queryset = Holiday.objects.all()
    pagination_class = None
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_VIEW
    capability_by_method = {"POST": Cap.HRMS_MANAGE}

    def perform_create(self, serializer):
        holiday = serializer.save()
        _resync_holiday(holiday.date)


class HolidayDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = HolidaySerializer
    queryset = Holiday.objects.all()
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_MANAGE

    def perform_update(self, serializer):
        old = serializer.instance.date
        holiday = serializer.save()
        _resync_holiday(old, holiday.date)

    def perform_destroy(self, instance):
        day = instance.date
        instance.delete()
        _resync_holiday(day)


# ============================================================
# Leave
# ============================================================

class LeaveTypeListCreateView(generics.ListCreateAPIView):
    """
    Active types; `?include_inactive=1` adds switched-off ones for HR, so a
    type removed by mistake can be switched back on.
    """

    serializer_class = LeaveTypeSerializer
    pagination_class = None
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_LEAVE
    required_capability = Cap.HRMS_VIEW
    capability_by_method = {"POST": Cap.HRMS_MANAGE}

    def get_queryset(self):
        qs = LeaveType.objects.all()
        if not (self.request.query_params.get("include_inactive") in ("1", "true")
                and can_manage(self.request.user)):
            qs = qs.filter(is_active=True)
        return qs


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
        p = self.request.query_params
        year = p.get("year") or timezone.localdate().year
        qs = qs.filter(year=year)
        if employee_id := p.get("employee"):
            qs = qs.filter(employee_id=employee_id)
        if p.get("mine") in ("1", "true"):
            qs = qs.filter(employee__agent=self.request.user)
        return qs.order_by("employee__employee_code", "leave_type__name")


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
        employee = _target_employee(self.request)
        data = serializer.validated_data
        half_day = bool(data.get("half_day"))
        try:
            per_year = leave_svc.validate_request(
                employee, data["leave_type"], data["start_date"], data["end_date"], half_day,
            )
        except leave_svc.LeaveError as exc:
            raise ValidationError({exc.field: str(exc)})
        serializer.save(employee=employee, half_day=half_day,
                        days=sum(per_year.values(), Decimal("0")))


# Rejecting your own request is allowed — it is the same as withdrawing it.
SELF_APPROVAL_REFUSED = {
    "error": "self_approval",
    "message": "You can't approve your own request. Ask another manager or the admin.",
}


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
            if action == "approve" and is_self_approval(request.user, leave.employee):
                return Response(SELF_APPROVAL_REFUSED, status=403)
            fn = leave_svc.approve_leave if action == "approve" else leave_svc.reject_leave
            args = (leave, request.user, note)

        # Decide against the row as it is NOW, locked. The status check in the
        # service ran on the copy read above, so two clicks landing together
        # both saw "pending" and both approved — debiting the balance twice.
        from django.db import transaction

        try:
            with transaction.atomic():
                locked = (
                    LeaveRequest.objects.select_for_update()
                    .select_related("employee__agent", "leave_type").get(pk=leave.pk)
                )
                fn(locked, *args[1:])
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
        employee = _target_employee(self.request)
        day = serializer.validated_data["date"]
        if day < employee.date_of_joining:
            raise ValidationError({"date": "That's before the employee joined."})
        serializer.save(employee=employee)


class ExpenseDecisionView(APIView):
    """POST /api/v1/hrms/expenses/{id}/{approve|reject}/ — manager only."""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_EXPENSES
    required_capability = Cap.HRMS_APPROVE

    def post(self, request, pk, action):
        claim = ExpenseClaim.objects.filter(pk=pk).select_related("employee").first()
        if claim is None:
            return Response({"error": "not_found"}, status=404)
        if action == "approve" and is_self_approval(request.user, claim.employee):
            return Response(SELF_APPROVAL_REFUSED, status=403)
        # One conditional UPDATE: only a claim still pending changes. Checking
        # and then saving let a double click apply two decisions.
        decided = ExpenseClaim.objects.filter(pk=claim.pk, status=ApprovalStatus.PENDING).update(
            status=ApprovalStatus.APPROVED if action == "approve" else ApprovalStatus.REJECTED,
            decided_by=request.user,
            decided_at=timezone.now(),
            decision_note=(request.data.get("note") or "")[:300],
            updated_at=timezone.now(),
        )
        claim.refresh_from_db()
        if not decided:
            return Response(
                {"error": "invalid_transition", "message": f"Claim is already {claim.status}."},
                status=400,
            )
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

    def perform_update(self, serializer):
        from apps.hrms.services.incentives import discard_unpaid_earnings

        rule = serializer.save()
        if not rule.is_active:
            discard_unpaid_earnings(rule)

    def perform_destroy(self, instance):
        from apps.hrms.services.incentives import discard_unpaid_earnings

        instance.is_active = False
        instance.save(update_fields=["is_active"])
        # Earnings a switched-off rule had computed are dropped unless a
        # finalized payslip already paid them; they used to be paid anyway.
        discard_unpaid_earnings(instance)


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


def _structure_in_use(structure) -> Payslip | None:
    """A finalized or paid payslip built from this structure, if any."""
    from apps.hrms.constants import PayslipStatus

    for slip in Payslip.objects.filter(employee=structure.employee).exclude(status=PayslipStatus.DRAFT):
        b = slip.breakdown or {}
        if structure.pk in (b.get("structure_ids") or [b.get("structure_id")]):
            return slip
    return None


class SalaryStructureDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/v1/hrms/salary-structures/{id}/

    A structure a finalized payslip was built from can't be changed (add a
    new one from a later date instead); any other can be fixed or removed.
    """

    serializer_class = SalaryStructureSerializer
    queryset = SalaryStructure.objects.select_related("employee__agent")
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_PAYROLL
    required_capability = Cap.HRMS_PAYROLL

    def _refuse_if_used(self, structure):
        slip = _structure_in_use(structure)
        if slip is not None:
            raise Refused(
                f"The {slip.period_month:%B %Y} payslip ({slip.status}) was built from this "
                f"structure. Add a new structure from a later date instead.", code="in_use",
            )

    def perform_update(self, serializer):
        if "employee" in serializer.validated_data and \
                serializer.validated_data["employee"] != serializer.instance.employee:
            raise ValidationError({"employee": "Can't be changed."})
        self._refuse_if_used(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._refuse_if_used(instance)
        instance.delete()


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
        from apps.hrms.services.payroll import finalize_blockers

        slip = Payslip.objects.filter(pk=pk).first()
        if slip is None:
            return Response({"error": "not_found"}, status=404)
        reason = finalize_blockers(slip)
        if reason:
            return Response({"error": "cannot_finalize", "message": reason}, status=400)
        # Conditional update: a double click can't finalize twice.
        from apps.hrms.constants import PayslipStatus

        Payslip.objects.filter(pk=slip.pk, status=PayslipStatus.DRAFT).update(
            status=PayslipStatus.FINALIZED, finalized_at=timezone.now(), updated_at=timezone.now(),
        )
        slip.refresh_from_db()
        return Response(PayslipSerializer(slip).data)


class PayslipReopenView(APIView):
    """
    POST /api/v1/hrms/payslips/{id}/reopen/ — finalized → draft, to correct it.

    A paid slip can't be reopened: money has left.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_PAYROLL
    required_capability = Cap.HRMS_PAYROLL

    def post(self, request, pk):
        from apps.hrms.constants import PayslipStatus

        slip = Payslip.objects.filter(pk=pk).first()
        if slip is None:
            return Response({"error": "not_found"}, status=404)
        reopened = Payslip.objects.filter(pk=slip.pk, status=PayslipStatus.FINALIZED).update(
            status=PayslipStatus.DRAFT, finalized_at=None, updated_at=timezone.now(),
        )
        slip.refresh_from_db()
        if not reopened:
            msg = ("This payslip is marked paid and can't be reopened."
                   if slip.status == PayslipStatus.PAID else "This payslip is already a draft.")
            return Response({"error": "invalid_transition", "message": msg}, status=400)
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


class PayslipDetailView(generics.RetrieveDestroyAPIView):
    """
    GET /api/v1/hrms/payslips/{id}/ — one slip including its `breakdown` JSON.
    DELETE removes a DRAFT slip (payroll admins); its incentives and claims
    are released for the next run.

    Scoped like the list: an employee may open their own slip, never a peer's.
    """

    serializer_class = PayslipSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_PAYROLL
    required_capability = Cap.HRMS_VIEW
    capability_by_method = {"DELETE": Cap.HRMS_PAYROLL}

    def perform_destroy(self, instance):
        from apps.hrms.constants import PayslipStatus

        if instance.status != PayslipStatus.DRAFT:
            raise Refused("Only a draft payslip can be deleted. Reopen it first.",
                          code="invalid_transition")
        instance.delete()  # FKs on earnings and claims are SET_NULL

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
        allocated = data.get("allocated_days", Decimal("0"))
        existing = LeaveBalance.objects.filter(
            employee=data["employee"], leave_type=data["leave_type"], year=data["year"],
        ).first()
        if existing and allocated < existing.used_days:
            raise ValidationError({
                "allocated_days": f"{existing.used_days} day(s) are already used; allocate at least that.",
            })
        obj, _created = LeaveBalance.objects.update_or_create(
            employee=data["employee"],
            leave_type=data["leave_type"],
            year=data["year"],
            defaults={"allocated_days": allocated},
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
        obj = LeaveBalance.objects.filter(pk=pk).first()
        if obj is None:
            return Response(status=404)
        if obj.used_days > 0:
            return Response({"error": "in_use",
                             "message": "Leave has been taken against this balance; it can't be deleted."},
                            status=400)
        obj.delete()
        return Response(status=204)


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
        try:
            year = int(request.data.get("year") or timezone.localdate().year)
        except (TypeError, ValueError):
            return Response({"error": "invalid_year", "message": "Enter a year."}, status=400)
        if not 2000 <= year <= 2100:
            return Response({"error": "invalid_year", "message": "Enter a year between 2000 and 2100."},
                            status=400)
        employees = Employee.objects.filter(is_active=True)
        types = LeaveType.objects.filter(is_active=True)

        created = updated = carried = 0
        for employee in employees:
            for leave_type in types:
                target = _yearly_entitlement(employee, leave_type, year)
                carry = Decimal("0")
                if leave_type.carry_forward:
                    prev = LeaveBalance.objects.filter(
                        employee=employee, leave_type=leave_type, year=year - 1
                    ).first()
                    if prev and prev.remaining_days > 0:
                        carry = prev.remaining_days
                        carried += 1
                target += carry
                obj, was_created = LeaveBalance.objects.get_or_create(
                    employee=employee, leave_type=leave_type, year=year,
                    defaults={"allocated_days": target},
                )
                if was_created:
                    created += 1
                elif obj.allocated_days < target:
                    obj.allocated_days = target
                    obj.save(update_fields=["allocated_days", "updated_at"])
                    updated += 1

        return Response({
            "year": year,
            "employees": employees.count(),
            "leave_types": types.count(),
            "created": created,
            "topped_up": updated,
            "carried_forward": carried,
        })


def _yearly_entitlement(employee, leave_type, year: int) -> Decimal:
    """
    The year's quota, pro-rated by whole months for someone who joined during
    it (rounded to the nearest half day). Someone joining in October used to
    get the full year's leave.
    """
    quota = leave_type.annual_quota_days
    joined = employee.date_of_joining
    if joined.year < year:
        return quota
    if joined.year > year:
        return Decimal("0")
    months = 12 - joined.month + 1
    share = quota * Decimal(months) / Decimal(12)
    return (share * 2).quantize(Decimal("1")) / 2


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

        # Only people still employed: an exited employee's row used to count.
        today_rows = Attendance.objects.filter(date=today, employee__is_active=True)
        by_status = dict(
            today_rows.order_by().values_list("status").annotate(n=Count("id")).values_list("status", "n")
        )

        payroll = Payslip.objects.filter(period_month=month).aggregate(
            gross=Sum("gross_earnings"),
            net=Sum("net_pay"),
            incentives=Sum("incentives_amount"),
            reimbursements=Sum("reimbursements_amount"),
            deductions=Sum("total_deductions"),
            n=Count("id"),
        )

        # "Awaiting you": what this person can actually decide — not their
        # own requests, which they can't approve.
        pending_leave = LeaveRequest.objects.filter(status=ApprovalStatus.PENDING)
        pending_expenses = ExpenseClaim.objects.filter(status=ApprovalStatus.PENDING)
        own = employee_for(request.user)
        if own is not None and is_self_approval(request.user, own):
            pending_leave = pending_leave.exclude(employee=own)
            pending_expenses = pending_expenses.exclude(employee=own)

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
                "leave": pending_leave.count(),
                "expenses": pending_expenses.count(),
            },
            "payroll": {
                "payslips": payroll["n"] or 0,
                "gross": str(payroll["gross"] or 0),
                "net": str(payroll["net"] or 0),
                "incentives": str(payroll["incentives"] or 0),
                "reimbursements": str(payroll["reimbursements"] or 0),
                "deductions": str(payroll["deductions"] or 0),
            },
            "birthdays_this_month": [],  # reserved: Agent has no DOB field yet
        })


# ============================================================
# Policy
# ============================================================

class HrmsPolicyView(APIView):
    """
    GET/PATCH /api/v1/hrms/policy/

    Company-wide thresholds: hours for a present / half day, the largest
    expense claim, and above what amount a receipt is required.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_ATTENDANCE
    required_capability = Cap.HRMS_VIEW
    capability_by_method = {"PATCH": Cap.HRMS_MANAGE}

    def get(self, request):
        return Response(HrmsPolicySerializer(HrmsPolicy.current()).data)

    def patch(self, request):
        serializer = HrmsPolicySerializer(HrmsPolicy.current(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
