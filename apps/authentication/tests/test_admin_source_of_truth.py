"""
"Admin" means one thing (MED-11).

The API authorises on `role == "admin"`; the web app gated admin screens on
`is_tenant_admin`. An owner whose role had drifted kept admin screens whose
actions all returned 403. The owner account is now always an admin by role.
"""
import pytest

from apps.authentication.models import Agent
from apps.authentication.permissions import IsTenantAdmin
from apps.core.constants import AgentRole

pytestmark = pytest.mark.django_db


class _Req:
    def __init__(self, user):
        self.user = user


def test_the_owner_cannot_drift_out_of_the_admin_role():
    owner = Agent.objects.create_tenant_admin(email="own@x.com", name="Owner", password="Pw@12345678")

    owner.role = AgentRole.MANAGER
    owner.save()
    owner.refresh_from_db()

    assert owner.role == AgentRole.ADMIN
    assert IsTenantAdmin().has_permission(_Req(owner), None)


def test_a_second_admin_is_an_admin_to_the_api_without_being_the_owner():
    second = Agent.objects.create_agent(
        email="two@x.com", name="Two", password="Pw@12345678", role=AgentRole.ADMIN,
    )

    assert not second.is_tenant_admin
    assert IsTenantAdmin().has_permission(_Req(second), None)
