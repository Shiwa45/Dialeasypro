"""
TeleCRM Backend — apps/leads/services/distribution.py

Lead distribution: split a set of leads across a set of agents.

One module, used by three callers — the CSV import task (auto-assign on
import), the manual "Distribute" action, and any future scheduled rebalance.
Before this existed the round-robin lived inline in LeadDistributeView, so
the import path could not reuse it and grew its own copy.

Every method is deterministic given the same inputs and agent order, which is
what makes the unit tests meaningful and what stops "distribute" producing a
different split each time an admin previews it.
"""
import logging
from collections import defaultdict

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

logger = logging.getLogger(__name__)


class Method:
    """How leads are split across agents."""

    ROUND_ROBIN = "round_robin"
    EQUAL_SPLIT = "equal_split"
    LEAST_LOADED = "least_loaded"

    CHOICES = [
        (ROUND_ROBIN, "Round robin — one at a time, in order"),
        (EQUAL_SPLIT, "Equal split — contiguous blocks per agent"),
        (LEAST_LOADED, "Least loaded — agents with fewest open leads get more"),
    ]
    ALL = [ROUND_ROBIN, EQUAL_SPLIT, LEAST_LOADED]


# Statuses that still count as "on an agent's plate" for LEAST_LOADED.
#
# Finished work must not make an agent look busy forever, or the person who
# closes the most deals stops receiving any new ones. That rules out converted
# and lost — and also NOT_INTERESTED, which needs no further action: counting
# it would punish exactly the agents who keep their pipeline honest.
from apps.core.constants import LeadStatus  # noqa: E402

CLOSED_STATUSES = (
    LeadStatus.CONVERTED,
    LeadStatus.LOST,
    LeadStatus.DUPLICATE,
    LeadStatus.NOT_INTERESTED,
)

OPEN_STATUSES = [s for s, _ in LeadStatus.CHOICES if s not in CLOSED_STATUSES]


def current_open_counts(agents) -> dict[int, int]:
    """
    Open leads per agent, for the agents given. One query, not one per agent.

    Agents with no open leads are absent from the aggregate, so they are
    seeded to zero — otherwise `.get(pk)` returns None and the sort explodes
    on exactly the agents who should be first in line for new work.
    """
    from apps.leads.models import Lead

    counts = {a.pk: 0 for a in agents}
    rows = (
        Lead.objects.filter(
            is_deleted=False,
            assigned_to__in=agents,
            status__in=OPEN_STATUSES,
        )
        .values("assigned_to")
        .annotate(n=Count("id"))
    )
    for row in rows:
        counts[row["assigned_to"]] = row["n"]
    return counts


def plan(lead_ids: list[int], agents: list, *, method: str = Method.ROUND_ROBIN,
         max_per_agent: int | None = None) -> tuple[dict[int, list[int]], list[int]]:
    """
    Work out who gets what. Pure computation — touches no rows.

    Returns (buckets, leftover) where `buckets` maps agent pk → lead ids and
    `leftover` is the leads nobody could take because every agent hit
    `max_per_agent`. Returning leftovers rather than silently dropping or
    force-assigning them is the whole point of having a cap: the caller tells
    the admin "40 of 200 could not be placed", and those leads stay unassigned
    and visible rather than quietly landing on an overloaded agent.

    `max_per_agent` is a ceiling on an agent's TOTAL open leads, not on how
    many this run may add — a cap that ignored existing load would let a
    repeated distribute pile up without limit.
    """
    buckets: dict[int, list[int]] = defaultdict(list)
    if not lead_ids or not agents:
        return buckets, list(lead_ids)

    # Remaining headroom per agent. None = unlimited.
    if max_per_agent is None:
        headroom = {a.pk: None for a in agents}
    else:
        existing = current_open_counts(agents)
        headroom = {a.pk: max(0, max_per_agent - existing.get(a.pk, 0)) for a in agents}

    def can_take(pk: int) -> bool:
        room = headroom[pk]
        return room is None or room > len(buckets[pk])

    leftover: list[int] = []

    if method == Method.LEAST_LOADED:
        # Fewest open leads first, then round-robin from there. Ties break on
        # agent pk so the result is stable across runs.
        existing = current_open_counts(agents)
        ordered = sorted(agents, key=lambda a: (existing.get(a.pk, 0), a.pk))
        # Track a live count so the agent who just received one drops down the
        # order — otherwise the least-loaded agent takes every single lead.
        live = {a.pk: existing.get(a.pk, 0) for a in agents}
        for lead_id in lead_ids:
            candidates = [a for a in ordered if can_take(a.pk)]
            if not candidates:
                leftover.append(lead_id)
                continue
            target = min(candidates, key=lambda a: (live[a.pk], a.pk))
            buckets[target.pk].append(lead_id)
            live[target.pk] += 1
        return buckets, leftover

    if method == Method.EQUAL_SPLIT:
        # Contiguous blocks. Useful when the file is ordered by something the
        # admin cares about (city, campaign) and they want each agent working
        # a coherent slice rather than an interleaved one.
        n = len(agents)
        base, extra = divmod(len(lead_ids), n)
        cursor = 0
        for i, agent in enumerate(agents):
            size = base + (1 if i < extra else 0)
            block = lead_ids[cursor:cursor + size]
            cursor += size
            room = headroom[agent.pk]
            if room is None:
                buckets[agent.pk].extend(block)
            else:
                buckets[agent.pk].extend(block[:room])
                leftover.extend(block[room:])
        return buckets, leftover

    # ROUND_ROBIN (default). Skips agents who are full rather than stalling on
    # them, so one capped agent does not block the whole rotation.
    i = 0
    for lead_id in lead_ids:
        placed = False
        for _ in range(len(agents)):
            agent = agents[i % len(agents)]
            i += 1
            if can_take(agent.pk):
                buckets[agent.pk].append(lead_id)
                placed = True
                break
        if not placed:
            leftover.append(lead_id)
    return buckets, leftover


