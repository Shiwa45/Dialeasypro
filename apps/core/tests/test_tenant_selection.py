"""
Which tenant a request is allowed to reach.

TenantSchemaFromTokenMiddleware switched the database schema for every /api/
request on an UNVERIFIED token claim or an X-Tenant-Schema header. Its safety
argument was that JWT authentication rejects a forgery later — true only for
authenticated endpoints. Anonymous endpoints have no later check, so anyone
could aim one at any tenant by schema name, without knowing its domain:
the unsigned lead webhooks, tenant-info. Demonstrated live: the public host
plus `X-Tenant-Schema: demo` returned Demo Realty's details with no login.

The rules now: the host decides when it names a tenant; only a token WE
signed may name another; the header works only on the sign-in endpoints that
run before a token exists.
"""
import base64
import json

import pytest
from django.db import connection
from django.test import RequestFactory

from apps.authentication.models import Agent
from apps.authentication.tokens import generate_tokens_for_agent
from apps.core.middleware import TenantSchemaFromTokenMiddleware

pytestmark = pytest.mark.django_db

TENANT = "test_tenant"


@pytest.fixture
def signed_token():
    agent = Agent.objects.create_tenant_admin(
        email="owner@example.com", name="Owner", password="Pw@12345678",
    )
    return generate_tokens_for_agent(agent)["access"]


def _forged_token(schema=TENANT):
    """A well-formed JWT with the right claim and a signature we did not make."""
    b64 = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'HS256', 'typ': 'JWT'})}.{b64({'tenant_schema': schema, 'agent_id': 1})}.forged"


def _run(path, *, host_schema, headers=None, token=None):
    """Run the middleware as if the host had resolved to `host_schema`."""
    extra = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in (headers or {}).items()}
    if token:
        extra["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    request = RequestFactory().get(path, **extra)

    previous = connection.schema_name
    connection.set_schema(host_schema)
    try:
        TenantSchemaFromTokenMiddleware(lambda r: None).process_request(request)
        return connection.schema_name
    finally:
        connection.set_schema(previous)


# ---- The exploit -------------------------------------------------------

def test_a_header_cannot_route_an_anonymous_webhook_to_a_tenant():
    reached = _run("/api/v1/integrations/google/", host_schema="public",
                   headers={"X-Tenant-Schema": TENANT})

    assert reached == "public"


def test_a_header_cannot_route_an_anonymous_api_call_to_a_tenant():
    reached = _run("/api/v1/calls/", host_schema="public",
                   headers={"X-Tenant-Schema": TENANT})

    assert reached == "public"


def test_a_forged_token_cannot_choose_the_tenant():
    """The claim used to be read without checking who signed it."""
    reached = _run("/api/v1/calls/", host_schema="public", token=_forged_token())

    assert reached == "public"


def test_a_header_never_overrides_a_tenant_host():
    reached = _run("/api/v1/calls/", host_schema=TENANT,
                   headers={"X-Tenant-Schema": "some_other_tenant"})

    assert reached == TENANT


# ---- The legitimate paths ----------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/v1/auth/login/", "/api/v1/auth/refresh/", "/api/v1/auth/tenant-info/",
])
def test_sign_in_on_a_host_that_names_no_tenant_can_use_the_header(path):
    """The mobile app reaching the server by IP address signs in this way."""
    reached = _run(path, host_schema="public", headers={"X-Tenant-Schema": TENANT})

    assert reached == TENANT


def test_a_signed_token_reaches_its_tenant_from_a_host_that_names_none(signed_token):
    reached = _run("/api/v1/calls/", host_schema="public", token=signed_token)

    assert reached == TENANT


def test_a_signed_token_on_its_own_tenant_host_is_left_alone(signed_token):
    assert _run("/api/v1/calls/", host_schema=TENANT, token=signed_token) == TENANT


def test_the_public_schema_is_never_targeted():
    reached = _run("/api/v1/auth/login/", host_schema="public",
                   headers={"X-Tenant-Schema": "public"})

    assert reached == "public"
