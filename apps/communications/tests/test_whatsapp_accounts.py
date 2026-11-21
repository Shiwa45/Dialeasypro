"""
Several WhatsApp numbers per tenant.

A tenant used to have exactly one WhatsApp connection. Now it can connect
several (a Sales number and a Support number, or two Meta WhatsApp Business
Accounts). These pin the rules that make that safe:

* exactly one account is the default, and stays so through edits and deletes;
* every send knows which number it goes out from — the one picked, else the
  template's own, else the number the lead last wrote to, else the default;
* a template approved on one account is never sent from another;
* replies and receipts are filed under the number they arrived on;
* a second number needs the plan feature.
"""
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.communications.models import (
    BulkCampaign, CampaignRecipient, WhatsAppConfig, WhatsAppMessage, WhatsAppTemplate,
)
from apps.communications.serializers import BulkCampaignCreateSerializer
from apps.communications.tasks import send_single_whatsapp, send_whatsapp_chunk
from apps.communications.views import (
    SendWhatsAppView, WhatsAppAccountDetailView, WhatsAppAccountListView,
    WhatsAppAccountMakeDefaultView, WhatsAppSendersView, WhatsAppTemplateListView,
    WhatsAppWebhookView,
)
from apps.communications.whatsapp_accounts import resolve_sender
from apps.core.constants import AgentRole, FeatureKey
from apps.leads.models import Lead

pytestmark = pytest.mark.django_db

TEST_SCHEMA = "test_tenant"


def _account(label, pnid="", active=True, **kw):
    acct = WhatsAppConfig(
        label=label, provider="meta_cloud", is_active=active,
        credentials={"access_token": "t", "phone_number_id": pnid or f"pn-{label}"},
        **kw,
    )
    acct.save()
    return acct


def _template(name="offer", account=None, **kw):
    return WhatsAppTemplate.objects.create(
        name=name, body_text="Hi {{1}}", variable_mapping={"1": "name"},
        status="approved", account=account, **kw,
    )


@pytest.fixture
def admin():
    return Agent.objects.create_agent(
        email="admin@x.com", name="Admin", password="Pw@12345678", role=AgentRole.ADMIN,
    )


@pytest.fixture
def agent():
    return Agent.objects.create_agent(email="a@x.com", name="Asha", password="Pw@12345678")


@pytest.fixture
def lead(agent):
    return Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=agent)


def _call(view, method, user, data=None, features=(), **kwargs):
    factory = APIRequestFactory()
    request = getattr(factory, method)("/x/", data or {}, format="json")
    force_authenticate(request, user=user)
    request.has_feature = lambda key: key in features or key == FeatureKey.ONE_CLICK_WHATSAPP
    return view.as_view()(request, **kwargs)


# ============================================================
# The default account
# ============================================================

def test_the_first_account_is_the_default():
    sales = _account("Sales")
    assert sales.is_default
    support = _account("Support")
    assert not support.is_default
    assert WhatsAppConfig.get_default() == sales


def test_making_another_default_moves_the_flag():
    sales, support = _account("Sales"), _account("Support")
    support.is_default = True
    support.save()
    sales.refresh_from_db()
    assert not sales.is_default
    assert WhatsAppConfig.objects.filter(is_default=True).count() == 1


def test_deleting_the_default_hands_it_on():
    sales, support = _account("Sales"), _account("Support")
    sales.delete()
    support.refresh_from_db()
    assert support.is_default


def test_get_solo_is_the_default_and_creates_one_only_when_none_exist():
    assert WhatsAppConfig.objects.count() == 0
    solo = WhatsAppConfig.get_solo()
    assert solo.is_default and WhatsAppConfig.objects.count() == 1
    _account("Support")
    assert WhatsAppConfig.get_solo() == solo
    assert WhatsAppConfig.objects.count() == 2


def test_the_meta_number_id_is_copied_out_of_the_encrypted_credentials():
    acct = _account("Sales", pnid="106540352242922")
    assert acct.phone_number_id == "106540352242922"
    assert WhatsAppConfig.for_phone_number_id("106540352242922") == acct
    assert WhatsAppConfig.for_phone_number_id("999") is None


# ============================================================
# Which number a message goes out from
# ============================================================

def test_the_picked_number_wins(lead):
    _account("Sales")
    support = _account("Support")
    assert resolve_sender(account_id=support.pk, lead=lead).account == support


