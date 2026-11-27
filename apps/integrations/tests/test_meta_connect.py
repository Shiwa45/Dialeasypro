"""
Meta Lead Ads through "Continue with Facebook".

The Graph API is faked at `requests.request`, so these pin the flow end to end:
sign-in lists the Pages, connecting subscribes the app and routes the Page to
this tenant, the platform webhook queues each lead for its tenant, a lead
lands in the CRM with the form's owner, and the poll imports what the webhook
missed — never twice.
"""
import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import connection
from django.test import Client, override_settings
from django.utils import timezone

from apps.authentication.models import Agent, AgentTeam, Team
from apps.core.constants import LeadSource
from apps.integrations import meta_connect
from apps.integrations.models import LeadSourceConfig, MetaConnection, MetaLeadForm, MetaLeadPage
from apps.leads.models import Lead
from apps.tenants.models import MetaPageRoute, Tenant

pytestmark = pytest.mark.django_db

META = dict(META_APP_ID="111", META_APP_SECRET="appsecret", META_VERIFY_TOKEN="vt-123",
            META_LOGIN_CONFIG_ID="", BASE_DOMAIN="dialsathi.test", META_OAUTH_REDIRECT_URI="",
            # The platform host must be allowed, or django-tenants answers an
            # empty 404 before any view runs (the .env list varies by machine).
            ALLOWED_HOSTS=["dialsathi.test", "testtenant.localhost"])


class FakeResp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data


