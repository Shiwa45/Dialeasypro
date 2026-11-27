"""
WhatsApp numbers assigned to agents.

An admin can tie a number to agents (WhatsAppConfig.agents). These pin what
that means:

* an agent with numbers sees and sends from only those, and starts on theirs;
* a free-text reply still goes from the number the customer wrote to — Meta
  refuses free text from any other number;
* a template goes from one of the agent's numbers that can send it, or is
  refused with the reason;
* admins, managers and agents with no number are not restricted (so nothing
  changes for a tenant until an admin assigns a number).
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.communications.models import WhatsAppConfig, WhatsAppMessage, WhatsAppTemplate
from apps.communications.views import WhatsAppAccountDetailView, WhatsAppSendersView
from apps.communications.whatsapp_accounts import (
    allowed_account_ids, preferred_account, resolve_sender,
)
from apps.core.constants import AgentRole, FeatureKey
from apps.leads.models import Lead

pytestmark = pytest.mark.django_db


def _account(label, waba="", **kw):
    acct = WhatsAppConfig(
        label=label, provider="meta_cloud", is_active=True,
        credentials={"access_token": "t", "phone_number_id": f"pn-{label}", "business_account_id": waba},
        **kw,
    )
    acct.save()
    return acct


def _template(name="offer", account=None):
    return WhatsAppTemplate.objects.create(
        name=name, body_text="Hi {{1}}", variable_mapping={"1": "name"}, status="approved", account=account,
    )


@pytest.fixture
def numbers():
    sales = _account("Sales", waba="W1", is_default=True)
    support = _account("Support", waba="W2")
    north = _account("North", waba="W3")
    return sales, support, north


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="asha@x.com", name="Asha", password="Pw@12345678")


@pytest.fixture
def manager():
    return Agent.objects.create_agent(email="m@x.com", name="Mona", password="Pw@12345678",
                                      role=AgentRole.MANAGER)


@pytest.fixture
def lead(asha):
    return Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=asha)


def _get(view, user, **kwargs):
    request = APIRequestFactory().get("/x/")
    force_authenticate(request, user=user)
    request.has_feature = lambda key: True
    return view.as_view()(request, **kwargs)


# ============================================================
# Who is restricted
# ============================================================

def test_nobody_is_restricted_until_a_number_is_assigned(numbers, asha, manager):
    sales, support, north = numbers
    assert allowed_account_ids(asha) is None
    assert preferred_account(asha) == sales  # the company default

    support.agents.add(asha, manager)
    assert allowed_account_ids(asha) == [support.pk]
    assert preferred_account(asha) == support
    assert allowed_account_ids(manager) is None  # managers and admins never are


def test_the_agents_list_shows_only_their_numbers(numbers, asha, manager):
    sales, support, north = numbers
    support.agents.add(asha)
    north.agents.add(asha)

    mine = _get(WhatsAppSendersView, asha).data
    assert [s["label"] for s in mine] == ["North", "Support"]
    assert [s["label"] for s in mine if s["preferred"]] == ["North"]

    everyone = _get(WhatsAppSendersView, manager).data
    assert len(everyone) == 3 and [s["label"] for s in everyone if s["preferred"]] == ["Sales"]


# ============================================================
# Which number a send uses
# ============================================================

def test_an_agent_cannot_pick_a_number_that_is_not_theirs(numbers, asha, lead):
    sales, support, _ = numbers
    support.agents.add(asha)
    sender = resolve_sender(account_id=sales.pk, template=_template(account=sales), lead=lead, agent=asha)
    assert sender.account is None and "Support" in sender.error
    assert resolve_sender(account_id=support.pk, lead=lead, agent=asha).account == support


def test_a_new_message_starts_on_the_agents_number(numbers, asha, lead):
    _, support, _ = numbers
    support.agents.add(asha)
    assert resolve_sender(lead=lead, agent=asha).account == support


def test_a_reply_stays_on_the_number_the_customer_wrote_to(numbers, asha, lead):
    sales, support, _ = numbers
    support.agents.add(asha)
    WhatsAppMessage.objects.create(lead=lead, direction="inbound", content="Price?", status="received",
                                   account=sales)
    # Free text, nothing picked: the customer's number, though not Asha's.
    assert resolve_sender(lead=lead, agent=asha).account == sales
    # And picking it explicitly for the reply is allowed too.
    assert resolve_sender(account_id=sales.pk, lead=lead, agent=asha).account == sales


def test_a_template_goes_from_an_assigned_number_that_can_send_it(numbers, asha, lead):
    sales, support, north = numbers
    support.agents.add(asha)
    north.agents.add(asha)
    WhatsAppMessage.objects.create(lead=lead, direction="inbound", content="Hi", status="received",
                                   account=sales)
    # The template belongs to North's account; the lead wrote to Sales (not
    # hers), and Support can't send it — so North.
    assert resolve_sender(template=_template(account=north), lead=lead, agent=asha).account == north
    # A shared template goes from her preferred number.
    assert resolve_sender(template=_template(name="shared"), lead=lead, agent=asha).account == north


def test_a_template_none_of_her_numbers_can_send_is_refused(numbers, asha, lead):
    sales, support, _ = numbers
    support.agents.add(asha)
    sender = resolve_sender(template=_template(account=sales), lead=lead, agent=asha)
    assert sender.account is None and 'template "offer"' in sender.error


def test_unrestricted_behaviour_is_unchanged(numbers, manager, lead):
    sales, support, _ = numbers
    WhatsAppMessage.objects.create(lead=lead, direction="inbound", content="Hi", status="received",
                                   account=support)
    assert resolve_sender(lead=lead, agent=manager).account == support
    assert resolve_sender(template=_template(account=sales), lead=lead, agent=manager).account == sales


# ============================================================
# Assigning, through the API
# ============================================================

def test_admin_assigns_agents_to_a_number(numbers, asha):
    _, support, _ = numbers
    admin = Agent.objects.create_agent(email="ad@x.com", name="Admin", password="Pw@12345678",
                                       role=AgentRole.ADMIN)
    request = APIRequestFactory().patch("/x/", {"agents": [asha.pk]}, format="json")
    force_authenticate(request, user=admin)
    request.has_feature = lambda key: True
    response = WhatsAppAccountDetailView.as_view()(request, pk=support.pk)

    assert response.status_code == 200, response.data
    assert response.data["agents"] == [asha.pk]
    assert response.data["agent_names"] == [{"id": asha.pk, "name": "Asha"}]
    assert list(asha.whatsapp_numbers.all()) == [support]