def test_a_template_goes_out_from_its_own_account(lead):
    _account("Sales")
    support = _account("Support")
    assert resolve_sender(template=_template(account=support), lead=lead).account == support


def test_a_template_from_another_account_is_refused_not_switched(lead):
    sales, support = _account("Sales"), _account("Support")
    sender = resolve_sender(account_id=sales.pk, template=_template(account=support), lead=lead)
    assert sender.account is None
    assert "Support" in sender.error


def test_a_shared_template_goes_out_from_any_number(lead):
    _account("Sales")
    support = _account("Support")
    sender = resolve_sender(account_id=support.pk, template=_template(account=None), lead=lead)
    assert sender.account == support and not sender.error


def test_a_reply_continues_on_the_number_the_lead_wrote_to(lead):
    _account("Sales")
    support = _account("Support")
    WhatsAppMessage.objects.create(
        lead=lead, direction="inbound", content="Hello?", status="received", account=support,
    )
    assert resolve_sender(lead=lead).account == support


def test_with_nothing_to_go_on_the_default_sends(lead):
    sales = _account("Sales")
    _account("Support")
    assert resolve_sender(lead=lead).account == sales


def test_a_lead_on_a_disconnected_number_falls_back_to_the_default(lead):
    sales = _account("Sales")
    support = _account("Support", active=False)
    WhatsAppMessage.objects.create(
        lead=lead, direction="inbound", content="Hi", status="received", account=support,
    )
    assert resolve_sender(lead=lead).account == sales


# ============================================================
# One-click send
# ============================================================

def test_one_click_send_queues_the_picked_number(agent, lead):
    _account("Sales")
    support = _account("Support")
    with patch("apps.communications.tasks.send_single_whatsapp.apply_async") as queued:
        response = _call(SendWhatsAppView, "post", agent,
                         {"lead_id": lead.pk, "message": "Hi", "account_id": support.pk})
    assert response.status_code == 200
    assert response.data["sent_from"].startswith("Support")
    assert queued.call_args.kwargs["kwargs"]["account_id"] == support.pk


def test_one_click_send_refuses_a_template_from_another_number(agent, lead):
    sales, support = _account("Sales"), _account("Support")
    template = _template(account=support)
    with patch("apps.communications.tasks.send_single_whatsapp.apply_async") as queued:
        response = _call(SendWhatsAppView, "post", agent,
                         {"lead_id": lead.pk, "template_id": template.pk, "account_id": sales.pk})
    assert response.status_code == 400
    assert response.data["error"] == "sender_not_usable"
    assert not queued.called


def test_one_click_send_from_an_unconnected_number_is_refused(agent, lead, settings):
    settings.WHATSAPP_ALLOW_MOCK = False
    _account("Sales")
    support = _account("Support", active=False)
    with patch("apps.communications.tasks.send_single_whatsapp.apply_async") as queued:
        response = _call(SendWhatsAppView, "post", agent,
                         {"lead_id": lead.pk, "message": "Hi", "account_id": support.pk})
    assert response.status_code == 400
    assert "Support" in response.data["message"]
    assert not queued.called


def test_the_sent_message_records_its_number(agent, lead):
    _account("Sales")
    support = _account("Support")
    provider = MagicMock()
    provider.send_text.return_value = "wamid.1"
    with patch("apps.communications.tasks._get_whatsapp_provider",
               return_value=(provider, "meta_cloud")) as built:
        send_single_whatsapp.run(TEST_SCHEMA, lead.pk, "Hello", sent_by_id=agent.pk,
                                 account_id=support.pk)
    assert built.call_args.args[0] == support
    msg = WhatsAppMessage.objects.get(lead=lead)
    assert msg.account == support and msg.status == "sent"


# ============================================================
# Campaigns
# ============================================================

def test_a_campaign_cannot_send_a_template_from_another_number():
    sales, support = _account("Sales"), _account("Support")
    serializer = BulkCampaignCreateSerializer(data={
        "name": "Diwali", "channel": "whatsapp", "audience_filters": {},
        "template": _template(account=support).pk, "whatsapp_account": sales.pk,
    })
    assert not serializer.is_valid()
    assert "whatsapp_account" in serializer.errors


