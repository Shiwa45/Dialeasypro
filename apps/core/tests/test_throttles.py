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
    scopes = {t.scope for t in TenantRegistrationAPIView.throttle_classes}
    assert TenantCheckSubdomainAPIView.throttle_scope not in scopes


# ---- MED-10: signup builds a schema, so it is limited three ways ---------

def _allowed(throttle_cls, ip, times):
    from unittest.mock import patch

    from django.core.cache import cache
    from rest_framework.test import APIRequestFactory

    results = []
    with patch.object(throttle_cls, "THROTTLE_RATES", RATES):
        for _ in range(times):
            request = APIRequestFactory().post("/api/v1/public/register/", REMOTE_ADDR=ip)
            results.append(throttle_cls().allow_request(request, None))
    return results


@pytest.fixture
def clean_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def test_one_address_gets_three_signups_an_hour(clean_cache):
    from apps.tenants.throttles import RegistrationBurstThrottle

    assert _allowed(RegistrationBurstThrottle, "203.0.113.5", 4) == [True, True, True, False]


def test_one_address_gets_ten_signups_a_day(clean_cache):
    from apps.tenants.throttles import RegistrationDailyThrottle

    assert _allowed(RegistrationDailyThrottle, "203.0.113.6", 11)[-2:] == [True, False]


def test_the_platform_cap_is_shared_by_every_address(clean_cache):
    from unittest.mock import patch

    from apps.tenants.throttles import RegistrationPlatformThrottle

    rates = {**RATES, "registration_platform": "2/day"}
    with patch.object(RegistrationPlatformThrottle, "THROTTLE_RATES", rates):
        from rest_framework.test import APIRequestFactory

        verdicts = [
            RegistrationPlatformThrottle().allow_request(
                APIRequestFactory().post("/", REMOTE_ADDR=f"198.51.100.{i}"), None)
            for i in range(3)
        ]
    assert verdicts == [True, True, False], "different addresses must share the cap"


def test_signup_uses_all_three_limits():
    from apps.tenants.throttles import (
        RegistrationBurstThrottle, RegistrationDailyThrottle, RegistrationPlatformThrottle,
    )

    assert TenantRegistrationAPIView.throttle_classes == [
        RegistrationBurstThrottle, RegistrationDailyThrottle, RegistrationPlatformThrottle,
    ]
