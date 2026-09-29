"""
Presence that survives a working day.

The daily login report is built from AgentStatusLog, so the intervals have to
be right. A flat 60-second stale sweep turned every call over a minute into
"offline" (the app is frozen while the phone's dialer is on screen), closed
intervals at sweep time rather than at the last sign of life, and a heartbeat
could not put a swept agent back — the app only reports changes.
"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.authentication.models import Agent, AgentStatus, AgentStatusLog
from apps.authentication.presence import (
    compute_today_totals, set_agent_status, sweep_stale, touch_heartbeat,
)
from apps.core.constants import AgentWorkStatus as S

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_broadcast():
    with patch("apps.authentication.presence._broadcast"):
        yield


@pytest.fixture
def agent():
    return Agent.objects.create_agent(email="a@x.com", name="Asha", password="Pw@12345678")


def _silent_for(agent, seconds):
    AgentStatus.objects.filter(agent=agent).update(
        last_seen=timezone.now() - timedelta(seconds=seconds))


def _status(agent):
    return AgentStatus.objects.get(agent=agent).status


def test_a_long_call_is_not_swept_offline(agent):
    set_agent_status(agent, S.ON_CALL)
    _silent_for(agent, 10 * 60)  # ten-minute call, app frozen behind the dialer

    sweep_stale()

    assert _status(agent) == S.ON_CALL


def test_a_lunch_break_with_the_phone_locked_stays_a_break(agent):
    set_agent_status(agent, S.BREAK, break_reason="Lunch")
    _silent_for(agent, 45 * 60)

    sweep_stale()

    assert _status(agent) == S.BREAK


def test_an_idle_agent_who_vanished_is_swept(agent):
    set_agent_status(agent, S.AVAILABLE)
    _silent_for(agent, 5 * 60)

    sweep_stale()

    assert _status(agent) == S.OFFLINE


def test_the_swept_interval_ends_at_the_last_sign_of_life(agent):
    set_agent_status(agent, S.AVAILABLE)
    _silent_for(agent, 5 * 60)
    last_seen = AgentStatus.objects.get(agent=agent).last_seen

    sweep_stale()

    log = AgentStatusLog.objects.get(agent=agent, status=S.AVAILABLE)
    assert log.ended_at == last_seen, "time after the agent vanished must not count as worked"


def test_a_heartbeat_puts_a_swept_agent_back(agent):
    set_agent_status(agent, S.AVAILABLE)
    _silent_for(agent, 5 * 60)
    sweep_stale()

    touch_heartbeat(agent, status=S.AVAILABLE)

    assert _status(agent) == S.AVAILABLE


def test_a_plain_heartbeat_still_works_for_older_apps(agent):
    set_agent_status(agent, S.AVAILABLE)
    _silent_for(agent, 30)

    touch_heartbeat(agent)

    assert (timezone.now() - AgentStatus.objects.get(agent=agent).last_seen).total_seconds() < 5


def test_todays_totals_include_a_session_started_before_midnight(agent):
    midnight = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    AgentStatusLog.objects.create(agent=agent, status=S.AVAILABLE,
                                  started_at=midnight - timedelta(hours=1))
    now = midnight + timedelta(minutes=30)

    totals = compute_today_totals(agent, now=now)

    assert totals[S.AVAILABLE] == 30 * 60