def test_a_campaign_sends_from_its_chosen_number():
    _account("Sales")
    support = _account("Support")
    template = _template(account=None)
    lead = Lead.objects.create(name="Ravi", phone="+919812300001")
    campaign = BulkCampaign.objects.create(
        name="Diwali", channel="whatsapp", status="running", audience_filters={},
        template=template, whatsapp_account=support,
    )
    recipient = CampaignRecipient.objects.create(campaign=campaign, lead=lead, phone=lead.phone)
    provider = MagicMock()
    provider.send_template.return_value = "wamid.c1"
    with patch("apps.communications.tasks._get_whatsapp_provider",
               return_value=(provider, "meta_cloud")) as built:
        send_whatsapp_chunk.run(TEST_SCHEMA, str(campaign.pk), [recipient.pk])
    assert built.call_args.args[0] == support
    assert WhatsAppMessage.objects.get(campaign=campaign).account == support


def test_a_campaign_without_a_sender_uses_the_templates_account():
    _account("Sales")
    support = _account("Support")
    template = _template(account=support)
    campaign = BulkCampaign.objects.create(
        name="Diwali", channel="whatsapp", status="running", audience_filters={}, template=template,
    )
    from apps.communications.tasks import campaign_sender

    assert campaign_sender(campaign).account == support


# ============================================================
# Templates
# ============================================================

def test_two_numbers_can_each_have_a_template_with_the_same_name(admin):
    sales, support = _account("Sales"), _account("Support")
    _template("welcome", account=sales)
    _template("welcome", account=support)
    from apps.communications.serializers import WhatsAppTemplateSerializer

    dup = WhatsAppTemplateSerializer(data={
        "name": "welcome", "body_text": "Hi", "account": sales.pk,
    })
    assert not dup.is_valid()
    assert "name" in dup.errors


def test_the_template_list_can_show_what_one_number_can_send(admin):
    sales, support = _account("Sales"), _account("Support")
    _template("sales_only", account=sales)
    _template("support_only", account=support)
    _template("shared", account=None)
    factory = APIRequestFactory()
    request = factory.get("/x/", {"account": support.pk})
    force_authenticate(request, user=admin)
    names = {t["name"] for t in WhatsAppTemplateListView.as_view()(request).data}
    assert names == {"support_only", "shared"}


# ============================================================
# Managing numbers (admin)
# ============================================================

def test_a_second_number_needs_the_plan_feature(admin):
    _account("Sales")
    response = _call(WhatsAppAccountListView, "post", admin,
                     {"label": "Support", "provider": "meta_cloud"})
    assert response.status_code in (402, 403)
    assert WhatsAppConfig.objects.count() == 1

    response = _call(WhatsAppAccountListView, "post", admin,
                     {"label": "Support", "provider": "meta_cloud",
                      "credentials": {"access_token": "x", "phone_number_id": "222"}},
                     features=(FeatureKey.WHATSAPP_MULTI_PROVIDER,))
    assert response.status_code == 201
    created = WhatsAppConfig.objects.get(label="Support")
    assert not created.is_default and not created.is_active
    assert created.phone_number_id == "222"
    assert "access_token" not in str(response.data.get("configured_fields", {}).get("access_token"))


def test_the_first_number_needs_no_extra_feature(admin):
    response = _call(WhatsAppAccountListView, "post", admin,
                     {"label": "Main", "provider": "interakt"})
    assert response.status_code == 201
    assert WhatsAppConfig.objects.get().is_default


def test_the_same_meta_number_cannot_be_connected_twice(admin):
    _account("Sales", pnid="111")
    response = _call(WhatsAppAccountListView, "post", admin,
                     {"label": "Copy", "provider": "meta_cloud",
                      "credentials": {"phone_number_id": "111"}},
                     features=(FeatureKey.WHATSAPP_MULTI_PROVIDER,))
    assert response.status_code == 400


def test_renaming_a_number_does_not_switch_sending_off(admin):
    sales = _account("Sales")
    response = _call(WhatsAppAccountDetailView, "patch", admin, {"label": "Sales team"}, pk=sales.pk)
    assert response.status_code == 200
    sales.refresh_from_db()
    assert sales.label == "Sales team" and sales.is_active


def test_new_credentials_switch_sending_off_until_tested(admin):
    sales = _account("Sales")
    _call(WhatsAppAccountDetailView, "patch", admin,
          {"credentials": {"access_token": "new"}}, pk=sales.pk)
    sales.refresh_from_db()
    assert not sales.is_active


