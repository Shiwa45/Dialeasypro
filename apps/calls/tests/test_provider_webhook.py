"""
Call-provider callbacks (LOW-4).

int(payload["Duration"]) raised on a blank or decimal duration — a call that
never connected sends "" — and the error was swallowed behind a 200, so the
call's outcome was never recorded. Knowlarity had an empty handler that
answered 200 and did nothing.
"""
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory

from apps.authentication.models import Agent
from apps.calls.models import CallLog
from apps.calls.views import CallProviderWebhookView

pytestmark = pytest.mark.django_db


@pytest.fixture
def call():
    agent = Agent.objects.create_agent(email="a@x.com", name="A", password="Pw@12345678")
    return CallLog.objects.create(agent=agent, phone_number="+919812300001",
                                  provider="exotel", provider_call_id="CA123")


def _post(provider, payload):
    request = APIRequestFactory().post(f"/api/v1/calls/webhook/{provider}/", payload, format="json")
    return CallProviderWebhookView.as_view()(request, provider=provider)


@pytest.mark.parametrize("duration,expected", [("", 0), ("12.0", 12), (None, 0), ("45", 45)])
def test_the_call_outcome_is_recorded_whatever_the_duration_looks_like(call, duration, expected):
    payload = {"CallSid": "CA123", "Status": "no-answer"}
    if duration is not None:
        payload["Duration"] = duration

    with patch("apps.calls.tasks.download_call_recording.apply_async"):
        assert _post("exotel", payload).status_code == 200

    call.refresh_from_db()
    assert call.duration_seconds == expected
    assert call.provider_meta.get("Status") == "no-answer", "the event was dropped"


def test_an_unsupported_provider_is_told_so():
    assert _post("knowlarity", {"anything": 1}).status_code == 400
