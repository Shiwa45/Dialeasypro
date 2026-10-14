"""
Calling queues: what an agent is served, and what an admin may configure.

Found by exercising the queues on the live site and in the API:

  * Skip released the lead straight back into the pool, so the next pull
    served the very same lead — skip could never move past it.
  * Pulling again while holding a lead (app restarted, queue re-opened)
    checked out a SECOND lead and left the first locked for the whole TTL.
  * The redial cooldown (24 h by default) also hid a lead whose follow-up
    was due — "Busy, call back in 1 h" waited a day in a follow-up queue.
  * A lead reassigned while checked out stayed locked by its old owner, so
    the new owner's queue skipped it.
  * Deleting or switching off a queue left its leads locked.
  * Any filter value was accepted: closed statuses (never served), unknown
    statuses/priorities/sources, a 0-minute lock (the lead could be served
    twice), a 100,000-hour cooldown, agents that don't exist or are
    read-only (who can't pull), and a second queue with the same name.
"""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.leads import views as lv
from apps.leads.models import CallQueue, CallQueueMembership, Lead

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(email="adm@q.l", name="Adm", password="Pw@12345678")


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="asha@q.l", name="Asha", password="Pw@12345678")


@pytest.fixture
def bilal():
    return Agent.objects.create_agent(email="bilal@q.l", name="Bilal", password="Pw@12345678")


def queue_for(*agents, **kw):
    q = CallQueue.objects.create(name=kw.pop("name", "Q"), **kw)
    for a in agents:
        CallQueueMembership.objects.create(queue=q, agent=a)
    return q


def leads(agent, n, **kw):
    out = []
    for i in range(n):
        out.append(Lead.objects.create(
            name=f"L{i}", phone=f"+9198{agent.pk:03d}{i:05d}", assigned_to=agent, **kw,
        ))
    # created_at ordering: the first created is served first ("priority"
    # order falls back to oldest).
    return out


def call(view, method, user, data=None, **kw):
    req = getattr(APIRequestFactory(), method)("/x/", data or {}, format="json")
    force_authenticate(req, user=user)
    req.has_feature = lambda k: True
    r = view.as_view()(req, **kw)
    r.render()
    return r


def pull(agent, q):
    return call(lv.QueuePullNextView, "post", agent, pk=q.pk)


def release(agent, lead, **data):
    return call(lv.QueueReleaseView, "post", agent, {"lead_id": lead.pk, **data})


# ============================================================
# Serving
# ============================================================

def test_skip_moves_on_to_the_next_lead(asha):
    first, second = leads(asha, 2)
    q = queue_for(asha)
    assert pull(asha, q).data["lead"]["id"] == first.pk
    release(asha, first)  # what the app sends on Skip
    assert pull(asha, q).data["lead"]["id"] == second.pk


def test_a_skipped_lead_comes_back_after_the_lock_time(asha):
    [only] = leads(asha, 1)
    q = queue_for(asha, lock_ttl_minutes=30)
    pull(asha, q)
    release(asha, only)
    assert pull(asha, q).data.get("empty") is True
    Lead.objects.filter(pk=only.pk).update(lock_expires_at=timezone.now() - timedelta(minutes=1))
    assert pull(asha, q).data["lead"]["id"] == only.pk


def test_leaving_the_queue_returns_the_lead_at_once(asha):
    [only] = leads(asha, 1)
    q = queue_for(asha)
    pull(asha, q)
    release(asha, only, return_to_queue=True)  # what the app sends on Stop
    assert pull(asha, q).data["lead"]["id"] == only.pk


def test_pulling_again_resumes_the_lead_already_held(asha):
    first, second = leads(asha, 2)
    q = queue_for(asha)
    assert pull(asha, q).data["lead"]["id"] == first.pk
    r = pull(asha, q)  # app restarted: the same lead, not a second one
    assert r.data["lead"]["id"] == first.pk and r.data["resumed"] is True
    assert Lead.objects.filter(locked_by=asha, lock_expires_at__gt=timezone.now()).count() == 1


def test_a_due_follow_up_is_served_inside_the_redial_cooldown(asha):
    [lead] = leads(asha, 1, status="follow_up")
    q = queue_for(asha, only_followup_due=True, redial_cooldown_hours=24)
    now = timezone.now()
    # Dialled 2 h ago ("Busy"), follow-up booked for 1 h after that: due now.
    Lead.objects.filter(pk=lead.pk).update(
        last_dialed_at=now - timedelta(hours=2), next_followup_at=now - timedelta(hours=1),
    )
    assert pull(asha, q).data["lead"]["id"] == lead.pk


