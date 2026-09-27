"""
Nobody approves their own leave or expenses.

The decision endpoints checked the approver's capability and nothing else, so
an HR manager could approve their own leave and reimburse their own expense
claims. The tenant admin is exempt — there is nobody above them.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.core.constants import AgentRole
from apps.hrms.constants import ApprovalStatus
from apps.hrms.models import Employee, ExpenseClaim, LeaveRequest, LeaveType
from apps.hrms.views import ExpenseDecisionView, LeaveDecisionView

pytestmark = pytest.mark.django_db


def _employee(email, role, code):
    agent = Agent.objects.create_agent(email=email, name=code, password="Pw@12345678", role=role)
    Employee.objects.create(agent=agent, employee_code=code,
                            date_of_joining=timezone.localdate() - timedelta(days=365))
    return agent


@pytest.fixture
def hr():
    return _employee("hr@x.com", AgentRole.HR, "EMP-HR")


@pytest.fixture
def other_hr():
    return _employee("hr2@x.com", AgentRole.HR, "EMP-HR2")


@pytest.fixture
def admin():
    return _employee("boss@x.com", AgentRole.ADMIN, "EMP-BOSS")


def _leave(agent):
    unpaid = LeaveType.objects.get_or_create(
        name="Unpaid-T", defaults={"annual_quota_days": Decimal("0"), "is_paid": False},
    )[0]
    start = timezone.localdate() + timedelta(days=10)
    return LeaveRequest.objects.create(
        employee=agent.employee, leave_type=unpaid, start_date=start, end_date=start, days=1,
    )


def _claim(agent):
    return ExpenseClaim.objects.create(
        employee=agent.employee, date=timezone.localdate(), category="travel", amount=Decimal("500"),
    )


def _decide(view, user, obj, action):
    request = APIRequestFactory().post("/", {}, format="json")
    force_authenticate(request, user=user)
    request.has_feature = lambda key: True
    response = view.as_view()(request, pk=obj.pk, action=action)
    obj.refresh_from_db()
    return response


@pytest.mark.parametrize("view,make", [(LeaveDecisionView, _leave), (ExpenseDecisionView, _claim)])
def test_hr_cannot_approve_their_own(hr, view, make):
    obj = make(hr)

    assert _decide(view, hr, obj, "approve").status_code == 403
    assert obj.status == ApprovalStatus.PENDING


@pytest.mark.parametrize("view,make", [(LeaveDecisionView, _leave), (ExpenseDecisionView, _claim)])
def test_another_hr_manager_can_approve_it(hr, other_hr, view, make):
    obj = make(hr)

    assert _decide(view, other_hr, obj, "approve").status_code == 200
    assert obj.status == ApprovalStatus.APPROVED


@pytest.mark.parametrize("view,make", [(LeaveDecisionView, _leave), (ExpenseDecisionView, _claim)])
def test_rejecting_your_own_is_just_withdrawing_it(hr, view, make):
    obj = make(hr)

    assert _decide(view, hr, obj, "reject").status_code == 200
    assert obj.status == ApprovalStatus.REJECTED


@pytest.mark.parametrize("view,make", [(LeaveDecisionView, _leave), (ExpenseDecisionView, _claim)])
def test_the_admin_has_nobody_above_them(admin, view, make):
    obj = make(admin)

    assert _decide(view, admin, obj, "approve").status_code == 200


# ---- LOW-10: two decisions landing together ------------------------------

def _second_click_lands_first(decide):
    """
    Run `decide` in the window between the view reading the row and writing
    it — where a second click's request lands in real life. The view's
    self-approval check sits exactly there.
    """
    from unittest.mock import patch

    from apps.hrms import views as hrms_views

    real = hrms_views.is_self_approval
    fired = []

    def check(agent, employee):
        if not fired:
            fired.append(1)
            decide()
        return real(agent, employee)

    return patch.object(hrms_views, "is_self_approval", side_effect=check)


def test_an_expense_is_not_decided_twice(hr, other_hr):
    claim = _claim(hr)

    def other_rejects():
        ExpenseClaim.objects.filter(pk=claim.pk).update(
            status=ApprovalStatus.REJECTED, decided_by=hr)

    with _second_click_lands_first(other_rejects):
        response = _decide(ExpenseDecisionView, other_hr, claim, "approve")

    assert response.status_code == 400
    assert claim.status == ApprovalStatus.REJECTED, "the later decision overwrote the earlier one"


def test_leave_is_not_approved_twice(hr, other_hr):
    from apps.hrms.models import LeaveBalance
    from apps.hrms.services import leave as leave_svc

    paid = LeaveType.objects.create(name="Casual-T", annual_quota_days=Decimal("12"), is_paid=True)
    start = timezone.localdate() + timedelta(days=10)
    leave = LeaveRequest.objects.create(
        employee=hr.employee, leave_type=paid, start_date=start, end_date=start, days=1,
    )

    def other_approves():
        leave_svc.approve_leave(LeaveRequest.objects.get(pk=leave.pk), other_hr)

    with _second_click_lands_first(other_approves):
        response = _decide(LeaveDecisionView, other_hr, leave, "approve")

    assert response.status_code == 400
    balance = LeaveBalance.objects.get(employee=hr.employee, leave_type=paid, year=start.year)
    assert balance.used_days == Decimal("1"), "the balance was debited twice"
