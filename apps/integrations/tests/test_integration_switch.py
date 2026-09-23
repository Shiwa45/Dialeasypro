"""
Switching a lead source integration on and off.

The CRM had the switch and the switch did nothing. `_get_config()` filtered on
`is_active=True`, so a disabled integration came back as None — indistinguishable
from one that was never configured — and the guard reading
`if config and not config.is_active` could never fire. Deliveries carried on
creating leads, minus the field mapping, duplicate policy and auto-assignment
that the config carries, so switching IndiaMART "off" quietly made its leads
WORSE rather than stopping them.

Switching one back on is gated like creating one: otherwise a tenant at their
plan's cap could switch one off, add another, and switch the first back on.
"""
import json

import pytest
from django.test import RequestFactory
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.core.constants import LeadSource
from apps.integrations.models import LeadSourceConfig, WebhookLog
from apps.integrations.views import (
    IndiaMArtWebhookView,
    IntegrationConfigDetailView,
)
from apps.leads.models import Lead

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(
        email="owner@example.com", name="Owner", password="Pw@12345678",
    )


@pytest.fixture
def indiamart():
    return LeadSourceConfig.objects.create(source=LeadSource.INDIAMART, is_active=True)


def _deliver(phone="9812300001", name="Webhook Lead"):
    """One IndiaMART enquiry, the way their Lead Manager posts it."""
    body = json.dumps({"NAME": name, "MOBILE": phone, "EMAIL": "buyer@example.com"})
    request = RequestFactory().post(
        "/api/v1/integrations/indiamart/", data=body, content_type="application/json",
    )
    return IndiaMArtWebhookView.as_view()(request)


def _patch(actor, config, *, entitled=True, plan=None, **payload):
    """
    PATCH the config the way the Integrations screen does.

    `entitled` and `plan` stand in for TenantFeatureFlagMiddleware, which does
    not run when a view is called directly — switching an integration ON is
    gated on the plan, so the gate has to be given something to read.
    """
    request = APIRequestFactory().patch(
        f"/api/v1/integrations/configs/{config.pk}/", payload, format="json",
    )
    force_authenticate(request, user=actor)
    request.has_feature = lambda key: entitled
    request.tenant_plan = plan
    response = IntegrationConfigDetailView.as_view()(request, pk=config.pk)
    response.render()
    return response


class _Plan:
    """Just the one field the cap is read from."""

    def __init__(self, lead_sources_limit):
        self.lead_sources_limit = lead_sources_limit


# ---- The switch actually switches --------------------------------------

def test_an_active_integration_accepts_its_leads(indiamart):
    response = _deliver(phone="9812300001")

    assert response.status_code == 200
    assert Lead.objects.filter(phone__contains="9812300001").exists()


def test_a_switched_off_integration_refuses_the_delivery(indiamart):
    """The bug: this returned 200 and created the lead anyway."""
    indiamart.is_active = False
    indiamart.save()

    response = _deliver(phone="9812300002")

    assert response.status_code == 403
    assert not Lead.objects.filter(phone__contains="9812300002").exists()


def test_switching_it_back_on_resumes_delivery(indiamart):
    indiamart.is_active = False
    indiamart.save()
    _deliver(phone="9812300003")

    indiamart.is_active = True
    indiamart.save()
    response = _deliver(phone="9812300004")

    assert response.status_code == 200
    assert not Lead.objects.filter(phone__contains="9812300003").exists()
    assert Lead.objects.filter(phone__contains="9812300004").exists()


def test_the_rejection_is_recorded_so_someone_can_see_why(indiamart):
    """
    "We switched it off and cannot tell whether anything is still arriving"
    is answered by the webhook log, not by silence.
    """
    indiamart.is_active = False
    indiamart.save()

    _deliver(phone="9812300005")

    log = WebhookLog.objects.filter(source=LeadSource.INDIAMART).latest("created_at")
    assert log.processed is False
    assert "switched off" in log.error