def test_the_cooldown_still_holds_without_a_new_follow_up(asha):
    [lead] = leads(asha, 1, status="contacted")
    q = queue_for(asha, redial_cooldown_hours=24)
    now = timezone.now()
    # The follow-up was due BEFORE the last dial: that dial was the follow-up.
    Lead.objects.filter(pk=lead.pk).update(
        last_dialed_at=now - timedelta(hours=2), next_followup_at=now - timedelta(hours=3),
    )
    assert pull(asha, q).data.get("empty") is True


def test_a_reassigned_lead_is_served_to_its_new_owner(asha, bilal):
    [lead] = leads(asha, 1)
    qa, qb = queue_for(asha, name="A"), queue_for(bilal, name="B")
    pull(asha, qa)
    lead.refresh_from_db()
    lead.assign_to(bilal)
    assert pull(bilal, qb).data["lead"]["id"] == lead.pk


def test_deleting_a_queue_releases_its_leads(admin, asha):
    [lead] = leads(asha, 1)
    q = queue_for(asha)
    pull(asha, q)
    assert call(lv.CallQueueDetailView, "delete", admin, pk=q.pk).status_code == 204
    lead.refresh_from_db()
    assert lead.locked_by is None


def test_switching_a_queue_off_releases_its_leads(admin, asha):
    [lead] = leads(asha, 1)
    q = queue_for(asha)
    pull(asha, q)
    assert call(lv.CallQueueDetailView, "patch", admin, {"is_active": False}, pk=q.pk).status_code == 200
    lead.refresh_from_db()
    assert lead.locked_by is None


# ============================================================
# Configuration
# ============================================================

def _create(admin, **data):
    body = {"name": "QA", "agent_ids": [], **data}
    return call(lv.CallQueueListCreateView, "post", admin, body)


@pytest.mark.parametrize("bad", [
    {"filter_statuses": ["converted"]},
    {"filter_statuses": ["bogus"]},
    {"filter_priorities": ["urgent"]},
    {"filter_sources": ["other"]},
    {"filter_tags": [5]},
    {"lock_ttl_minutes": 0},
    {"lock_ttl_minutes": 100000},
    {"redial_cooldown_hours": 100000},
])
def test_impossible_settings_are_refused(admin, asha, bad):
    r = _create(admin, agent_ids=[asha.pk], **bad)
    assert r.status_code == 400, (bad, r.data)


def test_agents_must_exist_be_active_and_able_to_dial(admin, asha):
    assert _create(admin, agent_ids=[]).status_code == 400
    assert _create(admin, agent_ids=[999]).status_code == 400
    gone = Agent.objects.create_agent(email="gone@q.l", name="Gone", password="Pw@12345678", is_active=False)
    assert _create(admin, agent_ids=[gone.pk]).status_code == 400
    viewer = Agent.objects.create_agent(email="ro@q.l", name="RO", password="Pw@12345678", role="readonly")
    assert _create(admin, agent_ids=[viewer.pk]).status_code == 400


def test_queue_names_are_unique(admin, asha):
    assert _create(admin, name="New leads", agent_ids=[asha.pk]).status_code == 201
    assert _create(admin, name=" new LEADS ", agent_ids=[asha.pk]).status_code == 400


def test_a_valid_queue_is_saved_and_reports_its_load(admin, asha):
    leads(asha, 3)
    r = _create(admin, agent_ids=[asha.pk], filter_statuses=["new"], filter_sources=["manual"],
                filter_tags=["vip"], lock_ttl_minutes=30)
    assert r.status_code == 201, r.data
    r = call(lv.CallQueueListCreateView, "get", admin)
    [q] = r.data
    assert q["waiting"] == 0  # no lead has the "vip" tag
    r = call(lv.CallQueueDetailView, "patch", admin, {"filter_tags": []}, pk=q["id"])
    assert r.data["waiting"] == 3 and r.data["checked_out"] == 0


def test_existing_queues_are_cleaned_by_the_migration(asha):
    from importlib import import_module

    from django.apps import apps as django_apps

    q = queue_for(asha, filter_statuses=["new", "converted", "bogus"], filter_sources=["manual", "other"],
                  filter_priorities=["urgent", "hot"], filter_tags=[5, " vip "], lock_ttl_minutes=0)
    import_module("apps.leads.migrations.0011_clean_queue_filters").clean(django_apps, None)
    q.refresh_from_db()
    assert q.filter_statuses == ["new"] and q.filter_sources == ["manual"]
    assert q.filter_priorities == ["hot"] and q.filter_tags == ["vip"] and q.lock_ttl_minutes == 30  # back to the default
