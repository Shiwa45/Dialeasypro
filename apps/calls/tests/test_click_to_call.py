"""
Click-to-call: what happens to the lead, and what the agent is told.

MED-4: the lead was marked worked (contact count up, New -> Attempted) before
dialling, so a call that failed still counted as an attempt.
MED-5: the provider is one platform-wide setting, and Exotel / MCUBE were
stubs that raise — choosing either broke click-to-call for every tenant.
LOW-3: manual mode dials nothing, yet the reply said "your phone will ring".
"""
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.calls import views as call_views
from apps.calls.models import CallLog
from apps.core.constants import LeadStatus
from apps.leads.models import Lead

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent():
    return Agent.objects.create_agent(email="a@x.com", name="Asha", password="Pw@12345678")


@pytest.fixture
def lead(agent):
    return Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=agent)


def _call(agent, lead):
    request = APIRequestFactory().post(
        "/api/v1/calls/click-to-call/", {"lead_id": lead.pk}, format="json")
    force_authenticate(request, user=agent)
    request.has_feature = lambda key: True
    response = call_views.ClickToCallView.as_view()(request)
    response.render()
    lead.refresh_from_db()
    return response


def _provider(name):
    return patch("apps.superadmin.models.GlobalSettings.get", return_value=name)


def test_a_failed_call_does_not_count_as_an_attempt(agent, lead):
    with patch.object(call_views, "_initiate_provider_call", side_effect=RuntimeError("down")):
        response = _call(agent, lead)

    assert response.status_code == 503
    assert lead.contact_count == 0
    assert lead.status == LeadStatus.NEW
    assert not lead.has_been_worked
    assert not CallLog.objects.filter(lead=lead).exists()


def test_a_successful_call_does(agent, lead):
    with _provider("manual"):
        response = _call(agent, lead)

    assert response.status_code == 200
    assert lead.contact_count == 1
    assert lead.status == LeadStatus.ATTEMPTED


@pytest.mark.parametrize("provider", ["exotel", "mcube"])
def test_an_unintegrated_provider_does_not_break_calling(agent, lead, provider):
    with _provider(provider):
        response = _call(agent, lead)

    assert response.status_code == 200
    assert CallLog.objects.get(lead=lead).provider == "manual"


def test_manual_mode_does_not_promise_a_ring(agent, lead):
    with _provider("manual"):
        data = _call(agent, lead).data

    assert data["dialed"] is False
    assert "ring" not in data["message"].lower()
    assert lead.phone in data["message"]


def test_a_real_provider_says_the_phone_will_ring(agent, lead):
    def fake_dialer(agent_phone, lead_phone):
        return {"provider": "exotel", "call_id": "EX123"}

    with _provider("exotel"), patch.dict(call_views.PROVIDER_DIALERS, {"exotel": fake_dialer}):
        data = _call(agent, lead).data

    assert data["dialed"] is True
    assert "ring" in data["message"].lower()
