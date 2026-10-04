"""
Lead webhooks must prove who sent them (HIGH-10).

IndiaMART, Meta Lead Ads and Google Ads checked a signature only when a
secret was configured. With no secret — or no integration at all — any post
to the predictable per-tenant URL created leads. Google's key was never
checked. A delivery now needs one of: a valid provider signature, the
config's webhook token, or (Google) the matching google_key.
"""
import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from django.test import RequestFactory

from apps.core.constants import LeadSource
from apps.integrations.models import LeadSourceConfig
from apps.integrations.views import (
    GenericWebhookView, GoogleAdsWebhookView, IndiaMArtWebhookView,
)
from apps.leads.models import Lead

pytestmark = pytest.mark.django_db

INDIAMART_BODY = {"NAME": "Buyer", "MOBILE": "9812300050"}
GOOGLE_BODY = {"lead_id": "g1", "user_column_data": [], "full_name": "Buyer",
               "phone_number": "9812300051"}


def _post(view, path, body, headers=None, **kwargs):
    raw = json.dumps(body)
    request = RequestFactory().post(path, data=raw, content_type="application/json",
                                    **{f"HTTP_{k.upper().replace('-', '_')}": v
                                       for k, v in (headers or {}).items()})
    return view.as_view()(request, **kwargs)


def _leads():
    return Lead.objects.count()


# ---- IndiaMART ---------------------------------------------------------

def test_an_anonymous_post_creates_nothing():
    LeadSourceConfig.objects.create(source=LeadSource.INDIAMART, is_active=True)

    response = _post(IndiaMArtWebhookView, "/api/v1/integrations/indiamart/", INDIAMART_BODY)

    assert response.status_code == 401
    assert _leads() == 0


def test_the_refusal_is_visible_on_the_integration():
    config = LeadSourceConfig.objects.create(source=LeadSource.INDIAMART, is_active=True)

    _post(IndiaMArtWebhookView, "/api/v1/integrations/indiamart/", INDIAMART_BODY)

    config.refresh_from_db()
    assert "token" in config.error_message


def test_the_url_with_its_token_is_accepted():
    config = LeadSourceConfig.objects.create(source=LeadSource.INDIAMART, is_active=True)

    response = _post(IndiaMArtWebhookView,
                     f"/api/v1/integrations/indiamart/?token={config.webhook_token}", INDIAMART_BODY)

    assert response.status_code == 200
    assert _leads() == 1


def test_another_tenants_or_a_guessed_token_is_refused():
    LeadSourceConfig.objects.create(source=LeadSource.INDIAMART, is_active=True)

    response = _post(IndiaMArtWebhookView, "/api/v1/integrations/indiamart/?token=guess", INDIAMART_BODY)

    assert response.status_code == 401


def test_a_valid_signature_is_enough():
    LeadSourceConfig.objects.create(
        source=LeadSource.INDIAMART, is_active=True, credentials={"webhook_secret": "shh"},
    )
    raw = json.dumps(INDIAMART_BODY).encode()
    signature = hmac.new(b"shh", raw, hashlib.sha256).hexdigest()

    response = _post(IndiaMArtWebhookView, "/api/v1/integrations/indiamart/", INDIAMART_BODY,
                     headers={"X-Im-Signature": signature})

    assert response.status_code == 200


# ---- Google Ads --------------------------------------------------------

def test_google_needs_its_key():
    LeadSourceConfig.objects.create(
        source=LeadSource.GOOGLE_ADS, is_active=True, credentials={"google_key": "gk-123"},
    )

    wrong = _post(GoogleAdsWebhookView, "/api/v1/integrations/google/", {**GOOGLE_BODY, "google_key": "nope"})
    right = _post(GoogleAdsWebhookView, "/api/v1/integrations/google/", {**GOOGLE_BODY, "google_key": "gk-123"})

    assert wrong.status_code == 401
    assert right.status_code == 200


# ---- Generic token URL -------------------------------------------------

def test_the_generic_url_now_uses_its_own_config():
    """Its config was never passed on, so mapping and the on/off switch were ignored."""
    config = LeadSourceConfig.objects.create(source=LeadSource.WEBHOOK, is_active=False)

    response = _post(GenericWebhookView, f"/api/v1/integrations/webhook/{config.webhook_token}/",
                     {"name": "Buyer", "phone": "9812300052"}, token=config.webhook_token)

    assert response.status_code == 403, "a switched-off integration must refuse deliveries"
    assert _leads() == 0


def test_the_generic_url_rejects_an_unknown_token():
    response = _post(GenericWebhookView, "/api/v1/integrations/webhook/nope/",
                     {"name": "Buyer", "phone": "9812300053"}, token="nope")

    assert response.status_code == 401


@pytest.mark.django_db
def test_the_google_key_saved_from_the_crm_is_the_one_checked():
    """
    The Configure screen asked every non-Meta source for an "API key" that no
    webhook reads, so the Google key a tenant typed was stored as `api_key`
    and Google's key check could never pass. It is saved as google_key now.
    """
    from apps.integrations.serializers import LeadSourceConfigSerializer

    config = LeadSourceConfig.objects.create(source=LeadSource.GOOGLE_ADS, is_active=True)
    serializer = LeadSourceConfigSerializer(config, data={"credentials": {"google_key": "gk-typed"}}, partial=True)
    assert serializer.is_valid(), serializer.errors
    serializer.save()

    config.refresh_from_db()
    assert LeadSourceConfigSerializer(config).data["credentials_status"]["has_google_key"] is True
    right = _post(GoogleAdsWebhookView, "/api/v1/integrations/google/", {**GOOGLE_BODY, "google_key": "gk-typed"})
    assert right.status_code == 200
