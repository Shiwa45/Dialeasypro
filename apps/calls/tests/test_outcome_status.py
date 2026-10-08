"""
A call outcome moves the lead to the status it stands for.

An outcome never reached the lead: an agent saved "Connected – Interested",
the lead stayed at Attempted, and the Leads screen's Interested filter (which
reads the lead's status) showed none of the leads the team had marked.
"""
import importlib
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.calls.models import CallDisposition, CallLog
from apps.calls.serializers import CallDispositionSerializer
from apps.leads.models import Lead, LeadActivity
from apps.leads.views import LeadListCreateView

pytestmark = pytest.mark.django_db
backfill = importlib.import_module("apps.calls.migrations.0005_backfill_outcome_lead_status")


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="asha@example.com", name="Asha", password="Pw@12345678")


@pytest.fixture
def interested():
    return CallDisposition.objects.create(name="Interested", slug="interested-x", lead_status="interested")


@pytest.fixture
def busy():
    return CallDisposition.objects.create(name="Busy", slug="busy-x")


def _lead(agent, status="attempted", phone="+919812300001"):
    return Lead.objects.create(name="Ravi", phone=phone, assigned_to=agent, status=status)


def _call(agent, lead, disposition, minutes_ago=0):
    return CallLog.objects.create(
        agent=agent, lead=lead, phone_number=lead.phone, disposition=disposition,
        started_at=timezone.now() - timedelta(minutes=minutes_ago),
    )


def test_an_interested_outcome_makes_the_lead_interested(asha, interested):
    lead = _lead(asha)

    _call(asha, lead, interested)

    lead.refresh_from_db()
    assert lead.status == "interested"
    # One feed line for the call, saying what it did to the lead.
    line = LeadActivity.objects.get(lead=lead, activity_type="call")
    assert line.meta["new_status"] == "interested"
    assert "Interested" in line.description


def test_the_interested_filter_now_finds_it(asha, interested):
    lead = _lead(asha)
    _call(asha, lead, interested)

    request = APIRequestFactory().get("/api/v1/leads/?status=interested")
    force_authenticate(request, user=asha)
    response = LeadListCreateView.as_view()(request)

    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == lead.pk


def test_an_outcome_without_a_status_leaves_the_lead(asha, busy):
    lead = _lead(asha, status="contacted")

    _call(asha, lead, busy)

    lead.refresh_from_db()
    assert lead.status == "contacted"


def test_a_won_deal_is_not_reopened_by_a_call(asha, interested):
    lead = _lead(asha, status="converted")

    _call(asha, lead, interested)

    lead.refresh_from_db()
    assert lead.status == "converted"


def test_admins_set_it_per_outcome_and_only_to_real_statuses():
    ok = CallDispositionSerializer(data={"name": "Site visit booked", "lead_status": "negotiation"})
    assert ok.is_valid(), ok.errors

    bad = CallDispositionSerializer(data={"name": "Odd", "lead_status": "maybe"})
    assert not bad.is_valid()
    assert "lead_status" in bad.errors


# ---- The one-time migration ---------------------------------------------

@pytest.mark.parametrize("slug,name,expected", [
    ("connected_interested", "Connected – Interested", "interested"),
    ("interested", "Interested", "interested"),
    ("connected_not_interested", "Connected – Not Interested", "not_interested"),
    ("not-interested", "Not interested", "not_interested"),
    ("connected_callback", "Connected – Callback Requested", "follow_up"),
    ("call-back-later", "Call back later", "follow_up"),
    ("busy", "Busy", ""),
    ("wrong_number", "Wrong Number", ""),
    ("connected_purchased", "Connected – Already Purchased", ""),
])
def test_existing_outcomes_are_read_by_their_words(slug, name, expected):
    assert backfill.guess_status(slug, name) == expected


def test_existing_leads_take_their_latest_outcome(asha, interested, busy):
    CallDisposition.objects.filter(pk=interested.pk).update(lead_status="")  # as before 0004
    marked = _lead(asha, phone="+919812300011")
    moved_on = _lead(asha, status="negotiation", phone="+919812300012")
    called_again = _lead(asha, phone="+919812300013")
    # Created as they were before this change: the outcome did not touch them.
    CallLog.objects.bulk_create([
        CallLog(agent=asha, lead=marked, phone_number=marked.phone, disposition=interested,
                started_at=timezone.now()),
        CallLog(agent=asha, lead=moved_on, phone_number=moved_on.phone, disposition=interested,
                started_at=timezone.now()),
        CallLog(agent=asha, lead=called_again, phone_number=called_again.phone, disposition=interested,
                started_at=timezone.now() - timedelta(hours=2)),
        CallLog(agent=asha, lead=called_again, phone_number=called_again.phone, disposition=busy,
                started_at=timezone.now()),
    ])

    backfill.forwards(django_apps, None)

    interested.refresh_from_db()
    assert interested.lead_status == "interested", "named Interested, so it got the status"
    statuses = dict(Lead.objects.values_list("pk", "status"))
    assert statuses[marked.pk] == "interested"
    assert statuses[moved_on.pk] == "negotiation", "a lead moved on by hand is left alone"
    assert statuses[called_again.pk] == "attempted", "the latest outcome (Busy) wins"
