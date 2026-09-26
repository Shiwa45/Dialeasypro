"""
The old server-rendered UI is gone, and nothing points at it.

/crm/ was still routed, but none of its templates existed: every page was a
500, and the tenant host's root redirected there — so opening the API host in
a browser showed a server error. New agents' welcome emails linked to it too.
"""
import pytest
from django.core import mail
from django.test import RequestFactory, override_settings
from django.urls import Resolver404, resolve

from apps.authentication.models import Agent
from apps.authentication.tasks import send_agent_welcome_email
from apps.core.views import ApiRootView

TEST_SCHEMA = "test_tenant"


@pytest.mark.parametrize("path", ["/crm/", "/crm/login/", "/crm/leads/", "/crm/calls/"])
def test_the_legacy_pages_are_not_routed(path):
    with pytest.raises(Resolver404):
        resolve(path)


def test_the_superadmin_dashboard_without_a_template_is_not_routed():
    with pytest.raises(Resolver404):
        resolve("/superadmin-dashboard/", urlconf="config.urls_public")


@override_settings(FRONTEND_URL="https://app.example.com")
def test_the_root_sends_people_to_the_crm():
    response = ApiRootView.as_view()(RequestFactory().get("/"))

    assert response.status_code == 302
    assert response["Location"] == "https://app.example.com"


@override_settings(FRONTEND_URL="")
def test_without_a_frontend_url_the_root_still_answers():
    response = ApiRootView.as_view()(RequestFactory().get("/"))

    assert response.status_code == 200


@pytest.mark.django_db
@override_settings(FRONTEND_URL="https://app.example.com")
def test_the_welcome_email_links_to_the_crm_not_the_dead_ui():
    agent = Agent.objects.create_agent(email="new@x.com", name="New", password="Pw@12345678")
    mail.outbox.clear()

    send_agent_welcome_email.run(TEST_SCHEMA, agent.pk)

    body = mail.outbox[-1].body
    assert "/crm/" not in body
    assert "https://app.example.com" in body
    assert "Workspace ID: testtenant" in body
