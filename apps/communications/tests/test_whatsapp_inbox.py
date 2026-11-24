"""
The WhatsApp inbox.

A customer's reply used to be stored on the lead and seen only by whoever
opened that lead's WhatsApp tab. These pin what the inbox adds:

* every lead that has written in is a conversation, newest first; leads that
  were only ever messaged (a bulk campaign) are not;
* unread is shared by the team and cleared when someone opens the thread;
* agents see only their own leads' conversations, admins see all;
* free text is offered only inside Meta's 24-hour window;
* the owner is told once per unread run, not once per message.
"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent, Notification
from apps.communications import inbox
from apps.communications.models import WhatsAppConfig, WhatsAppMessage
from apps.communications.views import (
    WhatsAppInboxReadView, WhatsAppInboxSummaryView, WhatsAppInboxThreadView, WhatsAppInboxView,
)
from apps.core.constants import AgentRole
from apps.leads.models import Lead

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return Agent.objects.create_agent(
        email="admin@x.com", name="Admin", password="Pw@12345678", role=AgentRole.ADMIN,
    )


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="a@x.com", name="Asha", password="Pw@12345678")


@pytest.fixture
def bala():
    return Agent.objects.create_agent(email="b@x.com", name="Bala", password="Pw@12345678")


def _msg(lead, direction="inbound", text="Hi", minutes_ago=0, seen=False, account=None, **kw):
    m = WhatsAppMessage.objects.create(
        lead=lead, direction=direction, content=text, provider="meta_cloud",
        status="received" if direction == "inbound" else "sent", account=account, **kw,
    )
    at = timezone.now() - timedelta(minutes=minutes_ago)
    WhatsAppMessage.objects.filter(pk=m.pk).update(created_at=at, seen_at=at if seen else None)
    return m


def _get(view, user, query="", **kwargs):
    request = APIRequestFactory().get(f"/x/{query}")
    force_authenticate(request, user=user)
    return view.as_view()(request, **kwargs)


def _post(view, user, **kwargs):
    request = APIRequestFactory().post("/x/", {}, format="json")
    force_authenticate(request, user=user)
    return view.as_view()(request, **kwargs)


def _ids(response):
    return [row["lead_id"] for row in response.data["results"]]


# ============================================================
# The list
# ============================================================

def test_only_leads_that_wrote_in_are_conversations_newest_first(admin, asha):
    ravi = Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=asha)
    priya = Lead.objects.create(name="Priya", phone="+919812300002", assigned_to=asha)
    campaign_only = Lead.objects.create(name="Campaign", phone="+919812300003")
    _msg(ravi, text="Price?", minutes_ago=30)
    _msg(priya, text="Hello", minutes_ago=50)
    _msg(priya, "outbound", text="Hi Priya, here are the details", minutes_ago=5)
    _msg(campaign_only, "outbound", text="Diwali offer", minutes_ago=1)

    response = _get(WhatsAppInboxView, admin)

    assert response.status_code == 200
    assert _ids(response) == [priya.pk, ravi.pk]
    top = response.data["results"][0]
    assert top["last_message"]["direction"] == "outbound"
    assert top["last_message"]["text"].startswith("Hi Priya")
    assert top["unread"] == 1
    assert top["owner_name"] == "Asha"
    assert top["window"]["open"] is True


def test_unread_counts_only_unseen_inbound(admin):
    lead = Lead.objects.create(name="Ravi", phone="+919812300001")
    _msg(lead, text="one", seen=True, minutes_ago=10)
    _msg(lead, text="two", minutes_ago=5)
    _msg(lead, text="three", minutes_ago=4)
    _msg(lead, "outbound", text="reply", minutes_ago=3)

    row = _get(WhatsAppInboxView, admin).data["results"][0]
    assert row["unread"] == 2
    assert _get(WhatsAppInboxSummaryView, admin).data == {
        "unread_conversations": 1, "unread_messages": 2,
    }


def test_agents_see_only_their_own_leads_admins_see_all(admin, asha, bala):
    mine = Lead.objects.create(name="Mine", phone="+919812300001", assigned_to=asha)
    theirs = Lead.objects.create(name="Theirs", phone="+919812300002", assigned_to=bala)
    nobody = Lead.objects.create(name="Nobody", phone="+919812300003")
    for i, lead in enumerate((mine, theirs, nobody)):
        _msg(lead, minutes_ago=i)

    assert _ids(_get(WhatsAppInboxView, asha)) == [mine.pk]
    assert set(_ids(_get(WhatsAppInboxView, admin))) == {mine.pk, theirs.pk, nobody.pk}
    assert _get(WhatsAppInboxSummaryView, asha).data["unread_conversations"] == 1
    # Nor can an agent open someone else's thread.
    assert _get(WhatsAppInboxThreadView, asha, lead_id=theirs.pk).status_code == 404
    assert _post(WhatsAppInboxReadView, asha, lead_id=theirs.pk).status_code == 404


def test_filters(admin, asha):
    sales = WhatsAppConfig(label="Sales", provider="meta_cloud", credentials={"phone_number_id": "1"})
    sales.save()
    support = WhatsAppConfig(label="Support", provider="meta_cloud", credentials={"phone_number_id": "2"})
    support.save()
    a = Lead.objects.create(name="Anil Kumar", phone="+919812300001", assigned_to=admin)
    b = Lead.objects.create(name="Bharat", phone="+919812300002")
    c = Lead.objects.create(name="Chitra", phone="+919899900003", assigned_to=asha)
    _msg(a, seen=True, account=sales, minutes_ago=3)
    _msg(b, account=support, minutes_ago=2)
    _msg(c, account=sales, minutes_ago=1)

    assert _ids(_get(WhatsAppInboxView, admin, "?unread=1")) == [c.pk, b.pk]
    assert _ids(_get(WhatsAppInboxView, admin, "?mine=1")) == [a.pk]
    assert _ids(_get(WhatsAppInboxView, admin, "?unassigned=1")) == [b.pk]
    assert _ids(_get(WhatsAppInboxView, admin, f"?agent={asha.pk}")) == [c.pk]
    assert _ids(_get(WhatsAppInboxView, admin, f"?account={sales.pk}")) == [c.pk, a.pk]
    assert _ids(_get(WhatsAppInboxView, admin, "?q=kumar")) == [a.pk]
    assert _ids(_get(WhatsAppInboxView, admin, "?q=98999")) == [c.pk]


# ============================================================
# One thread
# ============================================================

def test_thread_reads_oldest_first_and_does_not_mark_read(admin):
    lead = Lead.objects.create(name="Ravi", phone="+919812300001")
    _msg(lead, text="first", minutes_ago=20)
    _msg(lead, "outbound", text="second", minutes_ago=10)
    _msg(lead, text="third", minutes_ago=1)

    data = _get(WhatsAppInboxThreadView, admin, lead_id=lead.pk).data
    assert [m["content"] for m in data["messages"]] == ["first", "second", "third"]
    assert data["unread"] == 2
    assert data["lead"]["name"] == "Ravi"
    assert data["window"]["open"] is True
    assert inbox.unread_count(lead) == 2


def test_the_reply_window_closes_24_hours_after_the_customer_wrote(admin):
    lead = Lead.objects.create(name="Ravi", phone="+919812300001")
    _msg(lead, minutes_ago=25 * 60)
    _msg(lead, "outbound", text="template follow-up", minutes_ago=5)

    data = _get(WhatsAppInboxThreadView, admin, lead_id=lead.pk).data
    assert data["window"]["open"] is False
    row = _get(WhatsAppInboxView, admin).data["results"][0]
    assert row["window"]["open"] is False


def test_opening_a_thread_clears_it_for_everyone_and_answers_the_notification(admin, asha):
    lead = Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=asha)
    _msg(lead, minutes_ago=2)
    _msg(lead, minutes_ago=1)
    Notification.objects.create(recipient=asha, kind="whatsapp_reply", title="Ravi wrote", lead_id_ref=lead.pk)

    response = _post(WhatsAppInboxReadView, admin, lead_id=lead.pk)

    assert response.status_code == 200
    assert response.data["cleared"] == 2
    assert response.data["unread_conversations"] == 0
    assert inbox.summary(asha)["unread_messages"] == 0
    assert Notification.objects.get(lead_id_ref=lead.pk).is_read


# ============================================================
# Telling people
# ============================================================

def test_the_owner_is_notified_once_per_unread_run(asha):
    lead = Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=asha)
    with patch("apps.core.consumers.send_agent_notification") as live, \
            patch("apps.core.consumers.broadcast_to_monitors") as monitors:
        _msg(lead, text="Hi")
        inbox.message_arrived(lead, "Hi")
        _msg(lead, text="Are you there?")
        inbox.message_arrived(lead, "Are you there?")

    notes = Notification.objects.filter(recipient=asha, kind="whatsapp_reply")
    assert notes.count() == 1
    note = notes.get()
    assert note.title == "Ravi wrote on WhatsApp"
    assert note.body == "Hi"
    assert note.url == f"/inbox/{lead.pk}"
    # Every message still refreshes the open screens.
    inbox_events = [c for c in live.call_args_list if c.kwargs.get("event_type") == "whatsapp_inbox"]
    assert len(inbox_events) == 2
    assert monitors.call_count == 2

    # Read, then a new message: a new run, a new notification.
    inbox.mark_seen(lead)
    _msg(lead, text="Hello again")
    inbox.message_arrived(lead, "Hello again")
    assert Notification.objects.filter(recipient=asha, kind="whatsapp_reply").count() == 2


def test_an_unassigned_lead_notifies_nobody_but_still_shows_in_the_inbox(admin):
    lead = Lead.objects.create(name="Ravi", phone="+919812300001")
    _msg(lead)
    inbox.message_arrived(lead, "Hi")
    assert not Notification.objects.filter(kind="whatsapp_reply").exists()
    assert _get(WhatsAppInboxSummaryView, admin).data["unread_conversations"] == 1


def test_a_bsp_reply_lands_unread_in_the_inbox(asha):
    from apps.communications.whatsapp_webhooks import Inbound, record_inbound

    lead = Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=asha)
    record_inbound("interakt", Inbound(phone="+919812300001", text="Interested", message_id="m-1"))

    assert inbox.unread_count(lead) == 1
    assert Notification.objects.filter(recipient=asha, kind="whatsapp_reply").count() == 1