class FakeGraph:
    """Answers Graph calls by path; records what was called."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, params=None, timeout=None):
        path = url.split("graph.facebook.com/")[-1].split("/", 1)[-1].split("?")[0]
        self.calls.append((method, path, dict(params or {})))
        for (m, p), answer in self.routes.items():
            if m == method and p == path:
                data = answer(params or {}) if callable(answer) else answer
                return FakeResp(data, 400 if "error" in data else 200)
        return FakeResp({"error": {"message": f"unexpected {method} {path}"}}, 400)


def _lead_json(leadgen_id, phone="+919812300001", name="Ravi Kumar", form_id="F1", platform="fb"):
    return {
        "id": leadgen_id, "created_time": "2026-11-27T10:00:00+0000", "form_id": form_id,
        "platform": platform, "ad_name": "Diwali Ad", "campaign_name": "Diwali",
        "field_data": [
            {"name": "full_name", "values": [name]},
            {"name": "phone_number", "values": [phone]},
        ],
    }


@pytest.fixture
def admin():
    return Agent.objects.filter(role="admin").first() or Agent.objects.create_agent(
        email="admin@x.com", name="Admin", password="Pw@12345678", role="admin",
    )


@pytest.fixture
def page():
    return MetaLeadPage.objects.create(page_id="P1", name="Acme Realty", secrets={"page_token": "PT"})


# ============================================================
# Sign-in
# ============================================================

@override_settings(**META)
def test_login_url_and_state_round_trip():
    url = meta_connect.login_url("test_tenant", 7)
    assert url.startswith("https://www.facebook.com/")
    assert "client_id=111" in url and "leads_retrieval" in url
    assert "redirect_uri=https%3A%2F%2Fdialsathi.test%2Fapi%2Fv1%2Fpublic%2Fmeta%2Foauth%2Fcallback%2F" in url
    state = url.split("state=")[1].split("&")[0]
    from urllib.parse import unquote

    assert meta_connect.read_state(unquote(state))["s"] == "test_tenant"
    with pytest.raises(meta_connect.MetaError):
        meta_connect.read_state("forged")


@override_settings(**{**META, "META_LOGIN_CONFIG_ID": "cfg9"})
def test_login_url_uses_business_configuration_when_set():
    url = meta_connect.login_url("test_tenant", 7)
    assert "config_id=cfg9" in url and "scope=" not in url


@override_settings(**META)
def test_callback_stores_login_and_lists_pages(admin):
    graph = FakeGraph({
        ("GET", "oauth/access_token"): lambda p: {"access_token": "LONG" if p.get("grant_type") else "SHORT",
                                                   "expires_in": 5_000_000},
        ("GET", "me"): {"id": "U1", "name": "Shiwansh"},
        ("GET", "me/permissions"): {"data": [{"permission": s, "status": "granted"} for s in
                                             ("leads_retrieval", "pages_manage_metadata", "pages_show_list")]},
        ("GET", "me/accounts"): {"data": [
            {"id": "P1", "name": "Acme Realty", "access_token": "PT1", "picture": {"data": {"url": "https://x/p.jpg"}}},
            {"id": "P2", "name": "Acme Homes", "access_token": "PT2"},
        ]},
    })
    state = meta_connect.make_state(connection.schema_name, admin.pk)
    with patch("apps.integrations.meta_connect.requests.request", graph):
        response = Client(HTTP_HOST="dialsathi.test").get(
            "/api/v1/public/meta/oauth/callback/", {"code": "abc", "state": state})

    assert response.status_code == 200
    assert b"dialsathi-meta" in response.content and b"Found 2 Facebook Pages" in response.content
    assert b"PT1" not in response.content  # no token ever reaches the browser
    connection.set_schema("test_tenant")
    login = MetaConnection.latest()
    assert login.fb_user_name == "Shiwansh" and login.secrets["user_token"] == "LONG"
    assert MetaLeadPage.objects.get(page_id="P1").token == "PT1"
    assert MetaLeadPage.objects.filter(connected=True).count() == 0  # listed, not connected


@override_settings(**META)
def test_callback_refuses_a_forged_state():
    response = Client(HTTP_HOST="dialsathi.test").get(
        "/api/v1/public/meta/oauth/callback/", {"code": "abc", "state": "nope"})
    assert response.status_code == 200 and b'"ok": false' in response.content


# ============================================================
# Connecting a Page
# ============================================================

@override_settings(**META)
def test_connect_subscribes_routes_and_lists_forms(page, admin):
    graph = FakeGraph({
        ("POST", "P1/subscribed_apps"): {"success": True},
        ("GET", "P1/leadgen_forms"): {"data": [
            {"id": "F1", "name": "Site visit", "status": "ACTIVE"},
            {"id": "F0", "name": "Old form", "status": "ARCHIVED"},
        ]},
    })
    with patch("apps.integrations.meta_connect.requests.request", graph):
        meta_connect.connect_page(page, agent=admin)

    assert ("POST", "P1/subscribed_apps", {"subscribed_fields": "leadgen", "access_token": "PT"}) in graph.calls
    page.refresh_from_db()
    assert page.connected
    route = MetaPageRoute.objects.get(page_id="P1")
    assert route.tenant.schema_name == "test_tenant"
    assert MetaLeadForm.objects.get(form_id="F1").enabled
    assert not MetaLeadForm.objects.get(form_id="F0").enabled
    config = LeadSourceConfig.objects.get(source=LeadSource.META_FACEBOOK)
    assert config.is_active


@override_settings(**META)
def test_a_page_owned_by_another_workspace_is_refused(page):
    from django_tenants.utils import schema_context

    with schema_context("public"):
        other = Tenant(schema_name="other_ws", company_name="Other", primary_contact_name="O",
                       primary_contact_email="o@o.test", primary_contact_phone="+919800000000")
        other.auto_create_schema = False
        other.save()
    MetaPageRoute.objects.create(page_id="P1", tenant=other)

    with pytest.raises(meta_connect.MetaError, match="another DialSathi workspace"):
        meta_connect.connect_page(page)
    assert not MetaLeadPage.objects.get(page_id="P1").connected


@override_settings(**META)
def test_disconnect_unsubscribes_and_removes_the_route(page):
    page.connected = True
    page.save()
    MetaPageRoute.objects.create(page_id="P1", tenant=Tenant.objects.get(schema_name="test_tenant"))
    graph = FakeGraph({("DELETE", "P1/subscribed_apps"): {"success": True}})
    with patch("apps.integrations.meta_connect.requests.request", graph):
        meta_connect.disconnect_page(page)
    assert not MetaPageRoute.objects.filter(page_id="P1").exists()
    assert not MetaLeadPage.objects.get(page_id="P1").connected


# ============================================================
# The platform webhook
# ============================================================

def _signed_post(body: dict, secret="appsecret"):
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return Client(HTTP_HOST="dialsathi.test").post(
        "/api/v1/public/meta/leadgen/", data=raw, content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sig)


LEADGEN = {"object": "page", "entry": [{"id": "P1", "changes": [{"field": "leadgen", "value": {
    "leadgen_id": "L1", "page_id": "P1", "form_id": "F1", "ad_id": "A1"}}]}]}


@override_settings(**META)
def test_webhook_verification_uses_the_platform_token():
    c = Client(HTTP_HOST="dialsathi.test")
    ok = c.get("/api/v1/public/meta/leadgen/", {"hub.mode": "subscribe", "hub.verify_token": "vt-123",
                                                "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.content == b"42"
    assert c.get("/api/v1/public/meta/leadgen/", {"hub.mode": "subscribe", "hub.verify_token": "x",
                                                  "hub.challenge": "42"}).status_code == 403


@override_settings(**META)
def test_webhook_routes_each_lead_to_its_workspace():
    MetaPageRoute.objects.create(page_id="P1", tenant=Tenant.objects.get(schema_name="test_tenant"))
    with patch("apps.integrations.tasks.process_meta_leadgen.apply_async") as queued:
        assert _signed_post(LEADGEN).status_code == 200
    queued.assert_called_once()
    assert queued.call_args.kwargs["args"] == ["test_tenant", "P1", "F1", "L1"]


@override_settings(**META)
def test_webhook_refuses_a_bad_signature_and_ignores_unknown_pages():
    with patch("apps.integrations.tasks.process_meta_leadgen.apply_async") as queued:
        assert _signed_post(LEADGEN, secret="wrong").status_code == 401
        assert _signed_post(LEADGEN).status_code == 200  # no route for P1
    queued.assert_not_called()


# ============================================================
# One lead into the CRM
# ============================================================

def _connected(page):
    page.connected = True
    page.save()
    LeadSourceConfig.objects.get_or_create(source=LeadSource.META_FACEBOOK, defaults={"is_active": True})
    return page


@override_settings(**META)
def test_a_lead_lands_with_its_ad_details(page):
    _connected(page)
    MetaLeadForm.objects.create(page=page, form_id="F1", name="Site visit")
    graph = FakeGraph({("GET", "L1"): _lead_json("L1")})
    with patch("apps.integrations.meta_connect.requests.request", graph):
        assert meta_connect.handle_leadgen("P1", "F1", "L1") == "created"
        assert meta_connect.handle_leadgen("P1", "F1", "L1") == "duplicate"  # webhook retry

    lead = Lead.objects.get(source_lead_id="L1")
    assert lead.name == "Ravi Kumar" and lead.phone.endswith("9812300001")
    assert lead.source == LeadSource.META_FACEBOOK
    assert lead.campaign_name == "Diwali" and lead.ad_name == "Diwali Ad"
    assert lead.source_meta["form_name"] == "Site visit"
    page.refresh_from_db()
    assert page.leads_received == 1
    assert MetaLeadForm.objects.get(form_id="F1").leads_received == 1


@override_settings(**META)
def test_instagram_leads_are_marked_instagram(page):
    _connected(page)
    MetaLeadForm.objects.create(page=page, form_id="F1")
    graph = FakeGraph({("GET", "L9"): _lead_json("L9", platform="ig")})
    with patch("apps.integrations.meta_connect.requests.request", graph):
        meta_connect.handle_leadgen("P1", "F1", "L9")
    assert Lead.objects.get(source_lead_id="L9").source == LeadSource.META_INSTAGRAM


@override_settings(**META)
def test_a_switched_off_form_or_page_takes_no_leads(page):
    _connected(page)
    MetaLeadForm.objects.create(page=page, form_id="F1", enabled=False)
    graph = FakeGraph({("GET", "L1"): _lead_json("L1")})
    with patch("apps.integrations.meta_connect.requests.request", graph):
        assert meta_connect.handle_leadgen("P1", "F1", "L1") == "form_off"
        page.connected = False
        page.save()
        assert meta_connect.handle_leadgen("P1", "F2", "L2") == "page_not_connected"
    assert not Lead.objects.filter(source_lead_id__in=["L1", "L2"]).exists()


@override_settings(**META)
def test_a_new_form_follows_the_pages_auto_add_switch(page):
    _connected(page)
    graph = FakeGraph({
        ("GET", "F7"): {"name": "New form", "status": "ACTIVE"},
        ("GET", "L7"): _lead_json("L7", form_id="F7"),
    })
    with patch("apps.integrations.meta_connect.requests.request", graph):
        assert meta_connect.handle_leadgen("P1", "F7", "L7") == "created"
    assert MetaLeadForm.objects.get(form_id="F7").name == "New form"

    page.auto_add_new_forms = False
    page.save()
    graph = FakeGraph({("GET", "F8"): {"name": "Another", "status": "ACTIVE"}})
    with patch("apps.integrations.meta_connect.requests.request", graph):
        assert meta_connect.handle_leadgen("P1", "F8", "L8") == "form_off"


@override_settings(**META)
def test_a_form_can_send_its_leads_to_one_agent(page):
    _connected(page)
    asha = Agent.objects.create_agent(email="asha@x.com", name="Asha", password="Pw@12345678")
    MetaLeadForm.objects.create(page=page, form_id="F1", assign_mode="agent", assign_agent=asha)
    graph = FakeGraph({("GET", "L1"): _lead_json("L1")})
    with patch("apps.integrations.meta_connect.requests.request", graph):
        meta_connect.handle_leadgen("P1", "F1", "L1")
    assert Lead.objects.get(source_lead_id="L1").assigned_to == asha


@override_settings(**META)
def test_a_team_takes_turns(page):
    _connected(page)
    team = Team.objects.create(name="Noida")
    a = Agent.objects.create_agent(email="a@x.com", name="A", password="Pw@12345678")
    b = Agent.objects.create_agent(email="b@x.com", name="B", password="Pw@12345678")
    for ag in (a, b):
        AgentTeam.objects.create(agent=ag, team=team)
    MetaLeadForm.objects.create(page=page, form_id="F1", assign_mode="team", assign_team=team)
    graph = FakeGraph({("GET", f"L{i}"): _lead_json(f"L{i}", phone=f"+91981230000{i}") for i in range(1, 4)})
    with patch("apps.integrations.meta_connect.requests.request", graph):
        for i in range(1, 4):
            meta_connect.handle_leadgen("P1", "F1", f"L{i}")
    owners = [Lead.objects.get(source_lead_id=f"L{i}").assigned_to for i in range(1, 4)]
    assert owners == [a, b, a]


@override_settings(**META)
def test_the_task_routes_into_the_tenant_schema(page):
    from apps.integrations.tasks import process_meta_leadgen

    _connected(page)
    MetaLeadForm.objects.create(page=page, form_id="F1")
    graph = FakeGraph({("GET", "L1"): _lead_json("L1")})
    with patch("apps.integrations.meta_connect.requests.request", graph):
        assert process_meta_leadgen.apply(args=["test_tenant", "P1", "F1", "L1"]).get() == "created"


# ============================================================
# The safety-net poll
# ============================================================

@override_settings(**META)
def test_poll_imports_what_the_webhook_missed_once(page):
    _connected(page)
    page.last_polled_at = timezone.now() - timedelta(minutes=5)
    page.save()
    MetaLeadForm.objects.create(page=page, form_id="F1", enabled=True)
    graph = FakeGraph({
        ("GET", "P1/leadgen_forms"): {"data": [{"id": "F1", "name": "Site visit", "status": "ACTIVE"}]},
        ("GET", "F1/leads"): {"data": [_lead_json("L1"), _lead_json("L2", phone="+919812300002")]},
    })
    with patch("apps.integrations.meta_connect.requests.request", graph):
        first = meta_connect.poll_tenant()
        second = meta_connect.poll_tenant()

    assert first["created"] == 2
    assert second["created"] == 0 and second["duplicate"] == 2
    leads_call = [c for c in graph.calls if c[1] == "F1/leads"][0]
    assert "time_created" in leads_call[2]["filtering"]
    assert Lead.objects.filter(source_lead_id__in=["L1", "L2"]).count() == 2


@override_settings(**META)
def test_poll_respects_the_integration_switch(page):
    _connected(page)
    LeadSourceConfig.objects.filter(source=LeadSource.META_FACEBOOK).update(is_active=False)
    graph = FakeGraph({})
    with patch("apps.integrations.meta_connect.requests.request", graph):
        assert meta_connect.poll_tenant()["pages"] == 0
    assert graph.calls == []


# ============================================================
# Tenant API
# ============================================================

@override_settings(**META)
def test_status_and_form_settings_api(client, admin, page):
    from rest_framework_simplejwt.tokens import RefreshToken  # noqa: F401  (auth via force_login below)

    _connected(page)
    MetaLeadForm.objects.create(page=page, form_id="F1", name="Site visit")
    asha = Agent.objects.create_agent(email="asha2@x.com", name="Asha", password="Pw@12345678")

    from rest_framework.test import APIClient

    api = APIClient(HTTP_HOST="testtenant.localhost")
    api.force_authenticate(user=admin)
    with patch("apps.integrations.meta_connect_views.meta_connect.route_owner", return_value=None):
        data = api.get("/api/v1/integrations/meta/connect/").json()
    assert data["available"] is True
    assert data["pages"][0]["forms"][0]["name"] == "Site visit"

    r = api.patch("/api/v1/integrations/meta/connect/forms/F1/",
                  {"assign_mode": "agent", "assign_agent": asha.pk}, format="json")
    assert r.status_code == 200 and r.json()["assign_agent_name"] == "Asha"
    r = api.patch("/api/v1/integrations/meta/connect/forms/F1/", {"assign_mode": "team"}, format="json")
    assert r.status_code == 400  # a team must be picked

    with patch("apps.integrations.views.check_may_activate"):
        r = api.post("/api/v1/integrations/meta/connect/start/")
    assert r.status_code == 200 and r.json()["url"].startswith("https://www.facebook.com/")
