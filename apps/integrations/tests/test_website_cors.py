"""
A website form can post to the generic webhook from the visitor's browser.

CORS only allowed the CRM's own domains, so a tenant's website (any other
domain) had every lead refused by the browser before it reached the webhook.
The webhook path — authenticated by the token in its URL, cookie-free — now
accepts any origin; the rest of the API keeps the strict list.
"""
import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from corsheaders.middleware import CorsMiddleware

# Production's CORS: only the CRM's own domains (test settings allow all).
pytestmark = pytest.mark.usefixtures("strict_cors")

SITE = "https://dialsathi.com"
WEBHOOK = "/api/v1/integrations/webhook/8qg5example-token/"


@pytest.fixture
def strict_cors(settings):
    settings.CORS_ALLOW_ALL_ORIGINS = False
    settings.CORS_ALLOWED_ORIGINS = []
    settings.CORS_ALLOWED_ORIGIN_REGEXES = [r"^https://[\w-]+\.easyian\.shop$"]


def _through_cors(request):
    return CorsMiddleware(lambda r: HttpResponse("ok"))(request)


def _preflight(path):
    return RequestFactory().options(
        path,
        HTTP_ORIGIN=SITE,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
    )


def test_a_website_may_preflight_the_webhook():
    r = _through_cors(_preflight(WEBHOOK))

    assert r["Access-Control-Allow-Origin"] == SITE
    assert "POST" in r["Access-Control-Allow-Methods"]
    assert "content-type" in r["Access-Control-Allow-Headers"].lower()


def test_the_post_itself_is_readable_by_the_website():
    request = RequestFactory().post(WEBHOOK, data="{}", content_type="application/json", HTTP_ORIGIN=SITE)

    assert _through_cors(request)["Access-Control-Allow-Origin"] == SITE


def test_the_rest_of_the_api_still_refuses_other_sites():
    for path in ["/api/v1/leads/", "/api/v1/auth/login/", "/api/v1/integrations/configs/"]:
        r = _through_cors(_preflight(path))
        assert "Access-Control-Allow-Origin" not in r, path
