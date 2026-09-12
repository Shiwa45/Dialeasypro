"""
Follow-up reminders and the overdue chaser.

Two things were wrong before this.

The dispatcher was scheduled at crontab(hour=3, minute=0) — once a day — while
the task only looked a short way ahead. The server therefore only ever
reminded anyone about follow-ups falling in one narrow morning window; a
follow-up set for 4pm passed unannounced.

And nothing chased an overdue one. send_followup_reminders_for_tenant fires
once per follow-up and sets reminder_sent, so a follow-up four hours late had
already had its single notification and would never be mentioned again.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from django.db import connection

from apps.authentication.models import Agent, Notification, NotificationKind
from apps.leads.models import FollowUp, Lead
from apps.leads.tasks import (
    chase_overdue_followups_for_tenant,
    send_followup_reminders_for_tenant,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent():
    return Agent.objects.create_agent(
        email="fu@example.com", name="Follow Up Tester", password="x",
    )


@pytest.fixture
def lead(agent):
    return Lead.objects.create(name="Ravi Kumar", phone="+919812345678", assigned_to=agent)


def _followup(lead, agent, *, minutes_from_now):
    return FollowUp.objects.create(
        lead=lead, assigned_to=agent, followup_type="call",
        scheduled_at=timezone.now() + timedelta(minutes=minutes_from_now),
    )


# TenantAwareTask switches the connection to the schema named in arg 0, so
# the tests hand it the schema they are already running in. Passing a made-up
# name sends the queries at a schema that does not exist in the test database.
def _run_reminders():
    return send_followup_reminders_for_tenant.apply(args=[connection.schema_name]).get()


def _run_chaser():
    return chase_overdue_followups_for_tenant.apply(args=[connection.schema_name]).get()


# ---- The reminder itself -------------------------------------------

def test_a_followup_due_shortly_is_announced(lead, agent):
    fu = _followup(lead, agent, minutes_from_now=3)

    _run_reminders()

    note = Notification.objects.get(followup_id_ref=fu.pk)
    assert note.kind == NotificationKind.FOLLOWUP_DUE
    assert note.recipient_id == agent.pk
    fu.refresh_from_db()
    assert fu.reminder_sent is True


def test_a_followup_hours_away_is_left_alone(lead, agent):
    """
    The forward window has to be small now that the dispatcher runs every few
    minutes. Announcing a 4pm call at 9am is not a reminder.
    """
    _followup(lead, agent, minutes_from_now=240)

    _run_reminders()

    assert Notification.objects.count() == 0


def test_one_that_came_due_while_nothing_was_running_is_caught(lead, agent):
    """The 24h lookback. Its moment passed unannounced; it still gets told."""
    fu = _followup(lead, agent, minutes_from_now=-90)

    _run_reminders()

    note = Notification.objects.get(followup_id_ref=fu.pk)
    assert note.kind == NotificationKind.FOLLOWUP_OVERDUE


def test_the_reminder_is_not_repeated(lead, agent):
    _followup(lead, agent, minutes_from_now=3)

    _run_reminders()
    _run_reminders()

    assert Notification.objects.count() == 1


# ---- The hourly chaser ---------------------------------------------

def test_an_overdue_followup_is_chased(lead, agent):
    fu = _followup(lead, agent, minutes_from_now=-180)
    fu.reminder_sent = True          # its one reminder already went out
    fu.save(update_fields=["reminder_sent"])

    result = _run_chaser()

    assert result["chased"] == 1
    note = Notification.objects.get(followup_id_ref=fu.pk)
    assert note.kind == NotificationKind.FOLLOWUP_OVERDUE


def test_it_is_chased_once_an_hour_not_every_run(lead, agent):
    """
    Beat fires hourly, but the task may also run late, twice, or by hand. The
    cadence has to come from what was already sent, not from the schedule.
    """
    _followup(lead, agent, minutes_from_now=-180)

    _run_chaser()
    _run_chaser()
    _run_chaser()

    assert Notification.objects.count() == 1


def test_an_hour_later_it_is_chased_again(lead, agent):
    fu = _followup(lead, agent, minutes_from_now=-180)

    _run_chaser()
    # Age the first chase past the hour.
    Notification.objects.filter(followup_id_ref=fu.pk).update(
        created_at=timezone.now() - timedelta(hours=1, minutes=5)
    )
    _run_chaser()

    assert Notification.objects.count() == 2


def test_a_completed_followup_stops_being_chased(lead, agent):
    fu = _followup(lead, agent, minutes_from_now=-180)
    fu.is_completed = True
    fu.save(update_fields=["is_completed"])

    assert _run_chaser()["chased"] == 0
    assert Notification.objects.count() == 0


def test_chasing_stops_after_three_days(lead, agent):
    """Past the cap it is noise, and the follow-up needs a person."""
    _followup(lead, agent, minutes_from_now=-(80 * 60))

    assert _run_chaser()["chased"] == 0


def test_followups_for_two_agents_each_reach_their_own(lead, agent):
    """Chasing must not cross-post someone else's overdue follow-up."""
    other = Agent.objects.create_agent(
        email="other@example.com", name="Other Agent", password="x",
    )
    mine = _followup(lead, agent, minutes_from_now=-120)
    theirs = _followup(lead, other, minutes_from_now=-120)

    _run_chaser()

    assert Notification.objects.get(followup_id_ref=mine.pk).recipient_id == agent.pk
    assert Notification.objects.get(followup_id_ref=theirs.pk).recipient_id == other.pk
