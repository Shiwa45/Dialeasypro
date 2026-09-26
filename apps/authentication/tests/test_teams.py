"""
Teams.

The model, the permission rules and half an API existed; the part that puts
an agent IN a team did not. Teams could be listed and created and nothing
else — no rename, no disband, and no way to add a member through any
interface. Both rules that depend on membership were therefore inert:

  * a MANAGER only sees agents who share a team with them, so a manager saw
    nobody at all;
  * a SENIOR AGENT sees their teammates' leads, so they saw only their own.

And AgentTeam.is_team_lead has promised since the model was written that
"team leads can view their team members' leads", while nothing read the
field — marking somebody a lead changed nothing.
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent, AgentTeam, Team
from apps.authentication.views import (
    AgentListAPIView, TeamDetailAPIView, TeamListAPIView, TeamMembersAPIView,
)
from apps.core.constants import AgentRole
from apps.leads.models import Lead
from apps.leads.views import leads_visible_to

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(
        email="owner@example.com", name="Owner", password="Pw@12345678",
    )


@pytest.fixture
def agents():
    return [
        Agent.objects.create_agent(
            email=f"a{i}@example.com", name=f"Agent {i}", password="Pw@12345678",
        )
        for i in range(3)
    ]


def _post_team(user, **payload):
    request = APIRequestFactory().post("/api/v1/auth/teams/", payload, format="json")
    force_authenticate(request, user=user)
    response = TeamListAPIView.as_view()(request)
    response.render()
    return response


def _patch_team(user, team, **payload):
    request = APIRequestFactory().patch(f"/api/v1/auth/teams/{team.pk}/", payload, format="json")
    force_authenticate(request, user=user)
    response = TeamDetailAPIView.as_view()(request, pk=team.pk)
    response.render()
    return response


def _add_member(user, team, agent, is_team_lead=False):
    request = APIRequestFactory().post(
        f"/api/v1/auth/teams/{team.pk}/members/",
        {"agent_id": agent.pk, "is_team_lead": is_team_lead}, format="json",
    )
    force_authenticate(request, user=user)
    response = TeamMembersAPIView.as_view()(request, pk=team.pk)
    response.render()
    return response


def _remove_member(user, team, agent):
    request = APIRequestFactory().delete(
        f"/api/v1/auth/teams/{team.pk}/members/{agent.pk}/")
    force_authenticate(request, user=user)
    response = TeamMembersAPIView.as_view()(request, pk=team.pk, agent_id=agent.pk)
    response.render()
    return response


# ---- Making and editing a team ----------------------------------------

def test_an_admin_can_create_a_team(admin):
    r = _post_team(admin, name="North Zone", description="Pune and Nashik")

    assert r.status_code == 201, r.data
    assert Team.objects.filter(name="North Zone").exists()


def test_a_duplicate_team_name_is_refused(admin):
    Team.objects.create(name="North Zone")

    r = _post_team(admin, name="north zone")

    assert r.status_code == 400
    assert "already exists" in str(r.data)


def test_a_team_can_be_renamed(admin):
    team = Team.objects.create(name="North Zone")

    r = _patch_team(admin, team, name="West Zone", description="Mumbai")

    assert r.status_code == 200, r.data
    team.refresh_from_db()
    assert team.name == "West Zone"
    assert team.description == "Mumbai"


def test_disbanding_keeps_the_team_rather_than_deleting_it(admin, agents):
    """
    Memberships cascade, and membership decides who can see whom. Deleting
    the rows would change visibility with nothing left to explain why.
    """
    team = Team.objects.create(name="North Zone")
    AgentTeam.objects.create(team=team, agent=agents[0])

    request = APIRequestFactory().delete(f"/api/v1/auth/teams/{team.pk}/")
    force_authenticate(request, user=admin)
    response = TeamDetailAPIView.as_view()(request, pk=team.pk)

    assert response.status_code == 204
    team.refresh_from_db()
    assert team.is_active is False
    assert AgentTeam.objects.filter(team=team).exists(), "membership survives"


# ---- Putting agents in it ---------------------------------------------

def test_an_agent_can_be_added_to_a_team(admin, agents):
    """The thing that could not be done at all."""
    team = Team.objects.create(name="North Zone")

    r = _add_member(admin, team, agents[0])

    assert r.status_code == 201, r.data
    assert AgentTeam.objects.filter(team=team, agent=agents[0]).exists()


def test_the_team_answers_with_who_is_in_it(admin, agents):
    team = Team.objects.create(name="North Zone")
    _add_member(admin, team, agents[0])
    r = _add_member(admin, team, agents[1], is_team_lead=True)

    names = {m["name"] for m in r.data["members"]}
    assert names == {"Agent 0", "Agent 1"}
    assert r.data["member_count"] == 2
    lead = next(m for m in r.data["members"] if m["name"] == "Agent 1")
    assert lead["is_team_lead"] is True


def test_adding_someone_twice_updates_their_role_instead_of_failing(admin, agents):
    team = Team.objects.create(name="North Zone")
    _add_member(admin, team, agents[0])

    r = _add_member(admin, team, agents[0], is_team_lead=True)

    assert r.status_code == 200
    assert AgentTeam.objects.get(team=team, agent=agents[0]).is_team_lead is True
    assert AgentTeam.objects.filter(team=team, agent=agents[0]).count() == 1


def test_an_agent_can_be_removed(admin, agents):
    team = Team.objects.create(name="North Zone")
    _add_member(admin, team, agents[0])

    r = _remove_member(admin, team, agents[0])

    assert r.status_code == 200
    assert not AgentTeam.objects.filter(team=team, agent=agents[0]).exists()


def test_removing_someone_who_is_not_in_the_team_says_so(admin, agents):
    team = Team.objects.create(name="North Zone")

    assert _remove_member(admin, team, agents[0]).status_code == 404


def test_an_agent_cannot_change_team_membership(agents):
    """Membership decides who can see whose leads."""
    team = Team.objects.create(name="North Zone")

    assert _add_member(agents[0], team, agents[1]).status_code == 403


# ---- What membership actually does ------------------------------------

def test_a_manager_sees_the_agents_who_share_their_team(admin, agents):
    """
    The manager's agent list filters on shared teams. With no way to add a
    member, a manager saw an empty list.
    """
    manager = Agent.objects.create_agent(
        email="mgr@example.com", name="Manager", password="Pw@12345678",
        role=AgentRole.MANAGER,
    )
    team = Team.objects.create(name="North Zone")
    _add_member(admin, team, manager)
    _add_member(admin, team, agents[0])

    request = APIRequestFactory().get("/api/v1/auth/agents/")
    force_authenticate(request, user=manager)
    response = AgentListAPIView.as_view()(request)
    response.render()

    names = {a["name"] for a in response.data["results"]}
    assert "Agent 0" in names
    assert "Agent 2" not in names, "not in the manager's team"


def test_a_team_lead_sees_their_teams_leads(admin, agents):
    """
    is_team_lead has promised this since the model was written and nothing
    ever read the field.
    """
    team = Team.objects.create(name="North Zone")
    lead_agent, member, outsider = agents
    _add_member(admin, team, lead_agent, is_team_lead=True)
    _add_member(admin, team, member)

    mine = Lead.objects.create(name="Mine", phone="+919812300001", assigned_to=lead_agent)
    teammates = Lead.objects.create(name="Teammate's", phone="+919812300002", assigned_to=member)
    theirs = Lead.objects.create(name="Outsider's", phone="+919812300003", assigned_to=outsider)

    visible = set(leads_visible_to(lead_agent).values_list("pk", flat=True))

    assert mine.pk in visible
    assert teammates.pk in visible
    assert theirs.pk not in visible


def test_a_plain_member_still_only_sees_their_own(admin, agents):
    """Being in a team is not the same as leading one."""
    team = Team.objects.create(name="North Zone")
    _add_member(admin, team, agents[0])
    _add_member(admin, team, agents[1])

    mine = Lead.objects.create(name="Mine", phone="+919812300004", assigned_to=agents[0])
    theirs = Lead.objects.create(name="Theirs", phone="+919812300005", assigned_to=agents[1])

    visible = set(leads_visible_to(agents[0]).values_list("pk", flat=True))

    assert visible == {mine.pk}
    assert theirs.pk not in visible


def test_losing_the_lead_flag_takes_the_visibility_with_it(admin, agents):
    team = Team.objects.create(name="North Zone")
    _add_member(admin, team, agents[0], is_team_lead=True)
    _add_member(admin, team, agents[1])
    Lead.objects.create(name="Theirs", phone="+919812300006", assigned_to=agents[1])

    assert leads_visible_to(agents[0]).count() == 1

    _add_member(admin, team, agents[0], is_team_lead=False)

    assert leads_visible_to(agents[0]).count() == 0


# ---- Listing ----------------------------------------------------------

def test_disbanded_teams_are_out_of_the_way_but_recoverable(admin):
    Team.objects.create(name="Live team")
    Team.objects.create(name="Old team", is_active=False)

    request = APIRequestFactory().get("/api/v1/auth/teams/")
    force_authenticate(request, user=admin)
    response = TeamListAPIView.as_view()(request)
    response.render()
    names = {t["name"] for t in response.data["results"]}
    assert names == {"Live team"}

    request = APIRequestFactory().get("/api/v1/auth/teams/", {"include_inactive": "true"})
    force_authenticate(request, user=admin)
    response = TeamListAPIView.as_view()(request)
    response.render()
    names = {t["name"] for t in response.data["results"]}
    assert "Old team" in names
