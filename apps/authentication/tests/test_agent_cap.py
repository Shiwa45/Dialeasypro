"""
The cap on how many agents a tenant may have.

Seats were capped by the PLAN alone, so the only way to give one customer a
few more agents was to move them to a bigger plan or edit the plan every other
tenant shares. `Tenant.max_agents_override` is the per-customer number, set
from the super admin panel, and it wins over the plan when present.

The enforcement it replaced wrapped the whole check in `except Exception:
pass — if we can't check, allow creation`, so anything unexpected handed out a
free seat silently. The cap is now resolved in one place
(apps/core/quotas.agent_limit) that both the create and reactivate paths call.
"""
import pytest
from django.db import connection
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.authentication.views import AgentListAPIView, AgentReactivateAPIView
from apps.core.constants import SubscriptionStatus
from apps.core.quotas import agent_limit
from apps.plans.models import Plan, Subscription
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    """The test tenant, with any override from a previous test cleared."""
    t = Tenant.objects.get(schema_name=connection.schema_name)
    t.max_agents_override = None
    t.plan = None
    t.save(update_fields=["max_agents_override", "plan"])
    return t


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(
        email="owner@example.com", name="Owner", password="Pw@12345678",
    )


def _plan(tenant, *, max_agents, slug="cap-test"):
    """An active subscription to a plan allowing `max_agents` seats."""
    plan, _ = Plan.objects.get_or_create(
        slug=slug,
        defaults={"name": "Cap Test", "price_monthly": 999, "max_agents": max_agents},
    )
    if plan.max_agents != max_agents:
        plan.max_agents = max_agents
        plan.save(update_fields=["max_agents"])

    Subscription.objects.filter(tenant=tenant).delete()
    Subscription.objects.create(
        tenant=tenant, plan=plan, status=SubscriptionStatus.ACTIVE,
    )
    tenant.plan = plan
    tenant.save(update_fields=["plan"])

    # current_plan() caches the resolved plan id per schema.
    from django.core.cache import cache
    cache.delete(f"tenant_plan_id:{connection.schema_name}")
    return plan


def _fill_seats(n, prefix="seat"):
    for i in range(n):
        Agent.objects.create_agent(
            email=f"{prefix}{i}@example.com", name=f"Seat {i}", password="Pw@12345678",
        )


def _create_agent(actor, email="new@example.com"):
    request = APIRequestFactory().post("/api/v1/auth/agents/", {
        "email": email, "name": "New Joiner", "role": "agent",
        "password": "Pw@12345678", "confirm_password": "Pw@12345678",
    }, format="json")
    force_authenticate(request, user=actor)
    response = AgentListAPIView.as_view()(request)
    response.render()
    return response


def _reactivate(actor, agent):
    request = APIRequestFactory().post(f"/api/v1/auth/agents/{agent.pk}/reactivate/")
    force_authenticate(request, user=actor)
    response = AgentReactivateAPIView.as_view()(request, pk=agent.pk)
    response.render()
    return response


# ---- Where the number comes from ---------------------------------------

def test_without_an_override_the_plan_decides(tenant, admin):
    _plan(tenant, max_agents=5)

    assert agent_limit() == 5


def test_the_override_wins_over_the_plan(tenant, admin):
    """The whole point: one customer's seats, without touching the plan."""
    _plan(tenant, max_agents=5)
    tenant.max_agents_override = 12
    tenant.save(update_fields=["max_agents_override"])

    assert agent_limit() == 12


def test_the_override_can_hold_a_tenant_below_their_plan(tenant, admin):
    _plan(tenant, max_agents=100)
    tenant.max_agents_override = 3
    tenant.save(update_fields=["max_agents_override"])

    assert agent_limit() == 3


def test_an_override_of_zero_is_a_decision_not_a_blank(tenant, admin):
    """
    0 must mean "no more agents", not "fall back to the plan" — otherwise
    freezing an overdue account would quietly grant them their plan's seats.
    """
    _plan(tenant, max_agents=50)
    tenant.max_agents_override = 0
    tenant.save(update_fields=["max_agents_override"])

    assert agent_limit() == 0


def test_no_plan_and_no_override_means_no_cap(tenant, admin):
    """A tenant with nothing resolvable is not locked out of hiring."""
    Subscription.objects.filter(tenant=tenant).delete()
    from django.core.cache import cache
    cache.delete(f"tenant_plan_id:{connection.schema_name}")

    assert agent_limit() is None


# ---- Creating an agent --------------------------------------------------

def test_a_tenant_under_the_cap_can_add_an_agent(tenant, admin):
    _plan(tenant, max_agents=5)

    r = _create_agent(admin)

    assert r.status_code == 201, r.data
    assert Agent.objects.filter(email="new@example.com").exists()


def test_the_cap_refuses_the_seat_that_would_exceed_it(tenant, admin):
    _plan(tenant, max_agents=3)
    _fill_seats(2)  # plus the admin = 3 active

    r = _create_agent(admin)

    assert r.status_code == 402, r.data
    assert not Agent.objects.filter(email="new@example.com").exists()


def test_a_raised_override_lets_them_past_the_plan_limit(tenant, admin):
    """What a super admin does after selling extra seats."""
    _plan(tenant, max_agents=3)
    _fill_seats(2)
    assert _create_agent(admin).status_code == 402

    tenant.max_agents_override = 4
    tenant.save(update_fields=["max_agents_override"])

    assert _create_agent(admin).status_code == 201


def test_a_lowered_override_refuses_even_within_the_plan(tenant, admin):
    _plan(tenant, max_agents=50)
    tenant.max_agents_override = 1
    tenant.save(update_fields=["max_agents_override"])  # the admin already holds it

    r = _create_agent(admin)

    assert r.status_code == 402


def test_the_refusal_says_what_the_limit_is(tenant, admin):
    _plan(tenant, max_agents=2)
    _fill_seats(1)

    body = str(_create_agent(admin).data)

    assert "2" in body, "an admin who cannot add an agent must be told the number"


def test_a_deactivated_agent_does_not_hold_a_seat(tenant, admin):
    _plan(tenant, max_agents=2)
    _fill_seats(1)
    Agent.objects.filter(email="seat0@example.com").update(is_active=False)

    assert _create_agent(admin).status_code == 201


# ---- Reactivating -------------------------------------------------------

def test_reactivating_is_refused_when_that_would_exceed_the_cap(tenant, admin):
    """Otherwise deactivate/reactivate is a way round the cap."""
    _plan(tenant, max_agents=2)
    _fill_seats(2)
    parked = Agent.objects.get(email="seat1@example.com")
    parked.is_active = False
    parked.save(update_fields=["is_active"])
    _fill_seats(1, prefix="replacement")  # back to 3 active: admin + seat0 + replacement0

    r = _reactivate(admin, parked)

    assert r.status_code == 402
    parked.refresh_from_db()
    assert parked.is_active is False


def test_reactivating_within_the_cap_works(tenant, admin):
    _plan(tenant, max_agents=5)
    _fill_seats(1)
    parked = Agent.objects.get(email="seat0@example.com")
    parked.is_active = False
    parked.save(update_fields=["is_active"])

    r = _reactivate(admin, parked)

    assert r.status_code == 200, r.data
    parked.refresh_from_db()
    assert parked.is_active is True
