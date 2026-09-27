"""
The Meta Lead Ads webhook handshake (LOW-7).

With no verify token configured, an empty `hub.verify_token` equalled the
empty expected value and verification passed — anyone could subscribe the
endpoint.
"""
import pytest
from rest_framework.test import APIRequestFactory

from apps.core.constants import LeadSource
from apps.integrations.models import LeadSourceConfig
from apps.integrations.views import MetaLeadAdsWebhookView

pytestmark = pytest.mark.django_db


def _verify(token):
    request = APIRequestFactory().get("/api/v1/integrations/meta/", {
        "hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "42",
    })
    return MetaLeadAdsWebhookView.as_view()(request)


def test_an_empty_token_does_not_pass_when_none_is_configured():
    assert _verify("").status_code == 403


def test_an_empty_token_does_not_pass_with_a_config_but_no_token():
    LeadSourceConfig.objects.create(source=LeadSource.META_FACEBOOK, is_active=True, credentials={})

    assert _verify("").status_code == 403


def test_the_configured_token_passes():
    LeadSourceConfig.objects.create(
        source=LeadSource.META_FACEBOOK, is_active=True, credentials={"verify_token": "s3cret"},
    )

    response = _verify("s3cret")
    assert response.status_code == 200
    assert response.content == b"42"
    assert _verify("wrong").status_code == 403
