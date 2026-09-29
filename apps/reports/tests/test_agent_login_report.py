"""
The agent login report: every agent, every day, from the presence intervals.
"""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent, AgentStatusLog
from apps.calls.models import CallLog
from apps.core.constants import AgentRole, AgentWorkStatus as S
from apps.reports.login_report import build_login_report
from apps.reports.views import AgentLoginReportView

pytestmark = pytest.mark.django_db


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="asha@x.com", name="Asha", password="Pw@12345678")


@pytest.fixture
def bilal():
    return Agent.objects.create_agent(email="bilal@x.com", name="Bilal", password="Pw@12345678")


def _at(hour, minute=0, days_ago=0):
    day = timezone.localdate() - timedelta(days=days_ago)
    return timezone.make_aware(
        timezone.datetime(day.year, day.month, day.day, hour, minute),
        timezone.get_current_timezone(),
    )


def _interval(agent, status, start, end, reason=""):
    return AgentStatusLog.objects.create(
        agent=agent, status=status, started_at=start, ended_at=end,
        duration_seconds=int((end - start).total_seconds()), break_reason=reason,
    )


def _row(rows, agent, days_ago=0):
    day = (timezone.localdate() - timedelta(days=days_ago)).isoformat()
    return next(r for r in rows if r["agent_id"] == agent.pk and r["date"] == day)


def test_a_full_day_adds_up(asha):
    _interval(asha, S.AVAILABLE, _at(9, 30, 1), _at(10, 0, 1))
    _interval(asha, S.ON_CALL, _at(10, 0, 1), _at(10, 20, 1))
    _interval(asha, S.WRAP_UP, _at(10, 20, 1), _at(10, 25, 1))
    _interval(asha, S.BREAK, _at(13, 0, 1), _at(13, 45, 1), "Lunch")
    CallLog.objects.create(agent=asha, phone_number="+919812300001",
                           started_at=_at(10, 0, 1), is_connected=True)

    day = timezone.localdate() - timedelta(days=1)
    row = _row(build_login_report(day, day), asha, days_ago=1)

    assert row["first_online"].startswith(f"{day.isoformat()}T09:30")
    assert row["last_seen"].startswith(f"{day.isoformat()}T13:45")
    assert row["available_seconds"] == 30 * 60
    assert row["on_call_seconds"] == 20 * 60
    assert row["wrap_up_seconds"] == 5 * 60
    assert row["break_seconds"] == 45 * 60
    assert row["online_seconds"] == 100 * 60
    assert row["break_count"] == 1 and row["break_reasons"] == "Lunch ×1"
    assert row["calls"] == 1 and row["connected_calls"] == 1
    assert row["occupancy"] == 20


def test_today_is_live(asha):
    from apps.authentication.models import AgentStatus

    now = timezone.now()
    AgentStatusLog.objects.create(agent=asha, status=S.AVAILABLE, started_at=now - timedelta(minutes=12))
    AgentStatus.objects.create(agent=asha, status=S.AVAILABLE, since=now - timedelta(minutes=12), last_seen=now)

    row = _row(build_login_report(timezone.localdate(), timezone.localdate(), now=now), asha)

    assert row["online_now"] is True
    assert row["available_seconds"] == 12 * 60


def test_an_agent_who_never_logged_in_still_has_a_row(asha, bilal):
    today = timezone.localdate()
    row = _row(build_login_report(today, today), bilal)

    assert row["first_online"] is None and row["online_seconds"] == 0


def test_a_range_gives_one_row_per_agent_per_day(asha, bilal):
    today = timezone.localdate()
    rows = build_login_report(today - timedelta(days=2), today)

    ours = [r for r in rows if r["agent_id"] in (asha.pk, bilal.pk)]
    assert len(ours) == 6
    assert ours[0]["date"] == today.isoformat(), "newest day first"


# ---- the endpoint ----------------------------------------------------------

def _get(user, **params):
    request = APIRequestFactory().get("/api/v1/reports/agent-login/", params)
    force_authenticate(request, user=user)
    request.has_feature = lambda key: True
    response = AgentLoginReportView.as_view()(request)
    if hasattr(response, "render") and not getattr(response, "streaming", False):
        response.render()
    return response


def test_agents_cannot_see_the_report(asha):
    assert _get(asha).status_code == 403


def test_a_manager_gets_todays_report_by_default(asha):
    manager = Agent.objects.create_agent(email="m@x.com", name="Mona", password="Pw@12345678",
                                         role=AgentRole.MANAGER)
    response = _get(manager)

    assert response.status_code == 200
    assert response.data["date_from"] == timezone.localdate().isoformat()
    assert any(r["agent_id"] == asha.pk for r in response.data["rows"])


def test_the_report_downloads_as_csv(asha):
    manager = Agent.objects.create_agent(email="m@x.com", name="Mona", password="Pw@12345678",
                                         role=AgentRole.MANAGER)
    response = _get(manager, format="csv")

    body = b"".join(response.streaming_content).decode("utf-8")
    assert response["Content-Type"].startswith("text/csv")
    assert "First online" in body and "Asha" in body


def test_csv_times_and_durations_read_like_a_timesheet():
    from apps.reports.login_report import csv_cell

    assert csv_cell("first_online", "2026-09-29T14:22:00.180225+05:30") == "14:22"
    assert csv_cell("online_seconds", 11131) == "3:05"
    assert csv_cell("break_seconds", 0) == "0:00"
    assert csv_cell("last_seen", None) == ""


def test_more_than_a_month_is_refused():
    manager = Agent.objects.create_agent(email="m@x.com", name="Mona", password="Pw@12345678",
                                         role=AgentRole.MANAGER)
    today = timezone.localdate()

    response = _get(manager, date_from=(today - timedelta(days=40)).isoformat(), date_to=today.isoformat())

    assert response.status_code == 400


def test_an_open_interval_without_a_live_status_is_not_online_now(asha):
    """The row must not say "Online now" for an agent the board shows offline."""
    now = timezone.now()
    AgentStatusLog.objects.create(agent=asha, status=S.AVAILABLE, started_at=now - timedelta(minutes=5))

    row = _row(build_login_report(timezone.localdate(), timezone.localdate(), now=now), asha)

    assert row["online_now"] is False
