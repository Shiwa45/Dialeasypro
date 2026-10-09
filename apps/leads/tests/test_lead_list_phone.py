"""
The lead list shows the full phone number.

It was masked (XXXXXX3210) for everyone but admins and managers, so the app's
home screen and Leads screen showed unreadable numbers to agents — for their
own leads, which the detail screen showed in full and which they dial.
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.core.constants import AgentRole
from apps.leads.models import Lead
from apps.leads.views import LeadListCreateView

pytestmark = pytest.mark.django_db


def _list(user):
    request = APIRequestFactory().get("/api/v1/leads/")
    force_authenticate(request, user=user)
    return LeadListCreateView.as_view()(request).data["results"]


@pytest.mark.parametrize("role", [AgentRole.AGENT, AgentRole.SENIOR_AGENT, AgentRole.MANAGER])
def test_the_full_number_is_listed(role):
    agent = Agent.objects.create_agent(email=f"{role}@example.com", name="A", password="Pw@12345678", role=role)
    Lead.objects.create(name="Ravi", phone="+919812345678", assigned_to=agent)

    assert [r["phone"] for r in _list(agent)] == ["+919812345678"]


def test_an_agent_still_sees_only_their_own_leads():
    asha = Agent.objects.create_agent(email="asha@example.com", name="Asha", password="Pw@12345678")
    bilal = Agent.objects.create_agent(email="bilal@example.com", name="Bilal", password="Pw@12345678")
    Lead.objects.create(name="Mine", phone="+919812300001", assigned_to=asha)
    Lead.objects.create(name="Not mine", phone="+919812300002", assigned_to=bilal)

    assert [r["phone"] for r in _list(asha)] == ["+919812300001"]
