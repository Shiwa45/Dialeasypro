"""
The app's home card and the Follow-ups screen count the same leads.

They used three rules: the home card counted follow-ups dated today (this
morning's overdue ones included, and twice for a lead with two), the overdue
count counted leads, and the Follow-ups screen's "Due Today" tab sent
`followup_due_today`, which the API ignored — so it listed every lead.

Now both are by lead, on the lead's next open follow-up, and each lead is in
exactly one: overdue if that moment has passed, due today if it is later
today.
"""
from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.leads.models import FollowUp, Lead
from apps.leads.views import LeadListCreateView, LeadDashboardStatsView

pytestmark = pytest.mark.django_db


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="asha@example.com", name="Asha", password="Pw@12345678")


def _lead(agent, phone, *followups):
    lead = Lead.objects.create(name=f"Lead {phone[-2:]}", phone=phone, assigned_to=agent)
    for when in followups:
        FollowUp.objects.create(lead=lead, assigned_to=agent, followup_type="call", scheduled_at=when)
    return lead


def _get(view, user, query=""):
    request = APIRequestFactory().get(f"/api/v1/leads/?{query}")
    force_authenticate(request, user=user)
    response = view.as_view()(request)
    return response.data


@pytest.fixture
def day(asha):
    now = timezone.now()
    end_of_today = timezone.make_aware(
        datetime.combine(timezone.localdate() + timedelta(days=1), time.min),
        timezone.get_current_timezone(),
    )
    later_today = min(now + timedelta(minutes=30), end_of_today - timedelta(minutes=1))
    return {
        # Overdue: yesterday, and an hour ago (with a second one later today).
        "yesterday": _lead(asha, "+919812300001", now - timedelta(days=1)),
        "this_morning": _lead(asha, "+919812300002", now - timedelta(hours=1), later_today),
        # Due later today, with two follow-ups: still one lead.
        "today_twice": _lead(asha, "+919812300003", later_today, later_today + timedelta(seconds=30)),
        # Neither.
        "tomorrow": _lead(asha, "+919812300004", end_of_today + timedelta(hours=2)),
        "none": _lead(asha, "+919812300005"),
    }


def test_the_tabs_put_each_lead_in_one_bucket(asha, day):
    overdue = {r["id"] for r in _get(LeadListCreateView, asha, "overdue=true")["results"]}
    due_today = {r["id"] for r in _get(LeadListCreateView, asha, "followup_due_today=true")["results"]}

    assert overdue == {day["yesterday"].pk, day["this_morning"].pk}
    assert due_today == {day["today_twice"].pk}, "the Due Today tab no longer lists every lead"


def test_the_home_card_counts_what_the_tabs_list(asha, day):
    stats = _get(LeadDashboardStatsView, asha)["today"]

    assert stats["overdue_followups"] == 2
    assert stats["followups_due"] == 1, "leads, not follow-ups, and not this morning's overdue one"
