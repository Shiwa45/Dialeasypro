"""
The phone's own call recording replaces the app's microphone fallback.

Live data showed the fault: three of eight recorded calls carried the app's
microphone recording — 0.2 to 0.3 seconds of audio each — instead of the
phone's recording of the call. Once a call had any recording, every later
upload was refused as "already uploaded", so the real file, found a minute
later, could never take its place; and a fraction-of-a-second microphone file
was accepted as the call's recording.
"""
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.ai.models import CallInsight
from apps.authentication.models import Agent
from apps.calls.models import CallLog, CallRecording
from apps.calls.views import CallRecordingUploadView

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup():
    agent = Agent.objects.create_agent(email="a@r.l", name="A", password="Pw@12345678")
    call = CallLog.objects.create(agent=agent, phone_number="+919812300001", is_connected=True,
                                  duration_seconds=35)
    return agent, call


def _upload(agent, call, matched_by, *, name="x.mp3", duration=18.2):
    stored = {
        "url": f"https://res.cloudinary.com/demo/video/upload/v1/call_{call.pk}.{name.rsplit('.', 1)[1]}",
        "public_id": f"call_{call.pk}", "bytes": 5000, "duration": int(round(duration or 0)),
        "duration_exact": duration, "format": name.rsplit(".", 1)[1],
    }
    request = APIRequestFactory().post(
        f"/api/v1/calls/{call.pk}/recording/",
        {"file": SimpleUploadedFile(name, b"\x00" * 5000, content_type="audio/mpeg"),
         "matched_by": matched_by, "source_filename": name},
        format="multipart",
    )
    force_authenticate(request, user=agent)
    request.has_feature = lambda key: True
    with patch("apps.core.cloudinary_utils.upload_call_recording", return_value=stored), \
            patch("apps.core.cloudinary_utils.delete_call_recording") as deleted, \
            patch("apps.calls.views._queue_ai_pipeline") as queued:
        response = CallRecordingUploadView.as_view()(request, pk=call.pk)
    response.render()
    return response, queued, deleted


def test_the_phones_recording_replaces_the_microphone_fallback(setup):
    agent, call = setup
    r, _, _ = _upload(agent, call, "mic_fallback", name="mic_call_1.m4a", duration=30.0)
    assert r.status_code == 201
    rec = CallRecording.objects.get(call=call)
    rec.transcript, rec.transcript_status = "agent only", "done"
    rec.save()
    CallInsight.objects.create(call=call, status="done", summary="old")

    r, queued, _ = _upload(agent, call, "filename_number", name="+919812300001-2610141413.mp3")
    assert r.status_code == 201, r.data
    rec.refresh_from_db()
    assert rec.matched_by == "filename_number" and rec.format == "mp3"
    assert rec.transcript == "" and rec.transcript_status == "pending"
    assert not CallInsight.objects.filter(call=call).exists()
    assert queued.call_args.kwargs == {"force": True}


def test_a_worse_match_never_replaces_a_better_one(setup):
    agent, call = setup
    _upload(agent, call, "filename_number")
    r, queued, _ = _upload(agent, call, "mic_fallback", name="mic.m4a", duration=30.0)
    assert r.status_code == 200 and r.data["already_uploaded"] is True
    assert CallRecording.objects.get(call=call).matched_by == "filename_number"
    queued.assert_not_called()


def test_an_empty_microphone_recording_is_refused(setup):
    agent, call = setup
    r, queued, deleted = _upload(agent, call, "mic_fallback", name="mic.m4a", duration=0.21)
    assert r.status_code == 422 and r.data["error"] == "recording_empty"
    assert not CallRecording.objects.filter(call=call).exists()
    deleted.assert_called_once()
    queued.assert_not_called()


def test_the_measured_length_is_stored(setup):
    agent, call = setup
    _upload(agent, call, "filename_number", duration=18.6)
    assert CallRecording.objects.get(call=call).duration_seconds == 19
