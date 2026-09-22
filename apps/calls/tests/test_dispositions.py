"""
Managing call dispositions from the CRM.

Dispositions are per-tenant by design — every team's outcomes differ, and the
seeded set is only a starting point. But the API exposed a list endpoint and
nothing else, so a tenant admin could not add "Site visit booked" or correct a
wrong auto-follow-up delay from anywhere in the product. The settings screen
said as much: it told admins to go and run a management command on the server.

Deletion is the part worth being careful about. CallLog.disposition is
SET_NULL, so removing an outcome that calls already carry would blank it on
every one of those calls — the outcome history the reports, the dashboard's
positive-rate and the AI insights all read from.
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.calls.models import CallDisposition, CallLog
from apps.calls.views import CallDispositionDetailView, CallDispositionListView

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(
        email="owner@example.com", name="Owner", password="Pw@12345678",
    )


@pytest.fixture
def agent():
    return Agent.objects.create_agent(
        email="caller@example.com", name="Caller", password="Pw@12345678",
    )


def _post(user, **payload):
    request = APIRequestFactory().post("/api/v1/calls/dispositions/", payload, format="json")
    force_authenticate(request, user=user)
    response = CallDispositionListView.as_view()(request)
    response.render()
    return response


def _patch(user, pk, **payload):
    request = APIRequestFactory().patch(f"/api/v1/calls/dispositions/{pk}/", payload, format="json")
    force_authenticate(request, user=user)
    response = CallDispositionDetailView.as_view()(request, pk=pk)
    response.render()
    return response


def _delete(user, pk):
    request = APIRequestFactory().delete(f"/api/v1/calls/dispositions/{pk}/")
    force_authenticate(request, user=user)
    response = CallDispositionDetailView.as_view()(request, pk=pk)
    response.render()
    return response


def _list(user, **params):
    request = APIRequestFactory().get("/api/v1/calls/dispositions/", params)
    force_authenticate(request, user=user)
    response = CallDispositionListView.as_view()(request)
    response.render()
    return response


# ---- Adding ------------------------------------------------------------

def test_an_admin_can_add_an_outcome(admin):
    r = _post(admin, name="Site visit booked", is_positive=True, auto_followup_hours=48)

    assert r.status_code == 201, r.data
    added = CallDisposition.objects.get(name="Site visit booked")
    assert added.is_positive is True
    assert added.auto_followup_hours == 48
    assert added.is_active is True


def test_the_slug_is_derived_so_nobody_has_to_invent_one(admin):
    """The settings form asks for a name; the slug is plumbing."""
    r = _post(admin, name="Site Visit Booked")

    assert r.data["slug"] == "site-visit-booked"


def test_two_outcomes_never_collide_on_a_slug(admin):
    """
    slug is unique, and an IntegrityError here would surface as a 500 on a
    form an admin is simply typing into.
    """
    CallDisposition.objects.create(name="Callback", slug="callback")

    r = _post(admin, name="Call back!")

    assert r.status_code == 201, r.data
    assert r.data["slug"] == "call-back"
    assert CallDisposition.objects.filter(slug="callback").count() == 1


def test_a_duplicate_name_is_refused_rather_than_quietly_renamed(admin):
    CallDisposition.objects.create(name="Not Reachable", slug="not-reachable")

    r = _post(admin, name="not reachable")

    assert r.status_code == 400
    assert "already exists" in str(r.data)


def test_a_duplicate_of_a_switched_off_outcome_says_to_switch_it_back_on(admin):
    CallDisposition.objects.create(name="Wrong Number", slug="wrong-number", is_active=False)

    r = _post(admin, name="Wrong Number")

    assert r.status_code == 400
    assert "switch it back on" in str(r.data)


def test_an_agent_cannot_add_one(agent):
    """Outcomes drive follow-up automation and reporting; they are admin config."""
    r = _post(agent, name="Whatever")

    assert r.status_code == 403
    assert not CallDisposition.objects.filter(name="Whatever").exists()


# ---- Editing -----------------------------------------------------------

def test_an_admin_can_correct_an_outcome(admin):
    d = CallDisposition.objects.create(name="Callback", slug="callback", auto_followup_hours=2)

    r = _patch(admin, d.pk, name="Callback requested", auto_followup_hours=6, is_positive=True)

    assert r.status_code == 200, r.data
    d.refresh_from_db()
    assert d.name == "Callback requested"
    assert d.auto_followup_hours == 6
    assert d.is_positive is True


def test_editing_a_name_leaves_the_slug_alone(admin):
    """
    The slug is the handle the AI insight suggests by and past calls were
    logged under. Renaming the label must not silently repoint it.
    """
    d = CallDisposition.objects.create(name="Callback", slug="callback")

    _patch(admin, d.pk, name="Callback requested", slug="")

    d.refresh_from_db()
    assert d.slug == "callback"


def test_an_outcome_can_be_switched_back_on(admin):
    d = CallDisposition.objects.create(name="Busy", slug="busy", is_active=False)

    r = _patch(admin, d.pk, is_active=True)

    assert r.status_code == 200
    d.refresh_from_db()
    assert d.is_active is True


def test_an_agent_cannot_edit_one(agent):
    d = CallDisposition.objects.create(name="Busy", slug="busy")

    r = _patch(agent, d.pk, name="Hijacked")

    assert r.status_code == 403
    d.refresh_from_db()
    assert d.name == "Busy"


# ---- Removing ----------------------------------------------------------

def test_an_unused_outcome_is_deleted_outright(admin):
    d = CallDisposition.objects.create(name="Typo", slug="typo")

    r = _delete(admin, d.pk)

    assert r.status_code == 204
    assert not CallDisposition.objects.filter(pk=d.pk).exists()


def test_an_outcome_with_calls_is_switched_off_instead_of_deleted(admin):
    """
    Deleting it would SET_NULL the disposition on every call logged under it,
    erasing the outcome from history to tidy up a dropdown.
    """
    d = CallDisposition.objects.create(name="Interested", slug="interested")
    call = CallLog.objects.create(agent=admin, phone_number="+919812345678", disposition=d)

    r = _delete(admin, d.pk)

    assert r.status_code == 200
    assert r.data["deactivated"] is True
    d.refresh_from_db()
    assert d.is_active is False

    call.refresh_from_db()
    assert call.disposition_id == d.pk, "the call kept its outcome"


# ---- What each audience sees -------------------------------------------

def test_agents_are_not_offered_a_switched_off_outcome(agent):
    CallDisposition.objects.create(name="Live", slug="live")
    CallDisposition.objects.create(name="Retired", slug="retired", is_active=False)

    names = {d["name"] for d in _list(agent).data}

    assert "Live" in names
    assert "Retired" not in names


def test_settings_can_ask_for_the_whole_set(admin):
    """Otherwise a switched-off outcome is invisible and can never be restored."""
    CallDisposition.objects.create(name="Retired", slug="retired", is_active=False)

    names = {d["name"] for d in _list(admin, include_inactive="true").data}

    assert "Retired" in names


def test_the_list_carries_what_the_settings_screen_edits(admin):
    CallDisposition.objects.create(
        name="Interested", slug="interested", is_positive=True, sort_order=3,
    )

    row = next(d for d in _list(admin).data if d["name"] == "Interested")

    assert {"id", "name", "slug", "is_positive", "is_active", "sort_order",
            "auto_followup_hours"} <= set(row)
