"""
Opening the phone's own WhatsApp from the app leaves a trace (APP-L3).
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.communications.views import LogNativeWhatsAppView
from apps.leads.models import Lead, LeadActivity

pytestmark = pytest.mark.django_db


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="asha@x.com", name="Asha", password="Pw@12345678")


def _log(agent, **data):
    request = APIRequestFactory().post("/api/v1/comms/whatsapp/log-native/", data, format="json")
    force_authenticate(request, user=agent)
    return LogNativeWhatsAppView.as_view()(request)


def test_the_open_is_recorded_on_the_lead(asha):
    lead = Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=asha)

    assert _log(asha, lead_id=lead.pk, message="Sharing the brochure").status_code == 201

    activity = LeadActivity.objects.get(lead=lead, activity_type="whatsapp")
    assert "Sharing the brochure" in activity.description
    assert activity.performed_by == asha
    lead.refresh_from_db()
    assert lead.contact_count == 1


def test_not_on_someone_elses_lead(asha):
    bilal = Agent.objects.create_agent(email="b@x.com", name="Bilal", password="Pw@12345678")
    theirs = Lead.objects.create(name="Not yours", phone="+919812300002", assigned_to=bilal)

    assert _log(asha, lead_id=theirs.pk).status_code == 404
    assert not LeadActivity.objects.filter(lead=theirs, activity_type="whatsapp").exists()
