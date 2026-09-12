"""
What POST /leads/ answers with.

LeadCreateSerializer lists only the writable fields, so the 201 came back
without an id — effectively a copy of what the caller had just sent. The
mobile app parses that response into a Lead whose id is a non-null int, so
every successful creation threw on the client and surfaced as "An unexpected
error occurred". The lead existed. The agent was told it had failed and
retried, which is how duplicates get made.

deal_value was missing from the writable fields too, while both clients send
it on the new-lead form, so an expected deal size typed at creation was
accepted and silently dropped.
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.leads.models import Lead
from apps.leads.views import LeadListCreateView

pytestmark = pytest.mark.django_db


@pytest.fixture
def api():
    """
    The view, driven directly.

    Going through the test Client would need tenant host routing set up for
    every request; the question here is only what the view answers with.
    """
    return Agent.objects.create_tenant_admin(
        email="creator@example.com", name="Creator", password="Pw@12345678",
    )


def _create(agent, **overrides):
    payload = {
        "name": "Ravi Kumar",
        "phone": "+919812345678",
        "source": "manual", "status": "new", "priority": "warm",
    }
    payload.update(overrides)

    request = APIRequestFactory().post("/api/v1/leads/", payload, format="json")
    force_authenticate(request, user=agent)
    response = LeadListCreateView.as_view()(request)
    response.render()
    return response


def test_the_response_carries_the_id(api):
    """Without this the client cannot open, link to, or even name what it made."""
    r = _create(api)

    assert r.status_code == 201
    body = r.data
    assert "id" in body
    assert isinstance(body["id"], int)
    assert Lead.objects.filter(pk=body["id"]).exists()


def test_the_response_is_a_readable_lead_not_an_echo(api):
    """
    The mobile Lead model reads these. A response shaped like the request
    leaves every one of them missing.
    """
    body = _create(api).data

    for field in ("id", "status_display", "source_display", "priority_display",
                  "score", "followup_overdue", "is_dnd", "contact_count",
                  "created_at", "tags"):
        assert field in body, f"{field} missing from the create response"


def test_deal_value_is_stored_not_dropped(api):
    r = _create(api, deal_value="750000")

    assert r.status_code == 201
    assert r.data["deal_value"] is not None
    lead = Lead.objects.get(pk=r.data["id"])
    assert str(lead.deal_value).startswith("750000")


def test_budget_is_still_stored(api):
    """budget already worked; deal_value was added beside it."""
    r = _create(api, budget="500000")

    lead = Lead.objects.get(pk=r.data["id"])
    assert str(lead.budget).startswith("500000")


def test_a_duplicate_phone_still_names_the_field(api):
    """
    The one rejection this endpoint produces. It has to stay legible, because
    the app now shows the field error rather than the envelope's generic text.
    """
    _create(api)
    r = _create(api, name="Ravi Again")

    assert r.status_code == 400
    # The envelope: {"error": ..., "message": "Validation failed.",
    #                "detail": {"phone": [...]}}
    detail = r.data["detail"]
    assert "phone" in detail
    assert "already exists" in str(detail["phone"])


def test_a_rejected_lead_is_not_created(api):
    _create(api)
    _create(api, name="Ravi Again")

    assert Lead.objects.filter(phone="+919812345678").count() == 1