@transaction.atomic
def apply(buckets: dict[int, list[int]], *, actor=None) -> dict[int, int]:
    """
    Write a plan to the database. Returns agent pk → number assigned.

    Chunked because the IN clause on a 20,000-lead batch is not something to
    hand Postgres in one go, and atomic because a half-applied distribution
    leaves an admin unable to tell what actually happened.
    """
    from apps.leads.models import Lead

    now = timezone.now()
    applied: dict[int, int] = {}
    for agent_pk, ids in buckets.items():
        if not ids:
            continue
        for start in range(0, len(ids), 1000):
            Lead.objects.filter(pk__in=ids[start:start + 1000]).update(
                assigned_to_id=agent_pk, assigned_at=now,
            )
        applied[agent_pk] = len(ids)
    return applied


def distribute(lead_ids: list[int], agents: list, *, method: str = Method.ROUND_ROBIN,
               max_per_agent: int | None = None, actor=None) -> dict:
    """
    Plan and apply in one call, with a result shaped for the API response.

    `per_agent` is keyed by agent NAME for display, but `per_agent_id` carries
    the pks — a UI that only gets names cannot link anywhere, and two agents
    can share a name.
    """
    buckets, leftover = plan(lead_ids, agents, method=method, max_per_agent=max_per_agent)
    applied = apply(buckets, actor=actor)

    by_pk = {a.pk: a for a in agents}
    result = {
        "distributed": sum(applied.values()),
        "unassigned": len(leftover),
        "method": method,
        "per_agent": {by_pk[pk].name: n for pk, n in applied.items() if pk in by_pk},
        "per_agent_id": {pk: n for pk, n in applied.items()},
    }
    if leftover:
        result["message"] = (
            f"{len(leftover)} lead(s) stayed unassigned — every selected agent is at "
            f"the {max_per_agent}-lead cap. Raise the cap or add agents."
        )
    logger.info(
        "[Distribute] %s: %s assigned across %s agent(s), %s left over",
        method, result["distributed"], len(applied), len(leftover),
    )
    return result


def leads_for_batches(batch_ids, *, only_unassigned: bool = True, limit: int | None = None):
    """
    The lead ids in a set of batches, oldest first.

    Ordering by created_at (not pk) so an equal-split gives each agent a
    time-coherent slice, and so re-running a distribution on the same batch
    produces the same plan.
    """
    from apps.leads.models import Lead

    qs = Lead.objects.filter(is_deleted=False, batch_id__in=batch_ids)
    if only_unassigned:
        qs = qs.filter(assigned_to__isnull=True)
    qs = qs.order_by("created_at", "id")
    if limit:
        qs = qs[:limit]
    return list(qs.values_list("id", flat=True))
