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
