"""
One agent's calls, connected calls and talk time read the same on the Calls
page, Live Agents and the Login report.

They used to disagree: the Calls page's boxes ignored the search (so looking
up one agent still showed everyone's calls), and "talk" on Live Agents and the
report was the dialer's on-call status time — dialling and ringing included —
not the connected calls' durations the Calls page shows.
"""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent, AgentStatusLog
from apps.authentication.views import LiveAgentsAPIView
from apps.calls.models import CallLog
from apps.calls.views import CallStatsView
from apps.core.constants import AgentWorkStatus as S
from apps.reports.login_report import build_login_report

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(email="adm@f.l", name="Admin", password="Pw@12345678")


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="asha@f.l", name="Asha Rao", password="Pw@12345678")


@pytest.fixture
def bilal():
    return Agent.objects.create_agent(email="bilal@f.l", name="Bilal Khan", password="Pw@12345678")


def _today(hour, minute=0):
    d = timezone.localdate()
    return timezone.make_aware(timezone.datetime(d.year, d.month, d.day, hour, minute),
                               timezone.get_current_timezone())


def _call(agent, at, connected, seconds):
    return CallLog.objects.create(agent=agent, phone_number="+919812300001", started_at=at,
                                  is_connected=connected, duration_seconds=seconds)


@pytest.fixture
def day(asha, bilal):
    now = timezone.now()
    start = min(_today(0, 5), now - timedelta(minutes=30))
    _call(asha, start, True, 60)
    _call(asha, start + timedelta(minutes=2), False, 25)   # ring time, not talk
    _call(asha, start + timedelta(minutes=4), True, 30)
    _call(bilal, start + timedelta(minutes=6), True, 600)
    # Asha's dialer status: 10 minutes "on call" — dialling and ringing too.
    AgentStatusLog.objects.create(agent=asha, status=S.ON_CALL, started_at=start,
                                  ended_at=start + timedelta(minutes=10), duration_seconds=600)
    return {"calls": 3, "connected": 2, "talk_seconds": 90}


def _get(view, user, **params):
    req = APIRequestFactory().get("/x/", params)
    force_authenticate(req, user=user)
    req.has_feature = lambda k: True
    r = view.as_view()(req)
    r.render()
    assert r.status_code == 200, r.data
    return r.data


def _calls_page(admin, **filters):
    today = timezone.localdate().isoformat()
    p = _get(CallStatsView, admin, date_from=today, date_to=today, **filters)["period"]
    return {"calls": p["total_calls"], "connected": p["connected_calls"],
            "talk_seconds": p["total_duration_seconds"]}


def test_calls_page_boxes_follow_the_agent_search(admin, asha, day):
    assert _calls_page(admin, q="Asha") == day
    assert _calls_page(admin, agent=str(asha.pk)) == day


def test_live_agents_shows_the_calls_page_figures(admin, asha, day):
    agents = _get(LiveAgentsAPIView, admin)["agents"]
    row = next(a for a in agents if a["agent_id"] == asha.pk)
    assert row["calls"] == day == _calls_page(admin, agent=str(asha.pk))


def test_login_report_shows_the_calls_page_figures(admin, asha, day):
    today = timezone.localdate()
    row = next(r for r in build_login_report(today, today)
               if r["agent_id"] == asha.pk and r["date"] == today.isoformat())
    assert {"calls": row["calls"], "connected": row["connected_calls"],
            "talk_seconds": row["talk_seconds"]} == day
    # The dialer's on-call time stays as it is, under its own name.
    assert row["on_call_seconds"] == 600
