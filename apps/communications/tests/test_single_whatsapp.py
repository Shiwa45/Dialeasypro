"""
Sending one WhatsApp template from the app (APP-M4, APP-M5).

M4: the agent filled in {{1}}, {{2}}... but the backend threw those values
away and used the template's mapping (empty when it had none), while storing
the agent's text as if it had been sent. M5: unapproved templates were
offered and sent, and failed at the provider.
"""
from unittest.mock import MagicMock, patch

import pytest
from django.db import connection
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.communications.models import WhatsAppMessage, WhatsAppTemplate
from apps.communications.tasks import send_single_whatsapp
from apps.communications.views import SendWhatsAppView
from apps.leads.models import Lead

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent():
    return Agent.objects.create_agent(email="a@x.com", name="Asha", password="Pw@12345678")


@pytest.fixture
def lead(agent):
    return Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=agent)


def _template(status="approved", **kw):
    return WhatsAppTemplate.objects.create(
        name=f"offer_{status}", body_text="Hi {{1}}, your visit is on {{2}}.",
        status=status, provider_template_id="offer", **kw,
    )


def _send(agent, **data):
    request = APIRequestFactory().post("/api/v1/comms/whatsapp/send/", data, format="json")
    force_authenticate(request, user=agent)
    request.has_feature = lambda key: True
    with patch("apps.communications.tasks.send_single_whatsapp.apply_async") as queued:
        response = SendWhatsAppView.as_view()(request)
    return response, queued


@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_an_unapproved_template_is_refused(agent, lead, status):
    response, queued = _send(agent, lead_id=lead.pk, template_id=_template(status).pk, message="x")
    assert response.status_code == 400
    assert not queued.called


def test_a_switched_off_template_is_refused(agent, lead):
    template = _template(is_active=False)
    response, queued = _send(agent, lead_id=lead.pk, template_id=template.pk, message="x")
    assert response.status_code == 400


def test_the_agents_values_are_sent_and_recorded(agent, lead):
    template = _template()
    provider = MagicMock()
    provider.send_template.return_value = "wamid.1"

    with patch("apps.communications.tasks._get_whatsapp_provider", return_value=(provider, "interakt")):
        send_single_whatsapp.run(
            connection.schema_name, lead.pk, "whatever the app typed",
            template_id=template.pk, sent_by_id=agent.pk, variables=["Ravi", "Friday 11am"],
        )

    assert provider.send_template.call_args.kwargs["variables"] == ["Ravi", "Friday 11am"]
    stored = WhatsAppMessage.objects.get(lead=lead)
    assert stored.content == "Hi Ravi, your visit is on Friday 11am.", "record what the customer got"


def test_without_values_the_mapping_still_fills_them(agent, lead):
    template = _template(variable_mapping={"1": "name", "2": "city"})
    lead.city = "Pune"
    lead.save(update_fields=["city"])
    provider = MagicMock()
    provider.send_template.return_value = "wamid.2"

    with patch("apps.communications.tasks._get_whatsapp_provider", return_value=(provider, "interakt")):
        send_single_whatsapp.run(connection.schema_name, lead.pk, "", template_id=template.pk)

    assert provider.send_template.call_args.kwargs["variables"] == ["Ravi", "Pune"]