def test_make_default(admin):
    sales, support = _account("Sales"), _account("Support")
    response = _call(WhatsAppAccountMakeDefaultView, "post", admin, pk=support.pk)
    assert response.status_code == 200
    sales.refresh_from_db()
    support.refresh_from_db()
    assert support.is_default and not sales.is_default


def test_a_number_a_running_campaign_sends_from_cannot_be_disconnected(admin):
    _account("Sales")
    support = _account("Support")
    BulkCampaign.objects.create(name="Live", channel="whatsapp", status="running",
                                audience_filters={}, whatsapp_account=support)
    response = _call(WhatsAppAccountDetailView, "delete", admin, pk=support.pk)
    assert response.status_code == 400
    assert WhatsAppConfig.objects.filter(pk=support.pk).exists()


def test_disconnecting_keeps_the_message_history(admin, lead):
    _account("Sales")
    support = _account("Support")
    msg = WhatsAppMessage.objects.create(lead=lead, direction="inbound", content="Hi",
                                         status="received", account=support)
    response = _call(WhatsAppAccountDetailView, "delete", admin, pk=support.pk)
    assert response.status_code == 204
    msg.refresh_from_db()
    assert msg.account is None and msg.content == "Hi"


def test_agents_see_sender_names_but_never_credentials(agent):
    _account("Sales", display_phone="+91 98765 43210")
    response = _call(WhatsAppSendersView, "get", agent)
    assert response.status_code == 200
    row = response.data[0]
    assert row["label"] == "Sales" and row["is_default"]
    assert "credentials" not in row and "access_token" not in str(row)


def test_agents_cannot_manage_numbers(agent):
    response = _call(WhatsAppAccountListView, "get", agent)
    assert response.status_code == 403


# ============================================================
# Provider webhooks (Interakt, WATI, Gupshup …)
# ============================================================

def test_a_provider_reply_is_filed_under_the_number_whose_url_it_hit(lead):
    _account("Sales")
    support = _account("Support")
    request = APIRequestFactory().post(
        f"/api/v1/comms/webhook/whatsapp/interakt/?token={support.webhook_token}",
        {"type": "inbound_message", "data": {
            "customer_phone_number": "919812300001", "wa_message_id": "wamid.r1",
            "message": {"text": {"body": "Interested"}},
        }}, format="json")
    with patch("apps.core.consumers.send_agent_notification"):
        response = WhatsAppWebhookView.as_view()(request, provider="interakt")
    assert response.status_code == 200
    assert WhatsAppMessage.objects.get(provider_message_id="wamid.r1").account == support


# ============================================================
# Upgrade from one connection
# ============================================================

def test_the_existing_connection_becomes_the_default_and_keeps_its_history(lead):
    import importlib

    from django.apps import apps as django_apps

    migration = importlib.import_module("apps.communications.migrations.0007_whatsapp_accounts")
    acct = _account("Main", pnid="555")
    WhatsAppConfig.objects.filter(pk=acct.pk).update(is_default=False, phone_number_id="", label="x")
    template = _template("legacy")
    msg = WhatsAppMessage.objects.create(lead=lead, direction="outbound", content="Hi", status="sent")
    campaign = BulkCampaign.objects.create(name="Old", channel="whatsapp", audience_filters={})

    migration.accounts_from_the_single_connection(django_apps, None)

    acct.refresh_from_db()
    assert acct.is_default and acct.label == "Main number" and acct.phone_number_id == "555"
    for obj, field in ((template, "account"), (msg, "account"), (campaign, "whatsapp_account")):
        obj.refresh_from_db()
        assert getattr(obj, field) == acct


# ============================================================
# Several numbers in one Meta WhatsApp Business Account
# ============================================================

def _waba_number(label, pnid, waba="WABA1", **kw):
    acct = WhatsAppConfig(
        label=label, provider="meta_cloud", is_active=True,
        credentials={"access_token": "tok", "phone_number_id": pnid, "business_account_id": waba,
                     "app_secret": "sec", "verify_token": "vt"},
        **kw,
    )
    acct.save()
    return acct


def test_a_template_goes_out_from_every_number_in_its_business_account(lead):
    sales = _waba_number("Sales", "p1")
    support = _waba_number("Support", "p2")
    other = _waba_number("Other brand", "p3", waba="WABA2")
    template = _template(account=sales)
    assert template.usable_from(support)
    assert not template.usable_from(other)
    assert resolve_sender(account_id=support.pk, template=template, lead=lead).account == support
    assert resolve_sender(account_id=other.pk, template=template, lead=lead).error


