"""
An agent can apply for leave and claim an expense from the app.

Both serializers listed `employee` as a writable, required field. The views
set it themselves — it is the requester's own record — but validation ran
first, so every request from the app's My Work screen (which rightly does not
send it) was refused with "employee: This field is required".
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.hrms.models import Employee, ExpenseClaim, LeaveRequest, LeaveType
from apps.hrms.views import ExpenseClaimListCreateView, LeaveRequestListCreateView

pytestmark = pytest.mark.django_db


@pytest.fixture
def asha():
    agent = Agent.objects.create_agent(email="asha@example.com", name="Asha", password="Pw@12345678")
    Employee.objects.create(agent=agent, employee_code="EMP-ASHA",
                            date_of_joining=timezone.localdate() - timedelta(days=365))
    return agent


def _post(view, user, data):
    request = APIRequestFactory().post("/", data, format="json")
    force_authenticate(request, user=user)
    request.has_feature = lambda key: True
    response = view.as_view()(request)
    response.render()
    return response


def test_an_expense_claim_from_the_app_is_accepted(asha):
    # Exactly what the app sends (HrmsService.claimExpense).
    r = _post(ExpenseClaimListCreateView, asha, {
        "date": timezone.localdate().isoformat(), "category": "travel",
        "amount": "450", "description": "Cab to client",
    })

    assert r.status_code == 201, r.data
    claim = ExpenseClaim.objects.get()
    assert claim.employee == asha.employee
    assert claim.amount == Decimal("450")


def test_a_leave_request_from_the_app_is_accepted(asha):
    unpaid = LeaveType.objects.create(name="Unpaid", annual_quota_days=Decimal("0"), is_paid=False)
    start = timezone.localdate() + timedelta(days=7)

    # Exactly what the app sends (HrmsService.applyLeave).
    r = _post(LeaveRequestListCreateView, asha, {
        "leave_type": unpaid.pk, "start_date": start.isoformat(), "end_date": start.isoformat(),
        "days": "1", "reason": "Family function",
    })

    assert r.status_code == 201, r.data
    assert LeaveRequest.objects.get().employee == asha.employee


def test_nobody_files_for_someone_else(asha):
    other = Agent.objects.create_agent(email="bilal@example.com", name="Bilal", password="Pw@12345678")
    Employee.objects.create(agent=other, employee_code="EMP-BILAL",
                            date_of_joining=timezone.localdate() - timedelta(days=365))

    r = _post(ExpenseClaimListCreateView, asha, {
        "employee": other.employee.pk, "date": timezone.localdate().isoformat(),
        "category": "food", "amount": "100",
    })

    assert r.status_code == 201
    assert ExpenseClaim.objects.get().employee == asha.employee, "the claim is always the requester's own"
