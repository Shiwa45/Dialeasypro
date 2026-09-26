"""
What "today" means on a dashboard read at 2am.

Every today-count was computed from `timezone.now().date()`, which is the
date in UTC. The tenants are in IST (UTC+5:30), and the querysets compare
with `__date`, which Django evaluates in the ACTIVE timezone. So between
midnight and 5:30am local the two disagreed: the label said today, the
window was yesterday, and an admin opening the CRM early saw a new-lead
count that belonged to the previous day — reverting at 5:30 with no
explanation.

`timezone.localdate()` is the same thing in the tenant's own day.
"""
from datetime import datetime, timezone as dt_timezone

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.leads.models import Lead
from apps.leads.views import LeadDashboardStatsView
from apps.reports.views import DailyActivityView

pytestmark = pytest.mark.django_db

# 01:00 IST on 12 March 2026 — which is still 19:30 on the 11th in UTC.
EARLY_IST = datetime(2026, 3, 11, 19, 30, tzinfo=dt_timezone.utc)


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(
        email="owner@example.com", name="Owner", password="Pw@12345678",
    )


def _lead_created_at(when, **extra):
    lead = Lead.objects.create(
        name="Night Arrival", phone="+919812300777", status="new", **extra,
    )
    # created_at is auto_now_add, so it has to be set afterwards.
    Lead.objects.filter(pk=lead.pk).update(created_at=when)
    return lead


def _stats(user):
    request = APIRequestFactory().get("/api/v1/leads/stats/")
    force_authenticate(request, user=user)
    response = LeadDashboardStatsView.as_view()(request)
    response.render()
    return response.data


def _daily(user):
    request = APIRequestFactory().get("/api/v1/reports/daily-activity/")
    force_authenticate(request, user=user)
    # The view is plan-gated and TenantFeatureFlagMiddleware does not run when
    # a view is called directly; without this it answers 402 rather than data.
    request.has_feature = lambda key: True
    response = DailyActivityView.as_view()(request)
    response.render()
    return response.data


def test_today_is_the_tenants_today_not_utcs(admin):
    """
    localdate() and now().date() are the same thing for most of the day and
    differ for the 5.5 hours that matter. Pinning the rule itself keeps the
    next person from 'simplifying' it back.
    """
    with timezone.override("Asia/Kolkata"):
        assert timezone.localdate(EARLY_IST) == datetime(2026, 3, 12).date()
        assert EARLY_IST.date() == datetime(2026, 3, 11).date()


def test_the_dashboard_reports_the_same_day_from_both_endpoints(admin):
    """
    The two cards sit side by side and are served by different views. They
    used to derive 'today' separately, so they could disagree.
    """
    Lead.objects.create(name="Fresh", phone="+919812300778", status="new")

    assert _daily(admin)["date"] == str(timezone.localdate())
    assert _stats(admin)["today"]["new_leads"] == _daily(admin)["leads"]["new_today"]


def test_a_lead_created_now_is_counted_today(admin):
    before = _stats(admin)["today"]["new_leads"]

    Lead.objects.create(name="Right now", phone="+919812300779", status="new")

    assert _stats(admin)["today"]["new_leads"] == before + 1
