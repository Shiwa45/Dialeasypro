"""
What an agent is told when a phone number is already taken (APP-L7).

The number has to be refused either way, but the message was the same for
everyone: "A lead with this phone number already exists", confirming to an
agent that a number belonged to a colleague's customer. Details now only for
a lead the agent can already see.
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.core.constants import AgentRole
from apps.leads.models import Lead
from apps.leads.views import LeadDetailView, LeadListCreateView

pytestmark = pytest.mark.django_db

PHONE = "+919812300001"


@pytest.fixture
def agent():
    return Agent.objects.create_agent(email="a@example.com", name="Asha", password="Pw@12345678")


@pytest.fixture
def colleague():
    return Agent.objects.create_agent(email="b@example.com", name="Bilal", password="Pw@12345678")


@pytest.fixture
def manager():
    return Agent.objects.create_agent(
        email="m@example.com", name="Mona", password="Pw@12345678", role=AgentRole.MANAGER,
    )


def _create(user, phone=PHONE):
    request = APIRequestFactory().post(
        "/api/v1/leads/",
        {"name": "New", "phone": phone, "source": "manual", "status": "new", "priority": "warm"},
        format="json",
    )
    force_authenticate(request, user=user)
    response = LeadListCreateView.as_view()(request)
    response.render()
    return response


def _message(response):
    return str(response.data).lower()


def test_someone_elses_lead_is_not_described(agent, colleague):
    Lead.objects.create(name="Secret Customer", phone=PHONE, assigned_to=colleague)

    r = _create(agent)

    assert r.status_code == 400
    assert "ask your manager" in _message(r)
    assert "secret customer" not in _message(r)


def test_a_lead_the_agent_can_see_is_named(agent):
    Lead.objects.create(name="Ravi Kumar", phone=PHONE, assigned_to=agent)

    r = _create(agent)

    assert r.status_code == 400
    assert "ravi kumar" in _message(r)


def test_a_manager_is_told_which_lead(manager, colleague):
    Lead.objects.create(name="Ravi Kumar", phone=PHONE, assigned_to=colleague)

    r = _create(manager)

    assert r.status_code == 400
    assert "ravi kumar" in _message(r)


def test_editing_to_someone_elses_number_is_not_described(agent, colleague):
    Lead.objects.create(name="Secret Customer", phone=PHONE, assigned_to=colleague)
    mine = Lead.objects.create(name="Mine", phone="+919812300002", assigned_to=agent)

    request = APIRequestFactory().patch(f"/api/v1/leads/{mine.pk}/", {"phone": PHONE}, format="json")
    force_authenticate(request, user=agent)
    r = LeadDetailView.as_view()(request, pk=mine.pk)
    r.render()

    assert r.status_code == 400
    assert "ask your manager" in _message(r)
    assert "secret customer" not in _message(r)
