"""
Opening a lead you no longer have says why.

The detail endpoint answered every refusal with a bare 404, and the app
printed "status code of 404". It is usually an ordinary event — a
notification or follow-up for a lead since reassigned or deleted — so the
response now names the reason, without saying who has the lead now.
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.leads.models import Lead
from apps.leads.views import LeadDetailView

pytestmark = pytest.mark.django_db


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="asha@example.com", name="Asha", password="Pw@12345678")


@pytest.fixture
def bilal():
    return Agent.objects.create_agent(email="bilal@example.com", name="Bilal", password="Pw@12345678")


def _open(user, pk):
    request = APIRequestFactory().get(f"/api/v1/leads/{pk}/")
    force_authenticate(request, user=user)
    response = LeadDetailView.as_view()(request, pk=pk)
    response.render()
    return response


def test_a_lead_given_to_someone_else_says_so(asha, bilal):
    lead = Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=bilal)

    r = _open(asha, lead.pk)

    assert r.status_code == 404
    assert r.data["error"] == "lead_not_assigned"
    assert r.data["message"] == "This lead is no longer assigned to you."
    assert "Bilal" not in str(r.data), "who has it now is not disclosed"


def test_a_deleted_lead_says_it_was_deleted(asha):
    lead = Lead.objects.create(name="Ravi", phone="+919812300002", assigned_to=asha, is_deleted=True)

    r = _open(asha, lead.pk)

    assert r.status_code == 404
    assert r.data["error"] == "lead_deleted"


def test_a_lead_that_never_existed_is_a_plain_not_found(asha):
    r = _open(asha, 999999)

    assert r.status_code == 404
    assert r.data["error"] not in ("lead_not_assigned", "lead_deleted")


def test_the_agent_own_lead_still_opens(asha):
    lead = Lead.objects.create(name="Ravi", phone="+919812300003", assigned_to=asha)

    assert _open(asha, lead.pk).status_code == 200
