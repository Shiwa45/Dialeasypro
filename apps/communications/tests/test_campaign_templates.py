"""
Picking a template for a bulk WhatsApp campaign.

The campaign form's template dropdown was always empty, for every tenant, on
every template they had ever written. Templates are created with
status="pending"; the form asks for approved ones only; and nothing anywhere
— no provider sync, no admin action, no endpoint — could ever move a template
to "approved". Bulk WhatsApp was therefore unreachable through the CRM.

Approval genuinely happens in Meta's Business Manager, so the CRM cannot
decide it. What it can do is let an admin record the answer, which is what
PATCH on a template is for.

The campaign serializer also accepted any template id at all, so a campaign
could be built on a pending template and fail per recipient at send time —
long after whoever launched it had left the screen.
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.communications.models import WhatsAppTemplate
from apps.communications.serializers import BulkCampaignCreateSerializer
from apps.communications.views import (
    CampaignAudiencePreviewView,
    WhatsAppTemplateDetailView,
    WhatsAppTemplateListView,
)
from apps.leads.models import Lead

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(
        email="owner@example.com", name="Owner", password="Pw@12345678",
    )


@pytest.fixture
def agent():
    return Agent.objects.create_agent(
        email="floor@example.com", name="Floor", password="Pw@12345678",
    )


def _template(**overrides):
    fields = {
        "name": "diwali_offer", "category": "marketing", "language": "en",
        "body_text": "Hello {{1}}, our Diwali offer is live.",
    }
    fields.update(overrides)
    return WhatsAppTemplate.objects.create(**fields)


def _patch_template(user, template, **payload):
    request = APIRequestFactory().patch(
        f"/api/v1/comms/whatsapp/templates/{template.pk}/", payload, format="json",
    )
    force_authenticate(request, user=user)
    response = WhatsAppTemplateDetailView.as_view()(request, pk=template.pk)
    response.render()
    return response


def _list_templates(user, **params):
    request = APIRequestFactory().get("/api/v1/comms/whatsapp/templates/", params)
    force_authenticate(request, user=user)
    response = WhatsAppTemplateListView.as_view()(request)
    response.render()
    return response


# ---- A template starts out unusable, and can be made usable ------------

def test_a_new_template_is_pending_and_so_not_offered(admin):
    """Where the empty dropdown came from: nothing is approved by default."""
    _template()

    approved = _list_templates(admin, approved_only="true").data

    assert approved == []


def test_an_admin_can_record_metas_approval(admin):
    """The missing step. Without it the dropdown can never fill."""
    template = _template()

    r = _patch_template(admin, template, status="approved")

    assert r.status_code == 200, r.data
    template.refresh_from_db()
    assert template.status == "approved"


def test_once_approved_it_appears_in_the_campaign_list(admin):
    template = _template()
    _patch_template(admin, template, status="approved")

    names = [t["name"] for t in _list_templates(admin, approved_only="true").data]

    assert "diwali_offer" in names


def test_an_admin_can_record_a_rejection_too(admin):
    template = _template(status="approved")

    _patch_template(admin, template, status="rejected")

    template.refresh_from_db()
    assert template.status == "rejected"


def test_an_admin_can_correct_the_wording(admin):
    template = _template()

    r = _patch_template(admin, template, body_text="Hi {{1}}, the offer ends Friday.")

    assert r.status_code == 200
    template.refresh_from_db()
    assert "ends Friday" in template.body_text


def test_an_agent_cannot_approve_a_template(agent):
    """Approval is a claim about what Meta allows, not a floor-level edit."""
    template = _template()

    r = _patch_template(agent, template, status="approved")

    assert r.status_code == 403
    template.refresh_from_db()
    assert template.status == "pending"


def test_removing_a_template_keeps_it_for_the_record(admin):
    """
    Sent messages and past campaigns point at the template; deleting the row
    would take the record of what was sent with it.
    """
    template = _template(status="approved")

    request = APIRequestFactory().delete(f"/api/v1/comms/whatsapp/templates/{template.pk}/")
    force_authenticate(request, user=admin)
    response = WhatsAppTemplateDetailView.as_view()(request, pk=template.pk)

    assert response.status_code == 204
    template.refresh_from_db()
    assert template.is_active is False
    assert _list_templates(admin, approved_only="true").data == []


# ---- The campaign will not be built on an unusable template ------------

def _campaign_errors(template):
    serializer = BulkCampaignCreateSerializer(data={
        "name": "Diwali blast", "channel": "whatsapp",
        "audience_filters": {}, "template": template.pk,
    })
    serializer.is_valid()
    return serializer.errors


def test_a_campaign_cannot_be_built_on_a_pending_template(admin):
    """
    It used to be accepted, then fail per recipient at send time — the whole
    campaign completing with every message failed.
    """
    errors = _campaign_errors(_template())

    assert "template" in errors
    assert "approved" in str(errors["template"]).lower()


def test_a_campaign_cannot_be_built_on_a_switched_off_template(admin):
    errors = _campaign_errors(_template(status="approved", is_active=False))

    assert "template" in errors


def test_an_approved_template_is_accepted(admin):
    assert "template" not in _campaign_errors(_template(status="approved"))


# ---- Knowing who it reaches, before creating it ------------------------

def _preview(user, filters):
    request = APIRequestFactory().post(
        "/api/v1/comms/campaigns/preview-audience/",
        {"audience_filters": filters}, format="json",
    )
    force_authenticate(request, user=user)
    response = CampaignAudiencePreviewView.as_view()(request)
    response.render()
    return response


def test_the_audience_can_be_counted_before_the_campaign_exists(admin):
    Lead.objects.create(name="A", phone="+919812300001", status="new", city="Pune")
    Lead.objects.create(name="B", phone="+919812300002", status="interested", city="Pune")
    Lead.objects.create(name="C", phone="+919812300003", status="interested", city="Nashik")

    assert _preview(admin, {}).data["count"] == 3
    assert _preview(admin, {"status": "interested"}).data["count"] == 2
    assert _preview(admin, {"city": "pune"}).data["count"] == 2
    assert _preview(admin, {"status": "interested", "city": "Nashik"}).data["count"] == 1


def test_the_preview_says_how_many_are_reachable_on_each_channel(admin):
    """
    400 leads with 12 email addresses is not a 400-recipient email campaign,
    and the count alone would say it was.
    """
    Lead.objects.create(name="A", phone="+919812300011", email="a@example.com")
    Lead.objects.create(name="B", phone="+919812300012")

    data = _preview(admin, {}).data

    assert data["count"] == 2
    assert data["with_phone"] == 2
    assert data["with_email"] == 1


def test_a_malformed_filter_is_refused_rather_than_counted_as_everything(admin):
    request = APIRequestFactory().post(
        "/api/v1/comms/campaigns/preview-audience/",
        {"audience_filters": "status=new"}, format="json",
    )
    force_authenticate(request, user=admin)
    response = CampaignAudiencePreviewView.as_view()(request)
    response.render()

    assert response.status_code == 400
