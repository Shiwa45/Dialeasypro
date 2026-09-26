"""
An overdue follow-up stays overdue until someone completes it.

Lead.next_followup_at drives the Overdue filter, the overdue badge and the
dashboard's overdue count. Three places recomputed it from FUTURE follow-ups
only, so a lead with yesterday's follow-up still pending dropped out of the
Overdue list when:

  * another follow-up was scheduled on it (the save signal);
  * a later follow-up was completed early (FollowUp.complete);
  * its own overdue reminder was sent — the 5-minute task marks
    reminder_sent, which fires the same signal. This one ran on its own.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.authentication.models import Agent
from apps.leads.models import FollowUp, Lead
from apps.leads.views import leads_visible_to

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent():
    return Agent.objects.create_tenant_admin(
        email="owner@example.com", name="Owner", password="Pw@12345678",
    )


@pytest.fixture
def lead(agent):
    return Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=agent)


def _followup(lead, agent, when):
    return FollowUp.objects.create(
        lead=lead, assigned_to=agent, scheduled_at=when, followup_type="call",
    )


def _is_overdue(lead):
    lead.refresh_from_db()
    return (
        leads_visible_to(lead.assigned_to)
        .filter(pk=lead.pk, next_followup_at__lt=timezone.now())
        .exists()
    )


def test_an_overdue_follow_up_makes_the_lead_overdue(agent, lead):
    _followup(lead, agent, timezone.now() - timedelta(days=1))

    assert _is_overdue(lead)


def test_scheduling_another_follow_up_keeps_it_overdue(agent, lead):
    _followup(lead, agent, timezone.now() - timedelta(days=1))

    _followup(lead, agent, timezone.now() + timedelta(days=3))

    assert _is_overdue(lead), "yesterday's follow-up is still owed"


def test_completing_a_later_follow_up_early_keeps_it_overdue(agent, lead):
    _followup(lead, agent, timezone.now() - timedelta(days=1))
    later = _followup(lead, agent, timezone.now() + timedelta(days=1))

    later.complete(notes="Rang early")

    assert _is_overdue(lead)


def test_sending_the_overdue_reminder_keeps_it_overdue(agent, lead):
    """The reminder task marks reminder_sent; that save used to clear it."""
    overdue = _followup(lead, agent, timezone.now() - timedelta(hours=2))

    overdue.reminder_sent = True
    overdue.reminder_sent_at = timezone.now()
    overdue.save(update_fields=["reminder_sent", "reminder_sent_at"])

    assert _is_overdue(lead)


def test_a_back_dated_follow_up_is_overdue_immediately(agent, lead):
    _followup(lead, agent, timezone.now() - timedelta(hours=5))

    assert _is_overdue(lead)


def test_completing_the_overdue_one_clears_it(agent, lead):
    overdue = _followup(lead, agent, timezone.now() - timedelta(days=1))
    later = _followup(lead, agent, timezone.now() + timedelta(days=2))

    overdue.complete(notes="Done")

    lead.refresh_from_db()
    assert not _is_overdue(lead)
    assert lead.next_followup_at == later.scheduled_at


def test_completing_everything_leaves_nothing_next(agent, lead):
    only = _followup(lead, agent, timezone.now() - timedelta(days=1))

    only.complete(notes="Done")

    lead.refresh_from_db()
    assert lead.next_followup_at is None


def test_deleting_a_follow_up_resyncs(agent, lead):
    overdue = _followup(lead, agent, timezone.now() - timedelta(days=1))
    later = _followup(lead, agent, timezone.now() + timedelta(days=2))

    overdue.delete()

    lead.refresh_from_db()
    assert lead.next_followup_at == later.scheduled_at