def test_a_source_that_was_never_configured_is_unaffected(admin):
    """
    No config at all is not the same as one switched off. Tenants receiving
    leads on a source they never opened a config row for must keep receiving
    them — this fix must not silently cut them off.
    """
    assert not LeadSourceConfig.objects.filter(source=LeadSource.INDIAMART).exists()

    response = _deliver(phone="9812300006")

    assert response.status_code == 200
    assert Lead.objects.filter(phone__contains="9812300006").exists()


# ---- What the admin sees -----------------------------------------------

def test_switching_off_shows_as_inactive_not_active(admin, indiamart):
    """`status` sat at "active" on an integration that had just been switched off."""
    r = _patch(admin, indiamart, is_active=False)

    assert r.status_code == 200
    assert r.data["is_active"] is False
    assert r.data["status"] == "inactive"


def test_switching_on_shows_as_active(admin, indiamart):
    indiamart.is_active = False
    indiamart.save()

    r = _patch(admin, indiamart, is_active=True)

    assert r.data["status"] == "active"


def test_a_broken_integration_keeps_saying_so_when_switched_off(admin, indiamart):
    """
    "error" is more informative than "inactive": an admin switching off a
    failing integration should still be able to see what was wrong with it.
    """
    indiamart.status = "error"
    indiamart.error_message = "Invalid credentials"
    indiamart.save()

    r = _patch(admin, indiamart, is_active=False)

    assert r.data["status"] == "error"


def test_switching_off_keeps_the_configuration(admin, indiamart):
    """Off is reversible; the webhook token must survive it or the provider
    has to be reconfigured to turn it back on."""
    token = indiamart.webhook_token

    _patch(admin, indiamart, is_active=False)

    indiamart.refresh_from_db()
    assert indiamart.webhook_token == token


def test_only_an_admin_can_switch_an_integration(indiamart):
    agent = Agent.objects.create_agent(
        email="floor@example.com", name="Floor", password="Pw@12345678",
    )

    r = _patch(agent, indiamart, is_active=False)

    assert r.status_code == 403
    indiamart.refresh_from_db()
    assert indiamart.is_active is True


# ---- Switching ON is gated like creating -------------------------------

def test_switching_on_a_source_the_plan_does_not_include_is_refused(admin, indiamart):
    """
    A downgrade leaves the config row behind. Without this, switching it back
    on resumes a source the tenant no longer pays for.
    """
    indiamart.is_active = False
    indiamart.save()

    r = _patch(admin, indiamart, entitled=False, is_active=True)

    assert r.status_code == 402
    indiamart.refresh_from_db()
    assert indiamart.is_active is False


def test_an_existing_integration_can_be_restored_even_at_the_cap(admin, indiamart):
    """
    The count cap governs ADDING an integration, not putting back one the
    tenant already has. A plan's limit can be lowered after the fact, leaving
    a tenant with more active integrations than it allows; if the cap applied
    here, one of them switching something off to look at it could never switch
    it back on.
    """
    indiamart.is_active = False
    indiamart.save()
    LeadSourceConfig.objects.create(source=LeadSource.GOOGLE_ADS, is_active=True)

    r = _patch(admin, indiamart, plan=_Plan(lead_sources_limit=1), is_active=True)

    assert r.status_code == 200, r.data
    indiamart.refresh_from_db()
    assert indiamart.is_active is True


def test_switching_on_within_the_cap_is_allowed(admin, indiamart):
    indiamart.is_active = False
    indiamart.save()

    r = _patch(admin, indiamart, plan=_Plan(lead_sources_limit=3), is_active=True)

    assert r.status_code == 200
    indiamart.refresh_from_db()
    assert indiamart.is_active is True


def test_switching_OFF_is_never_gated(admin, indiamart):
    """
    A tenant who has lost the feature must still be able to switch the thing
    off — being over your plan is not a reason to be trapped with it running.
    """
    r = _patch(admin, indiamart, entitled=False, plan=_Plan(lead_sources_limit=1), is_active=False)

    assert r.status_code == 200
    indiamart.refresh_from_db()
    assert indiamart.is_active is False


def test_editing_options_on_an_active_integration_is_not_gated(admin, indiamart):
    """Only the off->on transition is a new activation."""
    r = _patch(admin, indiamart, entitled=False, plan=_Plan(lead_sources_limit=1),
               options={"duplicate_action": "update"})

    assert r.status_code == 200
