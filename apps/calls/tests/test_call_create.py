"""
Logging a call from the app (APP-M2, APP-M3).

M2: ended_at was not a serializer field, so every app call was saved with no
end time. M3: nothing checked the agent may see the lead — any agent could log
a call against any lead, marking it worked, moving it from new to attempted,
clearing its queue lock and writing to its history.
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.calls.models import CallLog
from apps.calls.views import CallLogListCreateView
from apps.core.constants import LeadStatus
from apps.leads.models import Lead

pytestmark = pytest.mark.django_db


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="asha@x.com", name="Asha", password="Pw@12345678")


@pytest.fixture
def bilal():
    return Agent.objects.create_agent(email="bilal@x.com", name="Bilal", password="Pw@12345678")


@pytest.fixture(autouse=True)
def answered():
    from apps.calls.models import CallDisposition
    return CallDisposition.objects.create(name="Interested", slug="interested-t", category="connected")


def _log(agent, **data):
    from apps.calls.models import CallDisposition
    body = {"direction": "outbound", "phone_number": "9812300001", "duration_seconds": 42,
            "is_connected": True, "disposition": CallDisposition.objects.get(slug="interested-t").pk, **data}
    request = APIRequestFactory().post("/api/v1/calls/", body, format="json")
    force_authenticate(request, user=agent)
    response = CallLogListCreateView.as_view()(request)
    response.render()
    return response


def test_the_end_time_is_saved(asha):
    lead = Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=asha)

    r = _log(asha, lead=lead.pk, started_at="2026-09-29T09:00:00Z", ended_at="2026-09-29T09:00:42Z")

    assert r.status_code == 201, r.data
    call = CallLog.objects.get(lead=lead)
    assert call.ended_at is not None and call.ended_at.minute == 0 and call.ended_at.second == 42


def test_a_call_cannot_end_before_it_starts(asha):
    lead = Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=asha)

    r = _log(asha, lead=lead.pk, started_at="2026-09-29T09:00:00Z", ended_at="2026-09-29T08:59:00Z")

    assert r.status_code == 400


def test_you_cannot_log_a_call_on_someone_elses_lead(asha, bilal):
    theirs = Lead.objects.create(name="Not yours", phone="+919812300001", assigned_to=bilal)

    r = _log(asha, lead=theirs.pk)

    assert r.status_code == 400
    theirs.refresh_from_db()
    assert theirs.status == LeadStatus.NEW and not theirs.has_been_worked
    assert not CallLog.objects.filter(lead=theirs).exists()
