"""
The JWT backend (LOW-8, LOW-9).

LOW-8: a token with no tenant claim (or "public") was accepted and resolved
in whichever tenant the request was addressed to.
LOW-9: every authenticated request saved the agent row to bump
last_active_at — one extra write per API call.
"""
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory
from rest_framework_simplejwt.tokens import AccessToken

from apps.authentication import backends
from apps.authentication.models import Agent
from apps.authentication.tokens import generate_tokens_for_agent

pytestmark = pytest.mark.django_db

Backend = backends.AgentJWTAuthentication


@pytest.fixture
def agent():
    return Agent.objects.create_agent(email="a@x.com", name="A", password="Pw@12345678")


def _auth(token):
    request = APIRequestFactory().get("/api/v1/leads/", HTTP_AUTHORIZATION=f"Bearer {token}")
    return Backend().authenticate(request)


@pytest.mark.parametrize("claim", [None, "public"])
def test_a_token_without_a_tenant_is_refused(agent, claim):
    token = AccessToken(generate_tokens_for_agent(agent)["access"])
    if claim is None:
        del token["tenant_schema"]
    else:
        token["tenant_schema"] = claim

    with pytest.raises(AuthenticationFailed):
        _auth(str(token))


def test_a_normal_token_still_works(agent):
    user, _ = _auth(generate_tokens_for_agent(agent)["access"])
    assert user.pk == agent.pk


def test_recent_activity_is_not_rewritten_on_every_request(agent):
    token = generate_tokens_for_agent(agent)["access"]
    Agent.objects.filter(pk=agent.pk).update(last_active_at=timezone.now())

    with CaptureQueriesContext(connection) as queries:
        _auth(token)

    writes = [q["sql"] for q in queries if q["sql"].lstrip().upper().startswith("UPDATE")]
    assert writes == []


def test_stale_activity_is_refreshed(agent):
    token = generate_tokens_for_agent(agent)["access"]
    old = timezone.now() - timedelta(minutes=10)
    Agent.objects.filter(pk=agent.pk).update(last_active_at=old)

    _auth(token)

    agent.refresh_from_db()
    assert agent.last_active_at > old
