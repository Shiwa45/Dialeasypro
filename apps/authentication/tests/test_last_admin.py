"""
A tenant always keeps an admin.

Nothing stopped an admin deactivating their own account, or the only admin
being deactivated or demoted — leaving the tenant with nobody who could manage
agents, billing or integrations.
"""
import pytest
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.authentication.serializers import check_admin_removal
from apps.authentication.views import AgentDetailAPIView
from apps.core.constants import AgentRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    # The test schema is seeded with a tenant admin of its own; take it out of
    # the picture so "the only admin" really is the only one.
    Agent.objects.filter(role=AgentRole.ADMIN).update(is_active=False)
    return Agent.objects.create_tenant_admin(email="only@x.com", name="Only", password="Pw@12345678")


@pytest.fixture
def second_admin(admin):
    return Agent.objects.create_tenant_admin(email="two@x.com", name="Two", password="Pw@12345678")


def _call(method, actor, target, data=None):
    factory = APIRequestFactory()
    url = f"/api/v1/auth/agents/{target.pk}/"
    request = factory.delete(url) if method == "delete" else factory.patch(url, data, format="json")
    force_authenticate(request, user=actor)
    response = AgentDetailAPIView.as_view()(request, pk=target.pk)
    response.render()
    target.refresh_from_db()
    return response


# ---- The endpoint: DELETE is open to any admin, including on themselves ----

def test_an_admin_cannot_deactivate_themselves(admin, second_admin):
    """Even with another admin around — you don't lock yourself out."""
    assert _call("delete", admin, admin).status_code == 400
    assert admin.is_active


def test_the_only_admin_cannot_deactivate_themselves(admin):
    assert _call("delete", admin, admin).status_code == 400
    assert admin.is_active


def test_with_two_admins_one_can_remove_the_other(admin, second_admin):
    assert _call("delete", admin, second_admin).status_code == 204
    assert not second_admin.is_active


def test_ordinary_agents_are_unaffected(admin):
    agent = Agent.objects.create_agent(email="a@x.com", name="A", password="Pw@12345678")

    assert _call("delete", admin, agent).status_code == 204


# ---- The rule itself, which the update serializer also applies ----------
# PATCH on an admin is refused earlier by CanManageAgent today; this keeps the
# guarantee if that permission is ever loosened.

def test_the_only_admin_cannot_be_deactivated_or_demoted(admin):
    with pytest.raises(ValidationError):
        check_admin_removal(None, admin, deactivating=True)
    with pytest.raises(ValidationError):
        check_admin_removal(None, admin, new_role=AgentRole.MANAGER)


def test_with_another_admin_either_is_fine(admin, second_admin):
    check_admin_removal(None, admin, deactivating=True)
    check_admin_removal(None, admin, new_role=AgentRole.MANAGER)


def test_keeping_the_admin_role_is_not_a_removal(admin):
    check_admin_removal(admin, admin, new_role=AgentRole.ADMIN)
