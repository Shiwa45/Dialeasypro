"""
Recording links must point into the company's own Cloudinary (APP-H1).

Older app builds uploaded call recordings to a Cloudinary account an agent
typed into the phone's voice-notes settings, then linked it here.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.calls.models import CallLog, CallRecording
from apps.calls.views import CallRecordingUploadView

pytestmark = pytest.mark.django_db


@pytest.fixture
def call():
    agent = Agent.objects.create_agent(email="a@x.com", name="A", password="Pw@12345678")
    return agent, CallLog.objects.create(agent=agent, phone_number="+919812300001")


def _link(agent, call, url):
    request = APIRequestFactory().post(f"/api/v1/calls/{call.pk}/recording/", {"cloud_url": url}, format="json")
    force_authenticate(request, user=agent)
    request.has_feature = lambda key: True
    return CallRecordingUploadView.as_view()(request, pk=call.pk)


@override_settings(CLOUDINARY_CLOUD_NAME="dialeasy-prod")
@pytest.mark.parametrize("url", [
    "https://res.cloudinary.com/some-agents-account/video/upload/v1/rec.m4a",
    "https://evil.example.com/dialeasy-prod/rec.m4a",
    "http://res.cloudinary.com/dialeasy-prod/video/upload/rec.m4a",
])
def test_links_outside_our_account_are_refused(call, url):
    agent, c = call
    assert _link(agent, c, url).status_code == 400
    assert not CallRecording.objects.filter(call=c).exists()


@override_settings(CLOUDINARY_CLOUD_NAME="dialeasy-prod")
def test_a_link_into_our_account_is_accepted(call):
    agent, c = call
    from unittest.mock import patch

    with patch("apps.calls.views._queue_ai_pipeline"):
        response = _link(agent, c, "https://res.cloudinary.com/dialeasy-prod/video/upload/v1/rec.m4a")
    assert response.status_code == 201