def test_a_reply_keeps_the_leads_number_when_it_can_send_the_template(lead):
    sales = _waba_number("Sales", "p1")
    support = _waba_number("Support", "p2")
    WhatsAppMessage.objects.create(lead=lead, direction="inbound", content="Hi",
                                   status="received", account=support)
    template = _template(account=sales)
    assert resolve_sender(template=template, lead=lead).account == support


def test_the_template_list_for_a_number_includes_its_business_accounts_templates(admin):
    sales = _waba_number("Sales", "p1")
    support = _waba_number("Support", "p2")
    other = _waba_number("Other brand", "p3", waba="WABA2")
    _template("sales_tpl", account=sales)
    _template("other_tpl", account=other)
    request = APIRequestFactory().get("/x/", {"account": support.pk})
    force_authenticate(request, user=admin)
    names = {t["name"] for t in WhatsAppTemplateListView.as_view()(request).data}
    assert names == {"sales_tpl"}


def test_one_template_name_per_business_account():
    from apps.communications.serializers import WhatsAppTemplateSerializer

    sales = _waba_number("Sales", "p1")
    support = _waba_number("Support", "p2")
    _template("welcome", account=sales)
    dup = WhatsAppTemplateSerializer(data={"name": "welcome", "body_text": "Hi", "account": support.pk})
    assert not dup.is_valid()
    assert "same WhatsApp Business Account" in str(dup.errors["name"])


def test_adding_another_number_of_a_connected_account_copies_its_credentials(admin):
    sales = _waba_number("Sales", "p1", inbound_enabled=True)
    response = _call(WhatsAppAccountListView, "post", admin, {
        "label": "Support", "display_phone": "+91 90000 00002",
        "copy_credentials_from": sales.pk, "credentials": {"phone_number_id": "p2"},
    }, features=(FeatureKey.WHATSAPP_MULTI_PROVIDER,))
    assert response.status_code == 201, response.data
    support = WhatsAppConfig.objects.get(label="Support")
    assert support.provider == "meta_cloud"
    assert support.credentials["access_token"] == "tok"
    assert support.credentials["app_secret"] == "sec"
    assert support.phone_number_id == "p2" and support.business_account_id == "WABA1"
    assert support.inbound_enabled and not support.is_active


def test_copying_needs_the_new_numbers_id(admin):
    sales = _waba_number("Sales", "p1")
    response = _call(WhatsAppAccountListView, "post", admin, {
        "label": "Support", "copy_credentials_from": sales.pk, "credentials": {},
    }, features=(FeatureKey.WHATSAPP_MULTI_PROVIDER,))
    assert response.status_code == 400


def test_meta_numbers_lists_the_business_accounts_numbers(admin):
    from apps.communications.views import WhatsAppAccountMetaNumbersView

    sales = _waba_number("Sales", "p1")
    meta = MagicMock(status_code=200, content=b"{}")
    meta.json.return_value = {"data": [
        {"id": "p1", "display_phone_number": "+91 90000 00001", "verified_name": "Acme"},
        {"id": "p2", "display_phone_number": "+91 90000 00002", "verified_name": "Acme"},
    ]}
    with patch("requests.get", return_value=meta) as got:
        response = _call(WhatsAppAccountMetaNumbersView, "get", admin, pk=sales.pk)
    assert response.status_code == 200
    assert "/WABA1/phone_numbers" in got.call_args.args[0]
    rows = {r["phone_number_id"]: r for r in response.data["numbers"]}
    assert rows["p1"]["connected_as"] == "Sales"
    assert rows["p2"]["connected_as"] is None


def test_meta_numbers_passes_metas_error_on(admin):
    from apps.communications.views import WhatsAppAccountMetaNumbersView

    sales = _waba_number("Sales", "p1")
    meta = MagicMock(status_code=400, content=b"{}")
    meta.json.return_value = {"error": {"message": "Invalid OAuth access token."}}
    with patch("requests.get", return_value=meta):
        response = _call(WhatsAppAccountMetaNumbersView, "get", admin, pk=sales.pk)
    assert response.status_code == 502
    assert "OAuth" in response.data["message"]
