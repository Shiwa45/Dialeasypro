"""
Who sees which calls, recordings and messages.

Leads were secure by default: anything not an admin or manager sees only its
own. Calls, reports and the AI module used the opposite — `if role == "agent":
restrict` — so HR, Accounts, Read-only and Senior Agents saw every call in the
tenant, could play any recording and read any transcript. Separately,
click-to-call and the WhatsApp/SMS endpoints fetched the lead without any
visibility check, and the WhatsApp message list returned every thread.
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent, AgentTeam, Team
from apps.calls.models import CallLog
from apps.calls.scoping import calls_visible_to
from apps.calls.views import CallLogListCreateView, ClickToCallView
from apps.communications.models import WhatsAppMessage
from apps.communications.views import SendSMSView, SendWhatsAppView, WhatsAppMessageListView
from apps.core.constants import AgentRole
from apps.leads.models import Lead

pytestmark = pytest.mark.django_db


def _agent(email, role=AgentRole.AGENT):
    return Agent.objects.create_agent(email=email, name=email.split("@")[0], password="Pw@12345678", role=role)


@pytest.fixture
def people():
    return {
        "admin": Agent.objects.create_tenant_admin(email="admin@x.com", name="Admin", password="Pw@12345678"),
        "manager": _agent("mgr@x.com", AgentRole.MANAGER),
        "senior": _agent("senior@x.com", AgentRole.SENIOR_AGENT),
        "hr": _agent("hr@x.com", AgentRole.HR),
        "accounts": _agent("acct@x.com", AgentRole.ACCOUNTS),
        "readonly": _agent("ro@x.com", AgentRole.READONLY),
        "asha": _agent("asha@x.com"),
        "bilal": _agent("bilal@x.com"),
    }


@pytest.fixture
def calls(people):
    return {
        "asha": CallLog.objects.create(agent=people["asha"], phone_number="+919812300001"),
        "bilal": CallLog.objects.create(agent=people["bilal"], phone_number="+919812300002"),
    }


def _visible(agent):
    return set(calls_visible_to(agent).values_list("agent__email", flat=True))


# ---- Calls: secure by default ------------------------------------------

@pytest.mark.parametrize("role", ["hr", "accounts", "readonly"])
def test_back_office_roles_do_not_see_the_floors_calls(people, calls, role):
    """HR and Accounts are 'not a CRM admin' and could play every recording."""
    assert _visible(people[role]) == set()


def test_an_agent_sees_only_their_own(people, calls):
    assert _visible(people["asha"]) == {"asha@x.com"}


def test_a_senior_agent_sees_their_team_not_the_floor(people, calls):
    team = Team.objects.create(name="North")
    AgentTeam.objects.create(team=team, agent=people["senior"])
    AgentTeam.objects.create(team=team, agent=people["asha"])

    assert _visible(people["senior"]) == {"asha@x.com"}


def test_a_team_lead_sees_their_team(people, calls):
    team = Team.objects.create(name="North")
    AgentTeam.objects.create(team=team, agent=people["bilal"], is_team_lead=True)
    AgentTeam.objects.create(team=team, agent=people["asha"])

    assert _visible(people["bilal"]) == {"asha@x.com", "bilal@x.com"}


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_admins_and_managers_see_everything(people, calls, role):
    assert _visible(people[role]) == {"asha@x.com", "bilal@x.com"}


def test_the_call_log_endpoint_applies_it(people, calls):
    request = APIRequestFactory().get("/api/v1/calls/")
    force_authenticate(request, user=people["hr"])
    response = CallLogListCreateView.as_view()(request)
    response.render()

    assert response.data["count"] == 0


# ---- Click-to-call -----------------------------------------------------

def _click(user, lead, **extra):
    request = APIRequestFactory().post(
        "/api/v1/calls/click-to-call/", {"lead_id": lead.pk, **extra}, format="json")
    force_authenticate(request, user=user)
    request.has_feature = lambda key: True
    response = ClickToCallView.as_view()(request)
    response.render()
    return response


def test_click_to_call_refuses_someone_elses_lead(people):
    lead = Lead.objects.create(name="Not yours", phone="+919812300010", assigned_to=people["bilal"])

    assert _click(people["asha"], lead).status_code == 404
    assert not CallLog.objects.filter(lead=lead).exists()


def test_click_to_call_refuses_a_number_not_on_the_lead(people):
    lead = Lead.objects.create(name="Yours", phone="+919812300011", assigned_to=people["asha"])

    r = _click(people["asha"], lead, phone_number="9999999999")

    assert r.status_code == 400
    assert not CallLog.objects.filter(lead=lead).exists()


def test_click_to_call_on_your_own_lead_works(people):
    lead = Lead.objects.create(name="Yours", phone="+919812300012", assigned_to=people["asha"])

    assert _click(people["asha"], lead).status_code == 200


# ---- WhatsApp and SMS --------------------------------------------------

def test_the_message_list_only_shows_visible_threads(people):
    mine = Lead.objects.create(name="Mine", phone="+919812300020", assigned_to=people["asha"])
    theirs = Lead.objects.create(name="Theirs", phone="+919812300021", assigned_to=people["bilal"])
    WhatsAppMessage.objects.create(lead=mine, direction="outbound", content="hi mine")
    WhatsAppMessage.objects.create(lead=theirs, direction="outbound", content="hi theirs")

    for params in ({}, {"lead": theirs.pk}):
        request = APIRequestFactory().get("/api/v1/comms/whatsapp/messages/", params)
        force_authenticate(request, user=people["asha"])
        response = WhatsAppMessageListView.as_view()(request)
        response.render()
        contents = {m["content"] for m in response.data["results"]}
        assert "hi theirs" not in contents


@pytest.mark.parametrize("view,payload", [
    (SendWhatsAppView, {"message": "hello"}),
    (SendSMSView, {"message": "hello"}),
])
def test_you_cannot_message_someone_elses_lead(people, view, payload):
    theirs = Lead.objects.create(name="Theirs", phone="+919812300030", assigned_to=people["bilal"])
    request = APIRequestFactory().post("/", {"lead_id": theirs.pk, **payload}, format="json")
    force_authenticate(request, user=people["asha"])
    request.has_feature = lambda key: True
    response = view.as_view()(request)

    assert response.status_code == 404
