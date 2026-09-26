"""
Nobody grants a role at or above their own.

A manager may edit agents they outrank — but the check compared the manager
with the agent's CURRENT role only, and `role` accepted any value. A manager
could PATCH an agent to "admin", and IsTenantAdmin grants on role alone, so
a manager could mint tenant admins: billing, Flush All Leads, integrations,
agent management.
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.authentication.views import AgentDetailAPIView
from apps.core.constants import AgentRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(
        email="owner@example.com", name="Owner", password="Pw@12345678",
    )


@pytest.fixture
def manager():
    return Agent.objects.create_agent(
        email="mgr@example.com", name="Manager", password="Pw@12345678",
        role=AgentRole.MANAGER,
    )


@pytest.fixture
def agent():
    return Agent.objects.create_agent(
        email="floor@example.com", name="Floor", password="Pw@12345678",
    )


def _set_role(actor, target, role):
    request = APIRequestFactory().patch(
        f"/api/v1/auth/agents/{target.pk}/", {"role": role}, format="json",
    )
    force_authenticate(request, user=actor)
    response = AgentDetailAPIView.as_view()(request, pk=target.pk)
    response.render()
    return response


def test_a_manager_cannot_make_an_agent_an_admin(manager, agent):
    """The escalation itself."""
    r = _set_role(manager, agent, AgentRole.ADMIN)

    assert r.status_code == 400
    agent.refresh_from_db()
    assert agent.role == AgentRole.AGENT


def test_a_manager_cannot_make_an_agent_a_manager(manager, agent):
    """A peer is as good as an admin for widening what someone can see."""
    r = _set_role(manager, agent, AgentRole.MANAGER)

    assert r.status_code == 400
    agent.refresh_from_db()
    assert agent.role == AgentRole.AGENT


def test_a_manager_can_still_promote_within_their_range(manager, agent):
    r = _set_role(manager, agent, AgentRole.SENIOR_AGENT)

    assert r.status_code == 200, r.data
    agent.refresh_from_db()
    assert agent.role == AgentRole.SENIOR_AGENT


def test_an_admin_can_assign_any_role(admin, agent):
    assert _set_role(admin, agent, AgentRole.MANAGER).status_code == 200
    agent.refresh_from_db()
    assert _set_role(admin, agent, AgentRole.ADMIN).status_code == 200
    agent.refresh_from_db()
    assert agent.role == AgentRole.ADMIN


def test_resending_the_current_role_is_harmless(manager, agent):
    """A form that re-posts every field must not be refused for 'role'."""
    request = APIRequestFactory().patch(
        f"/api/v1/auth/agents/{agent.pk}/",
        {"role": AgentRole.AGENT, "name": "Renamed"}, format="json",
    )
    force_authenticate(request, user=manager)
    response = AgentDetailAPIView.as_view()(request, pk=agent.pk)

    assert response.status_code == 200
