"""
Tests for lead batches and the distribution engine.

The distribution algorithms are pure functions over (lead_ids, agents), so the
interesting half of this file needs no database at all — which is why they were
pulled out of the view in the first place.
"""
from datetime import date, timedelta

import pytest

from apps.leads.services.distribution import Method, plan


class FakeAgent:
    """Stands in for an Agent — `plan` only ever reads .pk and .name."""

    def __init__(self, pk, name):
        self.pk = pk
        self.name = name


A, B, C = FakeAgent(1, "Asha"), FakeAgent(2, "Bala"), FakeAgent(3, "Chetan")


# ============================================================
# Planning — no DB needed
# ============================================================

@pytest.mark.parametrize("method", [Method.ROUND_ROBIN, Method.EQUAL_SPLIT])
def test_every_lead_is_placed_exactly_once(method):
    ids = list(range(1, 101))
    buckets, leftover = plan(ids, [A, B, C], method=method)
    placed = [i for ids_ in buckets.values() for i in ids_]
    assert sorted(placed) == ids
    assert len(placed) == len(set(placed)), "a lead was handed to two agents"
    assert leftover == []


def test_round_robin_interleaves():
    buckets, _ = plan([1, 2, 3, 4, 5, 6, 7], [A, B, C], method=Method.ROUND_ROBIN)
    assert buckets[A.pk] == [1, 4, 7]
    assert buckets[B.pk] == [2, 5]
    assert buckets[C.pk] == [3, 6]


def test_equal_split_gives_contiguous_blocks():
    buckets, _ = plan([1, 2, 3, 4, 5, 6, 7], [A, B, C], method=Method.EQUAL_SPLIT)
    # 7 across 3 → 3/2/2, remainder goes to the earliest agents.
    assert buckets[A.pk] == [1, 2, 3]
    assert buckets[B.pk] == [4, 5]
    assert buckets[C.pk] == [6, 7]


def test_fewer_leads_than_agents():
    buckets, leftover = plan([1, 2], [A, B, C], method=Method.ROUND_ROBIN)
    assert buckets[A.pk] == [1]
    assert buckets[B.pk] == [2]
    assert C.pk not in buckets or buckets[C.pk] == []
    assert leftover == []


def test_no_agents_leaves_everything_over():
    buckets, leftover = plan([1, 2, 3], [], method=Method.ROUND_ROBIN)
    assert buckets == {}
    assert leftover == [1, 2, 3]


def test_no_leads_is_a_no_op():
    buckets, leftover = plan([], [A, B], method=Method.ROUND_ROBIN)
    assert not buckets
    assert leftover == []


def test_plan_is_deterministic():
    """Re-planning the same input must give the same answer, or a preview lies."""
    first = plan(list(range(50)), [A, B, C], method=Method.ROUND_ROBIN)[0]
    second = plan(list(range(50)), [A, B, C], method=Method.ROUND_ROBIN)[0]
    assert dict(first) == dict(second)


# ============================================================
# Capacity cap — needs the DB (reads each agent's open load)
# ============================================================

@pytest.fixture
def agents(db):
    from apps.authentication.models import Agent

    return [
        Agent.objects.create_agent(email=f"a{i}@x.test", name=f"Agent {i}", password="x")
        for i in range(1, 4)
    ]


@pytest.mark.django_db
def test_cap_skips_full_agents_and_reports_leftovers(agents):
    from apps.leads.models import Lead

    a1, a2, a3 = agents
    # a1 already has 5 open leads; the cap is 5, so a1 must be skipped entirely.
    for i in range(5):
        Lead.objects.create(name=f"Existing {i}", phone=f"+9199999000{i:02d}", assigned_to=a1)

    buckets, leftover = plan([101, 102, 103, 104], agents, method=Method.ROUND_ROBIN,
                             max_per_agent=5)
    assert a1.pk not in buckets or buckets[a1.pk] == []
    assert sum(len(v) for v in buckets.values()) == 4
    assert leftover == []


@pytest.mark.django_db
def test_cap_counts_existing_load_not_just_this_run(agents):
    from apps.leads.models import Lead

    a1, a2, a3 = agents
    # Everyone is already at 2 open leads, cap is 3 → one slot each, 3 total.
    for agent in agents:
        for i in range(2):
            Lead.objects.create(
                name=f"E{agent.pk}{i}", phone=f"+9198{agent.pk}{i}0000{i}", assigned_to=agent,
            )

    buckets, leftover = plan(list(range(200, 210)), agents, method=Method.ROUND_ROBIN,
                             max_per_agent=3)
    assert sum(len(v) for v in buckets.values()) == 3
    assert len(leftover) == 7, "leads over the cap must be reported, not force-assigned"


@pytest.mark.django_db
def test_closed_leads_do_not_count_toward_load(agents):
    """
    A won or lost lead is finished work. Counting it would mean the agent who
    closes the most deals stops receiving new ones.
    """
    from apps.core.constants import LeadStatus
    from apps.leads.models import Lead
    from apps.leads.services.distribution import current_open_counts

    a1 = agents[0]
    Lead.objects.create(name="Won", phone="+919812300001",
                        assigned_to=a1, status=LeadStatus.CONVERTED)
    Lead.objects.create(name="Lost", phone="+919812300002",
                        assigned_to=a1, status=LeadStatus.LOST)
    Lead.objects.create(name="NotInt", phone="+919812300003",
                        assigned_to=a1, status=LeadStatus.NOT_INTERESTED)
    Lead.objects.create(name="Open", phone="+919812300004",
                        assigned_to=a1, status=LeadStatus.NEW)

    assert current_open_counts(agents)[a1.pk] == 1


