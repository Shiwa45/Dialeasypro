"""
The call-recording download refuses a URL that points inward.

`download_call_recording` is fed the RecordingUrl from a provider webhook. It
used to fetch whatever it was given, so an outsider could have the server read
cloud metadata and file it away as a call recording.
"""
from unittest import mock

import pytest
from django.db import connection

from apps.authentication.models import Agent
from apps.calls.models import CallLog, CallRecording
from apps.calls.tasks import download_call_recording
from apps.core import safe_fetch

pytestmark = pytest.mark.django_db


@pytest.fixture
def call():
    agent = Agent.objects.create_agent(email="a@example.com", name="A", password="Pw@12345678")
    return CallLog.objects.create(agent=agent, phone_number="+919812300001", duration_seconds=42)


def test_an_internal_recording_url_is_never_fetched_or_stored(call):
    with mock.patch.object(safe_fetch.socket, "getaddrinfo",
                           return_value=[(2, 1, 6, "", ("169.254.169.254", 80))]), \
         mock.patch.object(safe_fetch.requests, "get") as get:
        download_call_recording.apply(
            args=[connection.schema_name, str(call.id), "http://metadata.internal/latest/"])

    get.assert_not_called()
    assert not CallRecording.objects.filter(call=call).exists()
