"""
Meta inbound with several WhatsApp numbers on one tenant.

Every number a tenant connects can point at the same webhook URL. Each
delivery names the business number it reached (metadata.phone_number_id), so
each message is filed under that number's account — and the next reply goes
out from it. Numbers set up on different Meta apps verify with their own
token and sign with their own app secret.
"""
import hashlib
import hmac
import json

import pytest

from apps.communications.models import WhatsAppConfig, WhatsAppMessage
from apps.integrations.tests import meta_whatsapp_payloads as payloads

pytestmark = pytest.mark.django_db

WEBHOOK_URL = "/api/v1/integrations/meta/whatsapp/"
SECOND_PNID = "209000000000001"


def _account(label, pnid, secret, token, inbound=True):
    acct = WhatsAppConfig(
        label=label, provider="meta_cloud", is_active=True, inbound_enabled=inbound,
        create_leads_from_inbound=True,
        credentials={"access_token": "t", "phone_number_id": pnid,
                     "verify_token": token, "app_secret": secret},
    )
    acct.save()
    return acct


@pytest.fixture(autouse=True)
def no_enrichment(settings):
    settings.META_WHATSAPP_ADS_ENRICHMENT = False


@pytest.fixture
def sales():
    return _account("Sales", payloads.PHONE_NUMBER_ID, "secret-sales", "token-sales")


@pytest.fixture
def support():
    return _account("Support", SECOND_PNID, "secret-support", "token-support")


def _post(client, payload, secret):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(WEBHOOK_URL, data=body, content_type="application/json",
                       HTTP_X_HUB_SIGNATURE_256=sig)


def test_each_number_verifies_with_its_own_token(client, sales, support):
    for token in ("token-sales", "token-support"):
        response = client.get(WEBHOOK_URL, {"hub.mode": "subscribe", "hub.verify_token": token,
                                            "hub.challenge": "42"})
        assert response.status_code == 200 and response.content == b"42"
    bad = client.get(WEBHOOK_URL, {"hub.mode": "subscribe", "hub.verify_token": "nope",
                                   "hub.challenge": "42"})
    assert bad.status_code == 403


def test_a_delivery_signed_by_the_second_app_is_accepted(client, sales, support):
    payload = payloads.text_message(message_id="wamid.s2", phone_number_id=SECOND_PNID)
    assert _post(client, payload, "secret-support").status_code == 200
    assert _post(client, payloads.text_message(message_id="wamid.x"), "forged").status_code == 401


def test_a_message_is_filed_under_the_number_it_reached(client, sales, support):
    _post(client, payloads.text_message(message_id="wamid.a1"), "secret-sales")
    _post(client, payloads.text_message(message_id="wamid.b1", phone_number_id=SECOND_PNID),
          "secret-support")
    assert WhatsAppMessage.objects.get(provider_message_id="wamid.a1").account == sales
    assert WhatsAppMessage.objects.get(provider_message_id="wamid.b1").account == support

    support.refresh_from_db()
    sales.refresh_from_db()
    assert support.total_inbound_messages == 1 and support.last_webhook_at is not None
    assert sales.total_inbound_messages == 1


def test_the_reply_goes_out_from_the_number_the_customer_wrote_to(client, sales, support):
    from apps.communications.whatsapp_accounts import resolve_sender

    _post(client, payloads.text_message(message_id="wamid.c1", phone_number_id=SECOND_PNID),
          "secret-support")
    lead = WhatsAppMessage.objects.get(provider_message_id="wamid.c1").lead
    assert resolve_sender(lead=lead).account == support


def test_a_number_with_inbound_off_is_not_recorded(client, sales):
    _account("Support", SECOND_PNID, "secret-support", "token-support", inbound=False)
    response = _post(client, payloads.text_message(message_id="wamid.d1", phone_number_id=SECOND_PNID),
                     "secret-support")
    assert response.status_code == 200
    assert not WhatsAppMessage.objects.filter(provider_message_id="wamid.d1").exists()


def test_an_unknown_number_falls_back_to_the_default_account(client, sales):
    _post(client, payloads.text_message(message_id="wamid.e1", phone_number_id="unknown-pn"),
          "secret-sales")
    assert WhatsAppMessage.objects.get(provider_message_id="wamid.e1").account == sales