@pytest.mark.django_db
def test_least_loaded_favours_the_lightest_pipeline(agents):
    from apps.leads.models import Lead

    a1, a2, a3 = agents
    # a1 has 4 open, a2 has 1, a3 has 0.
    for i in range(4):
        Lead.objects.create(name=f"L{i}", phone=f"+9197000000{i:02d}", assigned_to=a1)
    Lead.objects.create(name="M", phone="+919700000099", assigned_to=a2)

    buckets, _ = plan([1, 2, 3], agents, method=Method.LEAST_LOADED)
    # a3 (0) first, then a2 (1), then a3 again (now level with a2 at 1 → lower pk wins).
    assert buckets[a3.pk][0] == 1
    assert buckets[a2.pk][0] == 2
    assert sum(len(v) for v in buckets.values()) == 3
    # The heaviest agent must not receive any of three leads.
    assert a1.pk not in buckets or buckets[a1.pk] == []


# ============================================================
# Batch model
# ============================================================

@pytest.mark.django_db
def test_batch_numbers_are_monotonic_and_never_reused(db):
    """
    Deleting a batch must NOT free its number for the next one.

    An admin who noted "distribute batch 2" would otherwise end up pointing at
    a completely different consignment, and the unique constraint cannot catch
    it because the original row is gone. max(number)+1 had exactly this hole.
    """
    from apps.leads.models import LeadBatch

    first = LeadBatch.create_for_import(import_job=None, name="First")
    second = LeadBatch.create_for_import(import_job=None, name="Second")
    assert second.number > first.number

    doomed_number = second.number
    second.delete()

    third = LeadBatch.create_for_import(import_job=None, name="Third")
    assert third.number > doomed_number, "a deleted batch number was handed out again"
    assert third.number == third.pk


def test_batch_numbers_are_unique_across_many_creates(db):
    from apps.leads.models import LeadBatch

    made = [LeadBatch.create_for_import(import_job=None) for _ in range(25)]
    numbers = [b.number for b in made]
    assert None not in numbers, "a batch was left without a number"
    assert len(set(numbers)) == len(numbers)
    assert numbers == sorted(numbers)


@pytest.mark.django_db
def test_webhook_batch_is_reused_within_a_day(db):
    from apps.core.constants import LeadSource
    from apps.leads.models import LeadBatch

    one = LeadBatch.open_for_source(LeadSource.META_FACEBOOK)
    two = LeadBatch.open_for_source(LeadSource.META_FACEBOOK)
    assert one.pk == two.pk, "a second lead the same day must join the same batch"

    yesterday = date.today() - timedelta(days=1)
    old = LeadBatch.open_for_source(LeadSource.META_FACEBOOK, on_date=yesterday)
    assert old.pk != one.pk


@pytest.mark.django_db
def test_webhook_batches_are_per_source(db):
    from apps.core.constants import LeadSource
    from apps.leads.models import LeadBatch

    meta = LeadBatch.open_for_source(LeadSource.META_FACEBOOK)
    indiamart = LeadBatch.open_for_source(LeadSource.INDIAMART)
    assert meta.pk != indiamart.pk


@pytest.mark.django_db
def test_label_falls_back_when_unnamed(db):
    from apps.core.constants import LeadSource
    from apps.leads.models import LeadBatch

    unnamed = LeadBatch.create_for_import(import_job=None)
    assert unnamed.label == f"Batch {unnamed.number}"

    named = LeadBatch.create_for_import(import_job=None, name="Diwali campaign")
    assert named.label == "Diwali campaign"

    auto = LeadBatch.open_for_source(LeadSource.INDIAMART)
    assert "IndiaMART" in auto.label


@pytest.mark.django_db
def test_recount_repairs_a_drifted_counter(db):
    from apps.leads.models import Lead, LeadBatch

    batch = LeadBatch.create_for_import(import_job=None, name="Drifted")
    for i in range(3):
        Lead.objects.create(name=f"L{i}", phone=f"+9196000000{i:02d}", batch=batch)

    batch.total_leads = 99  # pretend the denormalised counter drifted
    batch.save(update_fields=["total_leads"])
    assert batch.recount() == 3


@pytest.mark.django_db
def test_deleting_a_batch_keeps_its_leads(db, client):
    """A consignment record is not the people in it."""
    from apps.leads.models import Lead, LeadBatch

    batch = LeadBatch.create_for_import(import_job=None, name="Doomed")
    lead = Lead.objects.create(name="Survivor", phone="+919950000001", batch=batch)

    # Mirrors LeadBatchDetailView.perform_destroy.
    batch.leads.update(batch=None)
    batch.delete()

    lead.refresh_from_db()
    assert lead.pk is not None
    assert lead.batch_id is None
