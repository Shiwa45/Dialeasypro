"""
An agent is told about their own follow-ups — and nobody else's.

Ownership used to be decided differently in each place: a follow-up belonged
to whoever created it, the call-outcome auto follow-up to whoever made the
call, and reassigning a lead left its follow-ups with the previous agent. So
team leads got reminders meant for their agents, agents got reminders for
leads they had lost, the new agent got nothing, and every auto follow-up rang
twice. See apps/leads/followup_rules.py.
"""
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent, Notification, NotificationKind
from apps.calls.models import CallDisposition, CallLog
from apps.core.constants import AgentRole
from apps.leads.models import FollowUp, Lead
from apps.leads.services.distribution import distribute
from apps.leads.tasks import chase_overdue_followups_for_tenant, send_followup_reminders_for_tenant
from apps.leads.views import FollowUpListCreateView, LeadBulkAssignView, LeadDetailView, MyFollowUpsView

pytestmark = pytest.mark.django_db
factory = APIRequestFactory()


def _agent(email, role=AgentRole.AGENT, **extra):
    return Agent.objects.create_agent(email=email, name=email.split("@")[0].title(), password="Pw@12345678",
                                      role=role, **extra)


@pytest.fixture
def asha():
    return _agent("asha@example.com")


@pytest.fixture
def bilal():
    return _agent("bilal@example.com")


@pytest.fixture
def lead_tl():
    return _agent("tl@example.com", role=AgentRole.SENIOR_AGENT)


@pytest.fixture
def manager():
    return _agent("mona@example.com", role=AgentRole.MANAGER)


@pytest.fixture
def lead(asha):
    return Lead.objects.create(name="Ravi Kumar", phone="+919812345678", assigned_to=asha)


def _schedule(user, lead, **extra):
    data = {"followup_type": "call", "scheduled_at": (timezone.now() + timedelta(hours=2)).isoformat(), **extra}
    request = factory.post(f"/api/v1/leads/{lead.pk}/followups/", data, format="json")
    force_authenticate(request, user=user)
    response = FollowUpListCreateView.as_view()(request, lead_id=lead.pk)
    response.render()
    return response


def _followup(lead, agent, *, minutes_from_now, **extra):
    return FollowUp.objects.create(
        lead=lead, assigned_to=agent, followup_type="call",
        scheduled_at=timezone.now() + timedelta(minutes=minutes_from_now), **extra,
    )


def _reminders():
    return send_followup_reminders_for_tenant.apply(args=[connection.schema_name]).get()


def _chase():
    return chase_overdue_followups_for_tenant.apply(args=[connection.schema_name]).get()


def _told(agent, kind=None):
    qs = Notification.objects.filter(recipient=agent)
    return qs.filter(kind=kind) if kind else qs


def _mine(user):
    request = factory.get("/api/v1/leads/followups/mine/")
    force_authenticate(request, user=user)
    response = MyFollowUpsView.as_view()(request)
    response.render()
    return [row["id"] for row in response.data]


# ---- Who a new follow-up belongs to --------------------------------------

def test_a_follow_up_scheduled_by_the_team_lead_belongs_to_the_agent(lead, asha, manager):
    r = _schedule(manager, lead)

    assert r.status_code == 201, r.data
    fu = FollowUp.objects.get()
    assert fu.assigned_to == asha
    assert _told(asha, NotificationKind.FOLLOWUP_SCHEDULED).count() == 1
    assert not _told(manager).exists()


def test_asking_for_someone_other_than_the_lead_agent_is_refused(lead, manager, bilal):
    r = _schedule(manager, lead, assigned_to=bilal.pk)

    assert r.status_code == 400
    assert not FollowUp.objects.exists()


def test_an_agent_cannot_hand_a_follow_up_to_a_colleague(asha, bilal):
    unassigned = Lead.objects.create(name="Open", phone="+919812345600")
    # Agents only see their own leads, so give Asha a lead she can see first.
    unassigned.assigned_to = None
    unassigned.save()
    r = _schedule(_agent("admin@example.com", role=AgentRole.ADMIN), unassigned, assigned_to=bilal.pk)
    assert r.status_code == 201
    assert FollowUp.objects.get().assigned_to == bilal

    inactive = _agent("gone@example.com", is_active=False)
    r = _schedule(_agent("admin2@example.com", role=AgentRole.ADMIN), unassigned, assigned_to=inactive.pk)
    assert r.status_code == 400


# ---- Reassigning a lead moves its open follow-ups -----------------------

