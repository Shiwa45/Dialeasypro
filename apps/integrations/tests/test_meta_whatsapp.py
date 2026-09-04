"""
TeleCRM Backend — apps/integrations/tests/test_meta_whatsapp.py

Meta Click-to-WhatsApp → CRM.

Covers the contract that matters in production: Meta's verification handshake,
signature enforcement, idempotent processing of retried deliveries, and the
contact/conversation/message/lead rules — including the attribution rules,
where the important behaviour is what the integration does NOT do (invent a
campaign name Meta never sent).
"""
import hashlib
import hmac
import json
from unittest import mock

import pytest

from apps.communications.models import (
    WhatsAppConfig, WhatsAppConversation, WhatsAppMessage,
)
from apps.core.constants import LeadSource, LeadStatus
from apps.integrations.meta_whatsapp import MetaWhatsAppError
from apps.integrations.models import MetaWhatsAppEvent, WebhookLog
from apps.integrations.tests import meta_whatsapp_payloads as payloads
from apps.leads.models import Lead, LeadActivity

APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"

WEBHOOK_URL = "/api/v1/integrations/meta/whatsapp/"


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def config(db):
    """An inbound-enabled Meta Cloud connection for the test tenant."""
    conf = WhatsAppConfig.get_solo()
    conf.provider = "meta_cloud"
    conf.is_active = True
    conf.inbound_enabled = True
    conf.create_leads_from_inbound = True
    conf.credentials = {
        "access_token": "test-access-token",
        "phone_number_id": payloads.PHONE_NUMBER_ID,
        "business_account_id": payloads.WABA_ID,
        "verify_token": VERIFY_TOKEN,
        "app_secret": APP_SECRET,
    }
    conf.save()
    return conf


