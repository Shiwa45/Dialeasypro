"""
Lead screen and batch updates asked for in Oct 2026:

  * filter the lead list by agent (or unassigned),
  * a Notes column — the lead's latest note or call note,
  * delete ticked leads in one go,
  * take a batch back from every agent so it can be assigned again,
  * per agent in Reports: leads assigned now, and how many never dialled.
"""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.calls.models import CallLog
from apps.leads import views as lv
from apps.leads.models import Lead, LeadBatch, LeadNote

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(email="adm@u.l", name="Adm", password="Pw@12345678")


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="asha@u.l", name="Asha", password="Pw@12345678")


@pytest.fixture
def bilal():
    return Agent.objects.create_agent(email="bilal@u.l", name="Bilal", password="Pw@12345678")


def call(view, method, user, data=None, path="/x/", **kw):
    factory = APIRequestFactory()
    req = factory.get(path, data or {}) if method == "get" else \
        getattr(factory, method)(path, data or {}, format="json")
    force_authenticate(req, user=user)
    req.has_feature = lambda k: True
    r = view.as_view()(req, **kw)
    r.render()
    return r


def lead(n, **kw):
    return Lead.objects.create(name=f"L{n}", phone=f"+91981230{n:04d}", **kw)


# ---- Agent filter -------------------------------------------------

def test_the_list_filters_by_agent_and_by_unassigned(admin, asha, bilal):
    lead(1, assigned_to=asha)
    lead(2, assigned_to=bilal)
    lead(3)
    r = call(lv.LeadListCreateView, "get", admin, {"assigned_to": asha.pk})
    assert [x["name"] for x in r.data["results"]] == ["L1"]
    r = call(lv.LeadListCreateView, "get", admin, {"assigned_to": "unassigned"})
    assert [x["name"] for x in r.data["results"]] == ["L3"]


# ---- Notes column -------------------------------------------------

def test_the_list_carries_the_latest_note(admin, asha):
    a = lead(1, assigned_to=asha)
    b = lead(2, assigned_to=asha)
    lead(3, assigned_to=asha)
    note = LeadNote.objects.create(lead=a, agent=asha, content="Wants a demo on Monday")
    LeadNote.objects.filter(pk=note.pk).update(created_at=timezone.now() - timedelta(hours=2))
    CallLog.objects.create(lead=a, agent=asha, phone_number=a.phone, notes="Asked for the price list",
                           started_at=timezone.now() - timedelta(minutes=5))
    CallLog.objects.create(lead=b, agent=asha, phone_number=b.phone, notes="",
                           started_at=timezone.now())
    LeadNote.objects.create(lead=b, agent=asha, content="Call after 6 pm")
    r = call(lv.LeadListCreateView, "get", admin)
    notes = {x["name"]: x["latest_note"] for x in r.data["results"]}
    assert notes == {"L1": "Asked for the price list", "L2": "Call after 6 pm", "L3": None}


# ---- Bulk delete ----------------------------------------------------

def test_ticked_leads_are_deleted_together(admin, asha):
    batch = LeadBatch._create_numbered(name="B")
    a, b, c = lead(1, batch=batch), lead(2, batch=batch), lead(3)
    r = call(lv.LeadBulkDeleteView, "post", admin, {"lead_ids": [a.pk, b.pk]})
    assert r.status_code == 200 and r.data["deleted"] == 2
    assert set(Lead.objects.filter(is_deleted=True).values_list("pk", flat=True)) == {a.pk, b.pk}
    assert not Lead.objects.get(pk=c.pk).is_deleted


def test_agents_cannot_bulk_delete(asha):
    a = lead(1, assigned_to=asha)
    r = call(lv.LeadBulkDeleteView, "post", asha, {"lead_ids": [a.pk]})
    assert r.status_code == 403
    assert not Lead.objects.get(pk=a.pk).is_deleted


def test_bulk_delete_needs_ids(admin):
    assert call(lv.LeadBulkDeleteView, "post", admin, {"lead_ids": []}).status_code == 400
    assert call(lv.LeadBulkDeleteView, "post", admin, {"lead_ids": ["x"]}).status_code == 400


# ---- Unassign a batch ----------------------------------------------

@pytest.fixture
def batch(asha, bilal):
    b = LeadBatch._create_numbered(name="Expo leads")
    lead(1, batch=b, assigned_to=asha, dial_attempts=2)
    lead(2, batch=b, assigned_to=asha)
    lead(3, batch=b, assigned_to=bilal)
    lead(4, batch=b)
    lead(5, assigned_to=asha)  # another batch's — untouched
    return b


def test_a_batch_is_taken_back_from_every_agent(admin, batch):
    r = call(lv.LeadBatchUnassignView, "post", admin, {}, pk=batch.pk)
    assert r.status_code == 200, r.data
    assert r.data["unassigned"] == 3
    assert r.data["per_agent"] == {"Asha": 2, "Bilal": 1}
    assert not Lead.objects.filter(batch=batch, assigned_to__isnull=False).exists()
    assert Lead.objects.get(name="L5").assigned_to is not None


def test_only_the_uncalled_leads_can_be_taken_back(admin, batch):
    r = call(lv.LeadBatchUnassignView, "post", admin, {"only_uncalled": True}, pk=batch.pk)
    assert r.data["unassigned"] == 2
    assert Lead.objects.get(name="L1").assigned_to is not None  # dialled: stays


def test_only_admins_unassign_a_batch(asha, batch):
    assert call(lv.LeadBatchUnassignView, "post", asha, {}, pk=batch.pk).status_code == 403


# ---- Reports -------------------------------------------------------

def test_reports_count_assigned_and_never_called(admin, asha):
    from apps.reports.views import AgentPerformanceReportView

    old = timezone.now() - timedelta(days=90)
    for n, dials in [(1, 0), (2, 0), (3, 4)]:
        lead(n, assigned_to=asha, dial_attempts=dials)
    Lead.objects.update(created_at=old, assigned_at=old)
    r = call(AgentPerformanceReportView, "get", admin, {"agent_id": asha.pk})
    [row] = r.data["agents"]
    assert row["leads"]["assigned"] == 3 and row["leads"]["not_called"] == 2


def test_bulk_delete_recounts_the_batch(admin):
    batch = LeadBatch._create_numbered(name="C", total_leads=2)
    a = lead(1, batch=batch)
    lead(2, batch=batch)
    call(lv.LeadBulkDeleteView, "post", admin, {"lead_ids": [a.pk]})
    batch.refresh_from_db()
    assert batch.total_leads == 1