def test_bulk_assign_moves_open_follow_ups_to_the_new_agent(lead, asha, bilal, manager):
    open_fu = _followup(lead, asha, minutes_from_now=120, reminder_sent=True)
    done_fu = _followup(lead, asha, minutes_from_now=-60, is_completed=True)
    stale = Notification.objects.create(recipient=asha, kind=NotificationKind.FOLLOWUP_DUE,
                                        title="Follow up with Ravi", followup_id_ref=open_fu.pk)

    request = factory.post("/api/v1/leads/bulk-assign/", {"lead_ids": [lead.pk], "assigned_to": bilal.pk},
                           format="json")
    force_authenticate(request, user=manager)
    assert LeadBulkAssignView.as_view()(request).status_code == 200

    open_fu.refresh_from_db()
    done_fu.refresh_from_db()
    stale.refresh_from_db()
    assert open_fu.assigned_to == bilal
    assert open_fu.reminder_sent is False, "the new agent's reminder is armed again"
    assert done_fu.assigned_to == asha, "history is not rewritten"
    assert stale.is_read, "Asha's bell no longer points at a lead she cannot open"


def test_editing_the_lead_agent_moves_its_follow_ups(lead, asha, bilal, manager):
    fu = _followup(lead, asha, minutes_from_now=120)

    request = factory.patch(f"/api/v1/leads/{lead.pk}/", {"assigned_to": bilal.pk}, format="json")
    force_authenticate(request, user=manager)
    r = LeadDetailView.as_view()(request, pk=lead.pk)

    assert r.status_code == 200, getattr(r, "data", r)
    fu.refresh_from_db()
    assert fu.assigned_to == bilal


def test_distribution_moves_follow_ups_with_the_leads(asha, bilal):
    lead = Lead.objects.create(name="Unassigned", phone="+919812345601")
    fu = _followup(lead, asha, minutes_from_now=120)

    distribute([lead.pk], [bilal])

    fu.refresh_from_db()
    assert fu.assigned_to == bilal


# ---- Who is told -------------------------------------------------------

def test_reminders_go_only_to_the_agent_who_owns_the_lead(lead, asha, bilal):
    mine = _followup(lead, asha, minutes_from_now=3)
    # A follow-up still pointing at Bilal although the lead is Asha's — what a
    # reassignment left behind before follow_lead_owner existed.
    stale = _followup(lead, bilal, minutes_from_now=3)
    deleted_lead = Lead.objects.create(name="Gone", phone="+919812345602", assigned_to=asha, is_deleted=True)
    _followup(deleted_lead, asha, minutes_from_now=3)

    _reminders()

    assert list(_told(asha).values_list("followup_id_ref", flat=True)) == [mine.pk]
    assert not _told(bilal).exists()
    stale.refresh_from_db()
    assert stale.reminder_sent is False


def test_a_deactivated_agent_is_not_reminded(lead, asha):
    _followup(lead, asha, minutes_from_now=3)
    Agent.objects.filter(pk=asha.pk).update(is_active=False)

    _reminders()

    assert not Notification.objects.exists()


def test_the_overdue_chase_follows_the_same_rule(lead, asha, bilal):
    _followup(lead, asha, minutes_from_now=-90)
    _followup(lead, bilal, minutes_from_now=-90)

    _chase()

    assert _told(asha, NotificationKind.FOLLOWUP_OVERDUE).count() == 1
    assert not _told(bilal).exists()


def test_the_phone_list_only_has_the_agent_own_live_follow_ups(lead, asha, bilal):
    mine = _followup(lead, asha, minutes_from_now=60)
    _followup(lead, bilal, minutes_from_now=60)  # stale: the lead is Asha's

    assert _mine(asha) == [mine.pk]
    assert _mine(bilal) == []


def test_managers_keep_reminders_for_unassigned_leads_they_scheduled(manager):
    open_lead = Lead.objects.create(name="Open", phone="+919812345603")
    fu = _followup(open_lead, manager, minutes_from_now=3)

    _reminders()

    assert list(_told(manager).values_list("followup_id_ref", flat=True)) == [fu.pk]


# ---- Auto follow-ups and completion -------------------------------------

def test_the_call_outcome_auto_follow_up_goes_to_the_lead_agent(lead, asha, lead_tl):
    callback = CallDisposition.objects.create(name="Call back", slug="call-back-x", auto_followup_hours=24)

    CallLog.objects.create(agent=lead_tl, lead=lead, phone_number=lead.phone, disposition=callback)

    fu = FollowUp.objects.get()
    assert fu.assigned_to == asha
    assert fu.is_auto is True


def test_a_follow_up_scheduled_by_hand_replaces_the_auto_one(lead, asha):
    auto = _followup(lead, asha, minutes_from_now=24 * 60, is_auto=True)
    Notification.objects.create(recipient=asha, kind=NotificationKind.FOLLOWUP_DUE, title="x", followup_id_ref=auto.pk)

    r = _schedule(asha, lead)

    assert r.status_code == 201
    auto.refresh_from_db()
    assert auto.is_completed, "only one follow-up is left to ring"
    assert FollowUp.objects.filter(is_completed=False).count() == 1
    assert not _told(asha).filter(is_read=False).exists()


def test_completing_a_follow_up_clears_its_reminders_from_the_bell(lead, asha):
    fu = _followup(lead, asha, minutes_from_now=-90)
    _chase()
    assert _told(asha).filter(is_read=False).count() == 1

    fu.complete(agent=asha)

    assert not _told(asha).filter(is_read=False).exists()
