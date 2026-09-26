"""
What an agent may change on a lead.

Bulk assignment was manager-only, but PATCH /leads/{id}/ let any agent set
`assigned_to` on a lead they could see — handing leads away, or collecting
them through a colleague — set `score` by hand, and DELETE the lead. Nothing
checked the new owner was an active agent.
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.core.constants import AgentRole
from apps.leads.models import Lead
from apps.leads.views import LeadDetailView

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent():
    return Agent.objects.create_agent(email="a@example.com", name="Asha", password="Pw@12345678")


@pytest.fixture
def colleague():
    return Agent.objects.create_agent(email="b@example.com", name="Bilal", password="Pw@12345678")


@pytest.fixture
def manager():
    return Agent.objects.create_agent(
        email="m@example.com", name="Mona", password="Pw@12345678", role=AgentRole.MANAGER,
    )


@pytest.fixture
def lead(agent):
    return Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=agent, score=40)


def _patch(user, lead, **data):
    request = APIRequestFactory().patch(f"/api/v1/leads/{lead.pk}/", data, format="json")
    force_authenticate(request, user=user)
    response = LeadDetailView.as_view()(request, pk=lead.pk)
    response.render()
    return response


def _delete(user, lead):
    request = APIRequestFactory().delete(f"/api/v1/leads/{lead.pk}/")
    force_authenticate(request, user=user)
    return LeadDetailView.as_view()(request, pk=lead.pk)


# ---- Reassignment ------------------------------------------------------

def test_an_agent_cannot_hand_their_lead_to_someone_else(agent, colleague, lead):
    r = _patch(agent, lead, assigned_to=colleague.pk)

    assert r.status_code == 400
    lead.refresh_from_db()
    assert lead.assigned_to == agent


def test_a_manager_can_reassign(manager, colleague, lead):
    r = _patch(manager, lead, assigned_to=colleague.pk)

    assert r.status_code == 200, r.data
    lead.refresh_from_db()
    assert lead.assigned_to == colleague


def test_a_lead_cannot_go_to_a_deactivated_agent(manager, colleague, lead):
    colleague.is_active = False
    colleague.save(update_fields=["is_active"])

    r = _patch(manager, lead, assigned_to=colleague.pk)

    assert r.status_code == 400


def test_an_agent_can_still_edit_their_lead(agent, lead):
    """The restriction is on ownership, not on ordinary edits."""
    r = _patch(agent, lead, city="Pune", status="contacted")

    assert r.status_code == 200, r.data
    lead.refresh_from_db()
    assert lead.city == "Pune"


def test_resending_the_current_owner_is_harmless(agent, lead):
    """A form that re-posts every field must not trip the rule."""
    assert _patch(agent, lead, assigned_to=agent.pk, city="Pune").status_code == 200


# ---- Score -------------------------------------------------------------

def test_score_is_not_set_by_hand(agent, lead):
    _patch(agent, lead, score=100)

    lead.refresh_from_db()
    assert lead.score == 40


# ---- Deletion ----------------------------------------------------------

def test_an_agent_cannot_delete_a_lead(agent, lead):
    assert _delete(agent, lead).status_code == 403
    lead.refresh_from_db()
    assert lead.is_deleted is False


def test_a_manager_can_delete_a_lead(manager, lead):
    assert _delete(manager, lead).status_code == 204
    lead.refresh_from_db()
    assert lead.is_deleted is True