def sign(body: bytes, secret: str = APP_SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def post_webhook(client, payload: dict, *, secret: str = APP_SECRET, signature=None):
    """POST a delivery the way Meta does — signed over the exact raw body."""
    body = json.dumps(payload).encode()
    return client.post(
        WEBHOOK_URL,
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature if signature is not None else sign(body, secret),
    )


@pytest.fixture
def no_enrichment(settings):
    """
    Default the Marketing API lookup off.

    Enrichment is a live HTTP call; tests that care about it turn it on and
    mock the transport, and every other test must not depend on the network.
    """
    settings.META_WHATSAPP_ADS_ENRICHMENT = False


pytestmark = pytest.mark.django_db


# ============================================================
# 1. Webhook verification (GET)
# ============================================================

def test_verification_returns_challenge(client, config, no_enrichment):
    response = client.get(WEBHOOK_URL, {
        "hub.mode": "subscribe",
        "hub.verify_token": VERIFY_TOKEN,
        "hub.challenge": "1158201444",
    })
    assert response.status_code == 200
    assert response.content.decode() == "1158201444"


def test_verification_rejects_wrong_token(client, config, no_enrichment):
    response = client.get(WEBHOOK_URL, {
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong-token",
        "hub.challenge": "1158201444",
    })
    assert response.status_code == 403
    # The challenge must not be echoed to an unverified caller.
    assert b"1158201444" not in response.content


def test_verification_rejects_when_no_token_configured(client, db, no_enrichment, settings):
    """A tenant that never set a verify token cannot be verified by anyone."""
    settings.META_VERIFY_TOKEN = ""
    conf = WhatsAppConfig.get_solo()
    conf.credentials = {}
    conf.save()

    response = client.get(WEBHOOK_URL, {
        "hub.mode": "subscribe",
        "hub.verify_token": "",
        "hub.challenge": "abc",
    })
    assert response.status_code == 403


# ============================================================
# 2/3. Delivery acceptance and signature enforcement (POST)
# ============================================================

def test_valid_message_creates_lead_conversation_and_message(client, config, no_enrichment):
    response = post_webhook(client, payloads.ctwa_message())
    assert response.status_code == 200

    lead = Lead.objects.get(phone="+919876543210")
    assert lead.name == "Rahul Sharma"
    assert lead.source == LeadSource.META_CTWA
    assert lead.status == LeadStatus.NEW

    conversation = WhatsAppConversation.objects.get(lead=lead)
    assert conversation.status == WhatsAppConversation.STATUS_OPEN
    assert conversation.business_phone_number_id == payloads.PHONE_NUMBER_ID
    assert conversation.message_count == 1

    message = WhatsAppMessage.objects.get(conversation=conversation)
    assert message.direction == "inbound"
    assert message.content == "Hi, I want more information."
    assert message.status == "received"
    assert message.wa_timestamp is not None


def test_invalid_signature_is_rejected(client, config, no_enrichment):
    response = post_webhook(client, payloads.ctwa_message(), secret="wrong-secret")
    assert response.status_code == 401
    assert not Lead.objects.exists()
    assert not WebhookLog.objects.exists()


def test_missing_signature_is_rejected(client, config, no_enrichment):
    body = json.dumps(payloads.ctwa_message()).encode()
    response = client.post(WEBHOOK_URL, data=body, content_type="application/json")
    assert response.status_code == 401
    assert not Lead.objects.exists()


def test_body_tampering_invalidates_the_signature(client, config, no_enrichment):
    """The digest covers the raw body, so an altered phone number fails."""
    original = payloads.ctwa_message()
    signature = sign(json.dumps(original).encode())

    tampered = payloads.ctwa_message(wa_id="919999999999")
    response = client.post(
        WEBHOOK_URL,
        data=json.dumps(tampered).encode(),
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )
    assert response.status_code == 401


def test_disabled_inbound_discards_delivery(client, db, no_enrichment):
    conf = WhatsAppConfig.get_solo()
    conf.inbound_enabled = False
    conf.credentials = {"app_secret": APP_SECRET, "verify_token": VERIFY_TOKEN}
    conf.save()

    response = post_webhook(client, payloads.ctwa_message())
    # 200, not an error: retrying will not switch the integration on, and Meta
    # disables endpoints that keep failing.
    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    assert not Lead.objects.exists()


# ============================================================
# 4. Idempotency
# ============================================================

def test_duplicate_delivery_creates_nothing_twice(client, config, no_enrichment):
    payload = payloads.ctwa_message()

    assert post_webhook(client, payload).status_code == 200
    assert post_webhook(client, payload).status_code == 200
    assert post_webhook(client, payload).status_code == 200

    assert Lead.objects.count() == 1
    assert WhatsAppConversation.objects.count() == 1
    assert WhatsAppMessage.objects.count() == 1

    conversation = WhatsAppConversation.objects.get()
    assert conversation.message_count == 1

    event = MetaWhatsAppEvent.objects.get(message_id=payload["entry"][0]["changes"][0]["value"]["messages"][0]["id"])
    assert event.status == MetaWhatsAppEvent.STATUS_PROCESSED


def test_dedupe_key_is_unique_per_event(client, config, no_enrichment):
    post_webhook(client, payloads.ctwa_message())
    post_webhook(client, payloads.ctwa_message())
    assert MetaWhatsAppEvent.objects.count() == 1


# ============================================================
# 5/6. Contact handling
# ============================================================

def test_existing_contact_is_reused_not_duplicated(client, config, no_enrichment):
    existing = Lead.objects.create(
        name="Rahul S (from IndiaMART)",
        phone="+919876543210",
        email="rahul@example.com",
        city="Delhi",
        source=LeadSource.INDIAMART,
        status=LeadStatus.CONTACTED,
    )

    post_webhook(client, payloads.ctwa_message())

    assert Lead.objects.count() == 1
    existing.refresh_from_db()
    # Human-entered CRM data survives: the WhatsApp profile name must not
    # overwrite a name someone already curated, nor the source, nor the email.
    assert existing.name == "Rahul S (from IndiaMART)"
    assert existing.email == "rahul@example.com"
    assert existing.city == "Delhi"
    assert existing.source == LeadSource.INDIAMART
    assert existing.last_contacted_at is not None


def test_profile_name_fills_a_placeholder_name_only(client, config, no_enrichment):
    lead = Lead.objects.create(name="Unknown", phone="+919876543210")
    post_webhook(client, payloads.ctwa_message())
    lead.refresh_from_db()
    assert lead.name == "Rahul Sharma"


def test_new_contact_is_created_with_normalized_phone(client, config, no_enrichment):
    post_webhook(client, payloads.ctwa_message())
    lead = Lead.objects.get()
    # Meta sends a bare wa_id; the CRM stores E.164 like every other source.
    assert lead.phone == "+919876543210"
    assert lead.source_meta["wa_id"] == payloads.CUSTOMER_WA_ID


def test_lead_creation_can_be_switched_off(client, config, no_enrichment):
    config.create_leads_from_inbound = False
    config.save()

    response = post_webhook(client, payloads.ctwa_message())
    assert response.status_code == 200
    assert not Lead.objects.exists()


def test_ctwa_only_mode_ignores_organic_inbound(client, config, no_enrichment):
    config.ctwa_leads_only = True
    config.save()

    post_webhook(client, payloads.text_message())      # no referral
    assert not Lead.objects.exists()

    post_webhook(client, payloads.ctwa_message(message_id="wamid.AD1"))
    assert Lead.objects.count() == 1


# ============================================================
# 7/8. Conversation handling
# ============================================================

def test_second_message_reuses_the_open_conversation(client, config, no_enrichment):
    post_webhook(client, payloads.ctwa_message(message_id="wamid.ONE"))
    post_webhook(client, payloads.text_message(
        message_id="wamid.TWO", text="Any update?",
    ))

    assert WhatsAppConversation.objects.count() == 1
    conversation = WhatsAppConversation.objects.get()
    assert conversation.message_count == 2
    assert conversation.messages.count() == 2
    # The follow-up carried no referral; the ad attribution must survive.
    assert conversation.is_ad_referred is True
    assert conversation.referral_source_id == payloads.AD_ID


def test_a_different_ad_opens_a_new_conversation(client, config, no_enrichment):
    post_webhook(client, payloads.ctwa_message(message_id="wamid.AD_A"))
    post_webhook(client, payloads.ctwa_message(
        message_id="wamid.AD_B",
        referral=payloads.ctwa_referral(ad_id="99999", headline="New Year Offer"),
    ))

    assert Lead.objects.count() == 1
    assert WhatsAppConversation.objects.count() == 2
    # Exactly one open thread — the partial unique index guarantees it.
    assert WhatsAppConversation.objects.filter(status="open").count() == 1

    newest = WhatsAppConversation.objects.filter(status="open").get()
    assert newest.referral_source_id == "99999"
    assert newest.referral_headline == "New Year Offer"

    closed = WhatsAppConversation.objects.filter(status="closed").get()
    assert closed.referral_source_id == payloads.AD_ID


def test_a_referral_on_an_open_organic_thread_is_recorded(client, config, no_enrichment):
    post_webhook(client, payloads.text_message(message_id="wamid.ORGANIC"))
    conversation = WhatsAppConversation.objects.get()
    assert conversation.is_ad_referred is False

    post_webhook(client, payloads.ctwa_message(message_id="wamid.THEN_AD"))
    conversation.refresh_from_db()
    assert conversation.is_ad_referred is True
    assert conversation.referral_source_id == payloads.AD_ID
    assert WhatsAppConversation.objects.count() == 1


# ============================================================
# 9/10. Lead creation and update rules
# ============================================================

def test_messages_do_not_create_a_lead_each(client, config, no_enrichment):
    for i in range(4):
        post_webhook(client, payloads.text_message(message_id=f"wamid.M{i}"))
    assert Lead.objects.count() == 1
    assert WhatsAppMessage.objects.count() == 4


def test_closed_lead_is_reopened_on_a_new_message(client, config, no_enrichment):
    lead = Lead.objects.create(
        name="Rahul", phone="+919876543210", status=LeadStatus.LOST,
    )
    post_webhook(client, payloads.ctwa_message())
    lead.refresh_from_db()
    assert lead.status == LeadStatus.NEW


def test_reopening_can_be_switched_off(client, config, no_enrichment):
    config.reopen_lead_on_inbound = False
    config.save()
    lead = Lead.objects.create(
        name="Rahul", phone="+919876543210", status=LeadStatus.LOST,
    )
    post_webhook(client, payloads.ctwa_message())
    lead.refresh_from_db()
    assert lead.status == LeadStatus.LOST


def test_converted_lead_is_never_dragged_back_to_new(client, config, no_enrichment):
    """A won deal messaging in is a customer, not a fresh lead."""
    lead = Lead.objects.create(
        name="Rahul", phone="+919876543210", status=LeadStatus.CONVERTED,
    )
    post_webhook(client, payloads.ctwa_message())
    lead.refresh_from_db()
    assert lead.status == LeadStatus.CONVERTED


def test_inbound_message_is_logged_on_the_activity_feed(client, config, no_enrichment):
    Lead.objects.create(name="Rahul", phone="+919876543210")
    post_webhook(client, payloads.ctwa_message())

    activity = LeadActivity.objects.filter(activity_type="whatsapp").get()
    assert "Hi, I want more information." in activity.description
    assert activity.meta["direction"] == "inbound"


def test_new_lead_is_assigned_to_the_configured_agent(client, config, no_enrichment):
    from apps.authentication.models import Agent

    agent = Agent.objects.create_agent(
        email="inbound@testrealty.test", name="Inbound Owner", password="x",
    )
    config.inbound_assign_to = agent
    config.save()

    post_webhook(client, payloads.ctwa_message())
    lead = Lead.objects.get(phone="+919876543210")
    assert lead.assigned_to_id == agent.pk
    assert lead.assigned_at is not None


# ============================================================
# 11/12. Meta ad attribution
# ============================================================

def test_referral_attribution_is_stored(client, config, no_enrichment):
    post_webhook(client, payloads.ctwa_message())
    conversation = WhatsAppConversation.objects.get()

    assert conversation.is_ad_referred is True
    assert conversation.referral_source_type == "ad"
    assert conversation.referral_source_id == payloads.AD_ID
    assert conversation.meta_ad_id == payloads.AD_ID
    assert conversation.referral_headline == "Diwali Offer"
    assert conversation.ctwa_clid == "ARAaBbCcDdEeFfGg1234567890"
    # The raw object is kept whole for anything not modelled.
    assert conversation.referral_payload["source_url"].endswith(payloads.AD_ID)


def test_names_are_never_invented_without_enrichment(client, config, no_enrichment):
    """
    Meta's webhook has no campaign/ad-set/ad NAME in it.

    With the Marketing API lookup off, those columns must stay empty — a
    placeholder here would show a sales rep a campaign that does not exist.
    """
    post_webhook(client, payloads.ctwa_message())
    conversation = WhatsAppConversation.objects.get()

    assert conversation.meta_campaign_id == ""
    assert conversation.meta_campaign_name == ""
    assert conversation.meta_adset_name == ""
    assert conversation.meta_ad_name == ""
    assert "campaign_name" not in conversation.attribution

    lead = Lead.objects.get()
    assert lead.campaign_name == ""
    assert lead.ad_name == ""


def test_missing_attribution_leaves_every_ad_field_empty(client, config, no_enrichment):
    """An organic message must not be dressed up as ad traffic."""
    post_webhook(client, payloads.text_message())
    conversation = WhatsAppConversation.objects.get()

    assert conversation.is_ad_referred is False
    assert conversation.referral_source_id == ""
    assert conversation.referral_payload == {}
    assert conversation.attribution == {}

    lead = Lead.objects.get()
    assert lead.source == LeadSource.WHATSAPP


def test_enrichment_fills_campaign_names(client, config, settings):
    settings.META_WHATSAPP_ADS_ENRICHMENT = True

    graph_response = mock.Mock(status_code=200)
    graph_response.json.return_value = {
        "id": payloads.AD_ID,
        "name": "Discount Ad",
        "adset": {"id": "6123", "name": "Delhi Audience"},
        "campaign": {"id": "6987", "name": "Diwali Offer"},
    }

    with mock.patch("apps.integrations.meta_whatsapp.requests.get", return_value=graph_response) as get:
        post_webhook(client, payloads.ctwa_message())

    conversation = WhatsAppConversation.objects.get()
    assert conversation.meta_campaign_name == "Diwali Offer"
    assert conversation.meta_adset_name == "Delhi Audience"
    assert conversation.meta_ad_name == "Discount Ad"
    assert conversation.attribution_enriched_at is not None

    # The token must travel as a parameter, never in the URL path or a log.
    assert payloads.AD_ID in get.call_args.args[0]
    assert get.call_args.kwargs["params"]["access_token"] == "test-access-token"

    # The names mirror onto the lead's existing campaign columns.
    lead = Lead.objects.get()
    assert lead.campaign_name == "Diwali Offer"
    assert lead.ad_name == "Discount Ad"


def test_enrichment_does_not_overwrite_a_curated_campaign_name(client, config, settings):
    settings.META_WHATSAPP_ADS_ENRICHMENT = True
    Lead.objects.create(
        name="Rahul", phone="+919876543210", campaign_name="Manually tagged",
    )

    graph_response = mock.Mock(status_code=200)
    graph_response.json.return_value = {
        "id": payloads.AD_ID, "name": "Discount Ad",
        "campaign": {"id": "6987", "name": "Diwali Offer"},
    }
    with mock.patch("apps.integrations.meta_whatsapp.requests.get", return_value=graph_response):
        post_webhook(client, payloads.ctwa_message())

    assert Lead.objects.get().campaign_name == "Manually tagged"


# ============================================================
# 13. Malformed and unsupported payloads
# ============================================================

def test_malformed_json_is_rejected_without_retry(client, config, no_enrichment):
    body = b"{not json at all"
    response = client.post(
        WEBHOOK_URL, data=body, content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sign(body),
    )
    assert response.status_code == 400
    assert not Lead.objects.exists()


def test_structurally_invalid_payload_is_ignored(client, config, no_enrichment):
    response = post_webhook(client, payloads.malformed_payload())
    assert response.status_code == 200
    assert not Lead.objects.exists()


def test_unsupported_event_type_is_ignored(client, config, no_enrichment):
    response = post_webhook(client, payloads.unsupported_event())
    assert response.status_code == 200
    assert not Lead.objects.exists()
    assert not MetaWhatsAppEvent.objects.exists()


def test_message_without_an_id_is_skipped(client, config, no_enrichment):
    """No wamid means no idempotency key, so the message cannot be trusted."""
    response = post_webhook(client, payloads.message_without_id())
    assert response.status_code == 200
    assert not Lead.objects.exists()


def test_media_message_is_stored_with_its_metadata(client, config, no_enrichment):
    post_webhook(client, payloads.image_message())

    message = WhatsAppMessage.objects.get()
    assert message.message_type == "image"
    assert message.content == "Is this layout still available?"
    assert message.metadata["media"]["media_id"] == "1479537139276761"
    assert message.metadata["media"]["mime_type"] == "image/jpeg"


# ============================================================
# 14. Meta API failure
# ============================================================

def test_graph_failure_does_not_lose_the_lead(client, config, settings):
    """
    Enrichment needs `ads_read`; a WhatsApp-only token gets a 190 back.

    That is a configuration problem to surface, never a reason to drop the
    lead the customer just became.
    """
    settings.META_WHATSAPP_ADS_ENRICHMENT = True

    graph_response = mock.Mock(status_code=400)
    graph_response.json.return_value = {
        "error": {"message": "(#200) Ads management permission required", "code": 200},
    }
    with mock.patch("apps.integrations.meta_whatsapp.requests.get", return_value=graph_response):
        response = post_webhook(client, payloads.ctwa_message())

    assert response.status_code == 200
    lead = Lead.objects.get()
    assert lead.source == LeadSource.META_CTWA

    conversation = WhatsAppConversation.objects.get()
    assert conversation.meta_campaign_name == ""
    assert "Ads management permission required" in conversation.attribution_error
    # The ad id from the webhook is still there — only the names are missing.
    assert conversation.meta_ad_id == payloads.AD_ID


def test_graph_network_error_is_contained(client, config, settings):
    import requests as req

    settings.META_WHATSAPP_ADS_ENRICHMENT = True
    with mock.patch(
        "apps.integrations.meta_whatsapp.requests.get",
        side_effect=req.ConnectionError("connection reset"),
    ):
        response = post_webhook(client, payloads.ctwa_message())

    assert response.status_code == 200
    assert Lead.objects.count() == 1
    conversation = WhatsAppConversation.objects.get()
    assert "ConnectionError" in conversation.attribution_error


def test_graph_error_never_leaks_the_token(client, config, settings):
    settings.META_WHATSAPP_ADS_ENRICHMENT = True
    graph_response = mock.Mock(status_code=401)
    graph_response.json.return_value = {"error": {"message": "Invalid OAuth access token"}}

    with mock.patch("apps.integrations.meta_whatsapp.requests.get", return_value=graph_response):
        post_webhook(client, payloads.ctwa_message())

    conversation = WhatsAppConversation.objects.get()
    assert "test-access-token" not in conversation.attribution_error


# ============================================================
# 15. Database failure and retry
# ============================================================

def test_a_failure_mid_processing_leaves_no_partial_state(client, config, no_enrichment):
    """
    The dedupe claim and the CRM writes share one transaction.

    If they did not, a crash after the claim would make Meta's retry a no-op
    and the lead would be lost for good — so a failure must roll the claim
    back with everything else.
    """
    with mock.patch(
        "apps.integrations.meta_whatsapp._record_message",
        side_effect=RuntimeError("database is down"),
    ):
        response = post_webhook(client, payloads.ctwa_message())

    assert response.status_code == 200          # logged; the task reported the error
    assert not Lead.objects.exists()
    assert not WhatsAppConversation.objects.exists()
    assert not MetaWhatsAppEvent.objects.exists()


def test_meta_retry_after_a_failure_succeeds(client, config, no_enrichment):
    payload = payloads.ctwa_message()

    with mock.patch(
        "apps.integrations.meta_whatsapp._record_message",
        side_effect=RuntimeError("database is down"),
    ):
        post_webhook(client, payload)

    # Meta redelivers the same event; this time it must land completely.
    post_webhook(client, payload)

    assert Lead.objects.count() == 1
    assert WhatsAppConversation.objects.count() == 1
    assert WhatsAppMessage.objects.count() == 1
    assert MetaWhatsAppEvent.objects.get().status == MetaWhatsAppEvent.STATUS_PROCESSED


def test_one_bad_message_does_not_sink_the_batch(client, config, no_enrichment):
    """Meta batches events; a poison message must not cost us the good ones."""
    payload = payloads.ctwa_message()
    value = payload["entry"][0]["changes"][0]["value"]
    value["messages"].append({
        "from": "919812345678",
        "id": "wamid.SECOND",
        "timestamp": "1717430999",
        "type": "text",
        "text": {"body": "Second customer"},
    })
    value["contacts"].append({"profile": {"name": "Priya"}, "wa_id": "919812345678"})

    real_resolve = __import__(
        "apps.integrations.meta_whatsapp", fromlist=["_resolve_lead"]
    )._resolve_lead

    def explode_on_first(message, config_, referral):
        if message.from_wa_id == payloads.CUSTOMER_WA_ID:
            raise RuntimeError("boom")
        return real_resolve(message, config_, referral)

    with mock.patch(
        "apps.integrations.meta_whatsapp._resolve_lead", side_effect=explode_on_first,
    ):
        response = post_webhook(client, payload)

    assert response.status_code == 200
    assert Lead.objects.count() == 1
    assert Lead.objects.get().phone == "+919812345678"


# ============================================================
# Delivery receipts
# ============================================================

def test_status_update_marks_an_outbound_message_delivered(client, config, no_enrichment):
    from django.utils import timezone

    lead = Lead.objects.create(name="Rahul", phone="+919876543210")
    message = WhatsAppMessage.objects.create(
        lead=lead, direction="outbound", content="Hello",
        provider="meta_cloud", provider_message_id="wamid.OUTBOUND123",
        status="sent", sent_at=timezone.now(),
    )

    post_webhook(client, payloads.status_update())

    message.refresh_from_db()
    assert message.status == "delivered"
    assert message.delivered_at is not None


def test_status_for_an_unknown_message_is_ignored(client, config, no_enrichment):
    response = post_webhook(client, payloads.status_update(message_id="wamid.NOT_OURS"))
    assert response.status_code == 200
    event = MetaWhatsAppEvent.objects.get()
    assert event.status == MetaWhatsAppEvent.STATUS_IGNORED


def test_repeated_status_updates_apply_once(client, config, no_enrichment):
    lead = Lead.objects.create(name="Rahul", phone="+919876543210")
    WhatsAppMessage.objects.create(
        lead=lead, direction="outbound", content="Hello",
        provider="meta_cloud", provider_message_id="wamid.OUTBOUND123", status="sent",
    )

    post_webhook(client, payloads.status_update())
    post_webhook(client, payloads.status_update())

    assert MetaWhatsAppEvent.objects.filter(kind="status").count() == 1


# ============================================================
# Logging and secret hygiene
# ============================================================

def test_delivery_is_logged_without_the_signature_header(client, config, no_enrichment):
    post_webhook(client, payloads.ctwa_message())

    log = WebhookLog.objects.get()
    assert log.source == LeadSource.META_CTWA
    assert log.processed is True
    assert log.leads_created == 1
    header_names = {k.lower() for k in log.headers}
    assert "x-hub-signature-256" not in header_names
    assert "authorization" not in header_names


def test_config_api_never_returns_a_secret(client, config, no_enrichment):
    from apps.communications.serializers import WhatsAppConfigSerializer

    data = WhatsAppConfigSerializer(config).data
    rendered = json.dumps(data)
    for secret in (APP_SECRET, VERIFY_TOKEN, "test-access-token"):
        assert secret not in rendered

    assert data["webhook"]["verify_token_set"] is True
    assert data["webhook"]["app_secret_set"] is True


def test_lead_detail_exposes_only_real_attribution(client, config, no_enrichment):
    from apps.leads.serializers import LeadDetailSerializer

    post_webhook(client, payloads.ctwa_message())
    data = LeadDetailSerializer(Lead.objects.get()).data

    attribution = data["whatsapp_attribution"]
    assert attribution["source"] == "Meta Click-to-WhatsApp"
    assert attribution["first_message"] == "Hi, I want more information."
    assert attribution["attribution"]["headline"] == "Diwali Offer"
    # No enrichment ran, so no campaign key at all — not an empty string.
    assert "campaign_name" not in attribution["attribution"]


def test_lead_without_whatsapp_has_no_attribution_block(client, config, no_enrichment):
    from apps.leads.serializers import LeadDetailSerializer

    lead = Lead.objects.create(name="Walk-in", phone="+919812345670")
    assert LeadDetailSerializer(lead).data["whatsapp_attribution"] is None


# ============================================================
# Unit-level parsing
# ============================================================

def test_parse_referral_omits_keys_meta_did_not_send():
    from apps.integrations.meta_whatsapp import parse_referral

    parsed = parse_referral({"source_id": "123", "source_type": "ad"})
    assert parsed["referral_source_id"] == "123"
    assert parsed["meta_ad_id"] == "123"
    assert "referral_headline" not in parsed
    assert parsed["is_ad_referred"] is True


def test_parse_referral_of_a_post_is_not_an_ad_id():
    from apps.integrations.meta_whatsapp import parse_referral

    parsed = parse_referral({"source_id": "post_1", "source_type": "post"})
    assert parsed["referral_source_id"] == "post_1"
    assert "meta_ad_id" not in parsed


def test_parse_referral_of_nothing_is_nothing():
    from apps.integrations.meta_whatsapp import parse_referral

    assert parse_referral({}) == {}
    assert parse_referral(None) == {}


def test_signature_verification_rejects_an_empty_secret():
    from apps.integrations.meta_whatsapp import verify_signature

    body = b'{"a":1}'
    assert verify_signature(body, sign(body), APP_SECRET) is True
    assert verify_signature(body, sign(body), "") is False
    assert verify_signature(body, "", APP_SECRET) is False
    assert verify_signature(body, "md5=abc", APP_SECRET) is False


def test_graph_version_is_configurable(config, settings):
    from apps.integrations.meta_whatsapp import graph_version

    settings.META_GRAPH_API_VERSION = "v26.0"
    assert graph_version(None) == "v26.0"

    config.graph_api_version = "v25.0"
    assert graph_version(config) == "v25.0"


def test_fetch_ad_attribution_raises_a_clean_error():
    from apps.integrations.meta_whatsapp import fetch_ad_attribution

    response = mock.Mock(status_code=403)
    response.json.return_value = {"error": {"message": "no permission"}}
    with mock.patch("apps.integrations.meta_whatsapp.requests.get", return_value=response):
        with pytest.raises(MetaWhatsAppError) as excinfo:
            fetch_ad_attribution("123", "secret-token", "v25.0")

    assert "secret-token" not in str(excinfo.value)


# ============================================================
# Click-to-WhatsApp is not a LeadSourceConfig
# ============================================================

def test_ctwa_cannot_be_added_as_a_lead_source_config():
    """
    Its real configuration lives on WhatsAppConfig.

    A LeadSourceConfig row for it would hand an admin a generic webhook-token
    URL that the Click-to-WhatsApp handler never reads, and an API-key field
    nothing uses — a card that looks configured while capturing nothing.
    """
    from apps.integrations.serializers import LeadSourceConfigSerializer

    for source in (LeadSource.META_CTWA, LeadSource.WHATSAPP):
        serializer = LeadSourceConfigSerializer(data={"source": source})
        assert not serializer.is_valid()
        assert "source" in serializer.errors
        # The error has to say where the real screen is, not just "invalid".
        assert "WhatsApp" in str(serializer.errors["source"][0])


def test_other_lead_sources_are_still_configurable():
    """The guard must not catch the sources that genuinely use this model."""
    from apps.integrations.serializers import LeadSourceConfigSerializer

    serializer = LeadSourceConfigSerializer(data={"source": LeadSource.INDIAMART})
    assert serializer.is_valid(), serializer.errors
