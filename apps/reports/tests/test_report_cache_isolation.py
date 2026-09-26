"""
A tenant's reports are its own.

The report cache keys named the report and the dates and nothing else, on a
cache whose prefix is the same for every tenant. Whichever tenant computed a
report first had it served to every other tenant asking for the same dates
within five minutes — agent names and performance, lead sources, call
analytics, the pipeline funnel. With the dashboard defaulting to "Today",
every tenant's call and pipeline panels shared one key all day.

These tests plant a report under another tenant's key and check it is never
returned — the same way the leak was demonstrated against the live server.
"""
import pytest
from django.core.cache import cache
from django.db import connection
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.reports import views as report_views
from apps.reports.views import (
    CallAnalyticsReportView, ConversionFunnelView, LeadSourceReportView,
    AgentPerformanceReportView,
)

pytestmark = pytest.mark.django_db

FROM, TO = "2020-01-01", "2020-01-02"
SENTINEL = "SENTINEL_FROM_ANOTHER_TENANT"


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(
        email="owner@example.com", name="Owner", password="Pw@12345678",
    )


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


def _get(view, user, path):
    request = APIRequestFactory().get(path, {"date_from": FROM, "date_to": TO})
    force_authenticate(request, user=user)
    request.has_feature = lambda key: True
    response = view.as_view()(request)
    response.render()
    return response


def _other_tenant_key(kind, *parts):
    """The key another tenant's request would have written."""
    return ":".join(["report", "some_other_tenant", kind, *parts])


def _old_style_key(kind, *parts):
    """The key every tenant used to share."""
    return ":".join(["report", kind, *parts])


@pytest.mark.parametrize("kind,parts,view,path,field", [
    ("lead_sources", (FROM, TO), LeadSourceReportView, "/api/v1/reports/lead-sources/", "by_source"),
    ("agent_perf", (FROM, TO, "all"), AgentPerformanceReportView, "/api/v1/reports/agent-performance/", "agents"),
])
def test_another_tenants_report_is_never_served(admin, kind, parts, view, path, field):
    poison = [{"source": SENTINEL, "name": SENTINEL, "total": 999}]
    cache.set(_other_tenant_key(kind, *parts), poison, 120)
    cache.set(_old_style_key(kind, *parts), poison, 120)

    body = str(_get(view, admin, path).data)

    assert SENTINEL not in body


@pytest.mark.parametrize("kind,view,path", [
    ("call_analytics", CallAnalyticsReportView, "/api/v1/reports/call-analytics/"),
    ("funnel", ConversionFunnelView, "/api/v1/reports/conversion-funnel/"),
])
def test_scoped_reports_do_not_share_either(admin, kind, view, path):
    poison = {"period": {"date_from": SENTINEL}, "funnel": [SENTINEL], "daily_trend": [SENTINEL]}
    cache.set(_other_tenant_key(kind, "all", FROM, TO), poison, 120)
    cache.set(_old_style_key(kind, "all", FROM, TO), poison, 120)

    body = str(_get(view, admin, path).data)

    assert SENTINEL not in body


def test_the_key_names_the_current_tenant():
    key = report_views._report_key("lead_sources", FROM, TO)

    assert connection.schema_name in key.split(":")


def test_caching_still_works_within_a_tenant(admin):
    """Scoping must not turn the cache off: a planted value under THIS
    tenant's key is what comes back."""
    own = [{"source": "OWN_CACHED_VALUE", "total": 1}]
    cache.set(report_views._report_key("lead_sources", FROM, TO), own, 120)

    body = str(_get(LeadSourceReportView, admin, "/api/v1/reports/lead-sources/").data)

    assert "OWN_CACHED_VALUE" in body
