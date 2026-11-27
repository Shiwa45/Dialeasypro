"""
Workspace admins manage their own custom fields (Settings → Custom Fields).

* admins add, edit, switch off and delete fields; everyone else only reads;
* the key is made from the name and stays unique;
* key and type are fixed once a field exists;
* a dropdown needs options;
* the plan's custom-field limit counts active fields.
"""
from types import SimpleNamespace
from unittest import mock

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.core.constants import AgentRole
from apps.leads.models import CustomField, CustomFieldValue, Lead
from apps.leads.views import CustomFieldDetailView, CustomFieldListView

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


@pytest.fixture
def admin():
    return Agent.objects.create_agent(email="ad@x.com", name="Admin", password="Pw@12345678",
                                      role=AgentRole.ADMIN)


@pytest.fixture
def agent():
    return Agent.objects.create_agent(email="ag@x.com", name="Asha", password="Pw@12345678")


def _call(view, method, user, data=None, query="", **kwargs):
    request = getattr(factory, method)(f"/x/{query}", data, format="json")
    force_authenticate(request, user=user)
    request.has_feature = lambda key: True
    return view.as_view()(request, **kwargs)


def _plan(limit):
    return mock.patch("apps.core.quotas.current_plan",
                      return_value=SimpleNamespace(custom_fields_limit=limit))


def test_admin_adds_a_field_and_gets_a_key(admin):
    r = _call(CustomFieldListView, "post", admin, {"name": "Budget Range", "field_type": "number"})
    assert r.status_code == 201, r.data
    assert r.data["field_key"] == "budget_range"

    # Same name again is refused; a different name with the same key gets a suffix.
    again = _call(CustomFieldListView, "post", admin, {"name": "budget range"})
    assert again.status_code == 400 and "already" in str(again.data)
    other = _call(CustomFieldListView, "post", admin, {"name": "Budget-Range!"})
    assert other.status_code == 201 and other.data["field_key"] == "budget_range_2"


def test_agents_can_read_but_not_change(admin, agent):
    field = CustomField.objects.create(name="Project", field_key="project")
    assert _call(CustomFieldListView, "get", agent).status_code == 200
    assert _call(CustomFieldListView, "post", agent, {"name": "X"}).status_code == 403
    assert _call(CustomFieldDetailView, "patch", agent, {"name": "Y"}, pk=field.pk).status_code == 403
    assert _call(CustomFieldDetailView, "delete", agent, pk=field.pk).status_code == 403


def test_switched_off_fields_are_listed_for_admins_only(admin, agent):
    CustomField.objects.create(name="On", field_key="on")
    CustomField.objects.create(name="Off", field_key="off", is_active=False)
    q = "?include_inactive=1"
    assert len(_call(CustomFieldListView, "get", admin, query=q).data) == 2
    assert [f["name"] for f in _call(CustomFieldListView, "get", agent, query=q).data] == ["On"]
    assert len(_call(CustomFieldListView, "get", admin).data) == 1


def test_a_dropdown_needs_options(admin):
    r = _call(CustomFieldListView, "post", admin, {"name": "Property", "field_type": "dropdown"})
    assert r.status_code == 400 and "option" in str(r.data)
    r = _call(CustomFieldListView, "post", admin,
              {"name": "Property", "field_type": "dropdown", "options": [" Flat ", "Villa", "flat", ""]})
    assert r.status_code == 201 and r.data["options"] == ["Flat", "Villa"]

    # Emptying the options later is refused too.
    r = _call(CustomFieldDetailView, "patch", admin, {"options": []}, pk=r.data["id"])
    assert r.status_code == 400


def test_key_and_type_are_fixed_but_the_rest_can_change(admin):
    field = CustomField.objects.create(name="Project", field_key="project")
    r = _call(CustomFieldDetailView, "patch", admin, {"field_type": "date"}, pk=field.pk)
    assert r.status_code == 400
    r = _call(CustomFieldDetailView, "patch", admin, {"field_key": "proj"}, pk=field.pk)
    assert r.status_code == 400
    r = _call(CustomFieldDetailView, "patch", admin,
              {"name": "Project name", "is_required": True, "sort_order": 3, "placeholder": "e.g. Skyline"},
              pk=field.pk)
    assert r.status_code == 200, r.data
    field.refresh_from_db()
    assert (field.name, field.field_key, field.is_required, field.sort_order) == ("Project name", "project", True, 3)


def test_the_plan_limit_counts_active_fields(admin):
    CustomField.objects.create(name="A", field_key="a")
    off = CustomField.objects.create(name="B", field_key="b", is_active=False)
    with _plan(1):
        r = _call(CustomFieldListView, "post", admin, {"name": "C"})
        assert r.status_code == 402
        # Switching a field back on counts as well.
        assert _call(CustomFieldDetailView, "patch", admin, {"is_active": True}, pk=off.pk).status_code == 402
    with _plan(2):
        assert _call(CustomFieldDetailView, "patch", admin, {"is_active": True}, pk=off.pk).status_code == 200
    with _plan(None):
        assert _call(CustomFieldListView, "post", admin, {"name": "C"}).status_code == 201


def test_deleting_a_field_removes_its_values(admin):
    field = CustomField.objects.create(name="Project", field_key="project")
    lead = Lead.objects.create(name="Ravi", phone="+919812300001")
    CustomFieldValue.objects.create(lead=lead, field=field, value="Skyline")
    assert _call(CustomFieldDetailView, "delete", admin, pk=field.pk).status_code == 204
    assert not CustomFieldValue.objects.exists()
