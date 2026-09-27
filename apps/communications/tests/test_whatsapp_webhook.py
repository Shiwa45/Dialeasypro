"""
WhatsApp provider webhooks — replies and receipts reach the CRM.

MED-6: a number on two leads raised MultipleObjectsReturned, swallowed — the
reply was lost. MED-7: "+91" was prefixed to any number without "+", so
"919812345678" became "+91919812345678" and matched nothing. MED-8: only
Interakt was parsed; WATI, Gupshup and Meta Cloud posts were thrown away.
"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.communications.models import WhatsAppMessage
from apps.communications.views import WhatsAppWebhookView
from apps.leads.models import Lead

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def quiet_notifications():
    with patch("apps.core.consumers.send_agent_notification"):
        yield


def _token():
    from apps.communications.models import WhatsAppConfig

    return WhatsAppConfig.get_solo().webhook_token


def _post(provider, payload, *, token=None, expect=200):
    token = _token() if token is None else token
    request = APIRequestFactory().post(
        f"/api/v1/comms/webhook/whatsapp/{provider}/?token={token}", payload, format="json")
    response = WhatsAppWebhookView.as_view()(request, provider=provider)
    assert response.status_code == expect
    return response


def _interakt_reply(phone, text="Interested", msg_id="wamid.1"):
    return {"type": "inbound_message", "data": {
        "customer_phone_number": phone, "wa_message_id": msg_id,
        "message": {"text": {"body": text}},
    }}


def _replies():
    return list(WhatsAppMessage.objects.filter(direction="inbound").values_list("lead__name", "content"))


# ---- MED-6 / MED-7 -----------------------------------------------------

def test_a_number_on_two_leads_still_gets_its_reply():
    Lead.objects.create(name="Old copy", phone="+919812300001")
    recent = Lead.objects.create(name="Recent copy", phone="+919812300001")
    Lead.objects.filter(pk=recent.pk).update(last_contacted_at=timezone.now())

    _post("interakt", _interakt_reply("9812300001"))

    assert _replies() == [("Recent copy", "Interested")]


@pytest.mark.parametrize("sent_as", ["9812300002", "919812300002", "+919812300002"])
def test_the_country_code_is_not_added_twice(sent_as):
    Lead.objects.create(name="Asha", phone="+919812300002")

    _post("interakt", _interakt_reply(sent_as))

    assert _replies() == [("Asha", "Interested")]


def test_the_alternate_phone_counts():
    Lead.objects.create(name="Asha", phone="+919812300003", alternate_phone="+919812300004")

    _post("interakt", _interakt_reply("919812300004"))

    assert _replies() == [("Asha", "Interested")]


def test_a_retried_webhook_is_recorded_once():
    Lead.objects.create(name="Asha", phone="+919812300005")

    _post("interakt", _interakt_reply("919812300005", msg_id="wamid.same"))
    _post("interakt", _interakt_reply("919812300005", msg_id="wamid.same"))

    assert len(_replies()) == 1


# ---- MED-8: the other providers ----------------------------------------

@pytest.mark.parametrize("provider,payload", [
    ("wati", {"eventType": "message", "waId": "919812300010", "text": "Interested",
              "id": "w1", "type": "text", "owner": False}),
    ("gupshup", {"type": "message", "payload": {
        "id": "g1", "source": "919812300010", "type": "text", "payload": {"text": "Interested"}}}),
    ("meta_cloud", {"object": "whatsapp_business_account", "entry": [{"id": "waba", "changes": [{
        "field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "919000000000", "phone_number_id": "pn1"},
            "contacts": [{"wa_id": "919812300010", "profile": {"name": "Asha"}}],
            "messages": [{"id": "m1", "from": "919812300010", "timestamp": "1760000000",
                          "type": "text", "text": {"body": "Interested"}}],
        }}]}]}),
])
def test_replies_from_every_provider_are_recorded(provider, payload):
    Lead.objects.create(name="Asha", phone="+919812300010")

    _post(provider, payload)

    assert _replies() == [("Asha", "Interested")]


def _outbound(provider_message_id, status="sent"):
    lead = Lead.objects.create(name="Asha", phone="+919812300020")
    return WhatsAppMessage.objects.create(
        lead=lead, direction="outbound", content="Hi", status=status,
        provider_message_id=provider_message_id,
    )


@pytest.mark.parametrize("provider,payload,expected", [
    ("wati", {"eventType": "sentMessageDELIVERED_v2", "id": "abc"}, "delivered"),
    ("wati", {"eventType": "sentMessageREAD", "localMessageId": "abc"}, "read"),
    ("gupshup", {"type": "message-event", "payload": {"id": "abc", "type": "read"}}, "read"),
    ("gupshup", {"type": "message-event", "payload": {"gsId": "abc", "type": "delivered"}}, "delivered"),
    ("meta_cloud", {"object": "whatsapp_business_account", "entry": [{"id": "waba", "changes": [{
        "field": "messages", "value": {
            "metadata": {"phone_number_id": "pn1"},
            "statuses": [{"id": "abc", "status": "delivered", "timestamp": "1760000000",
                          "recipient_id": "919812300020"}],
        }}]}]}, "delivered"),
])
def test_delivery_receipts_from_every_provider_are_recorded(provider, payload, expected):
    message = _outbound("abc")

    _post(provider, payload)

    message.refresh_from_db()
    assert message.status == expected


def test_a_late_delivered_does_not_undo_read():
    message = _outbound("abc", status="read")

    _post("interakt", {"type": "message_status", "data": {"message_id": "abc", "status": "delivered"}})

    message.refresh_from_db()
    assert message.status == "read"


def test_an_unknown_provider_is_answered_but_not_guessed_at():
    _post("aisensy", {"anything": "at all"})

    assert not WhatsAppMessage.objects.exists()


# ---- CRIT-5: the webhook must carry the tenant's token -----------------

@pytest.mark.parametrize("token", ["", "guessed"])
def test_a_forged_reply_is_refused(token):
    Lead.objects.create(name="Asha", phone="+919812300060")

    _post("interakt", _interakt_reply("919812300060", "click this link"), token=token, expect=401)

    assert _replies() == []


def test_a_forged_receipt_is_refused():
    message = _outbound("abc")

    _post("interakt", {"type": "message_status", "data": {"message_id": "abc", "status": "read"}},
          token="guessed", expect=401)

    message.refresh_from_db()
    assert message.status == "sent"


def test_settings_show_the_url_to_give_the_provider():
    from apps.communications.models import WhatsAppConfig
    from apps.communications.serializers import WhatsAppConfigSerializer

    config = WhatsAppConfig.get_solo()
    data = WhatsAppConfigSerializer(config).data

    assert data["webhook"]["status_url"].endswith(f"?token={config.webhook_token}")
