"""
Which endpoints are rate-limited, and by how much.

Every AllowAny DRF view that did not override throttle_classes fell under the
default anonymous throttle — 20 requests an hour per IP. That included:

  * the WhatsApp and call-provider webhooks: from the 21st callback in an hour
    the provider got a 429, so a campaign lost almost all delivery statuses
    (demonstrated live: posts 21-24 answered 429);
  * token refresh: twenty agents behind one office address exhausted it and
    were signed out.

Registration declared a "registration" scope that never applied, because
ScopedRateThrottle was not enabled and the rate was not defined.
"""
import pytest
from django.conf import settings
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle

from apps.authentication.views import AgentRefreshTokenAPIView, TenantInfoAPIView
from apps.calls.views import CallProviderWebhookView
from apps.communications.views import WhatsAppWebhookView
from apps.tenants.views import TenantCheckSubdomainAPIView, TenantRegistrationAPIView

# The PRODUCTION rates. Test settings raise every rate out of reach so other
# tests are never throttled, so the real numbers are read from base.
from config.settings import base as base_settings  # noqa: E402

RATES = base_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]


def _classes(view):
    return [t.__class__ for t in view().get_throttles()]


@pytest.mark.parametrize("view", [WhatsAppWebhookView, CallProviderWebhookView])
def test_provider_webhooks_are_not_throttled(view):
    assert _classes(view) == []


@pytest.mark.parametrize("view,scope", [
    (AgentRefreshTokenAPIView, "token_refresh"),
    (TenantInfoAPIView, "tenant_info"),
    (TenantRegistrationAPIView, "registration"),
    (TenantCheckSubdomainAPIView, "subdomain_check"),
])
def test_pre_auth_endpoints_use_their_own_scope(view, scope):
    assert _classes(view) == [ScopedRateThrottle]
    assert AnonRateThrottle not in _classes(view)
    assert view.throttle_scope == scope
    assert scope in RATES, f"no rate defined for {scope!r} — the scope would do nothing"


def test_an_office_of_agents_can_refresh():
    """At least a hundred refreshes an hour from one address."""
    count, period = RATES["token_refresh"].split("/")
    per_hour = int(count) * {"second": 3600, "minute": 60, "hour": 1, "day": 1 / 24}[period]
    assert per_hour >= 100


def test_typing_a_subdomain_cannot_use_up_registration():
    assert TenantCheckSubdomainAPIView.throttle_scope != TenantRegistrationAPIView.throttle_scope
