"""
AI call summaries are made on request, not for every call.

Summarising every uploaded recording spent AI credits on calls nobody read.
Now:
  * uploading a recording spends nothing (unless AI_AUTO_SUMMARISE is on);
  * AI Call Summary lists every connected call with a recording, summarised
    or not;
  * "Summarise" makes the summary for that one call: transcribe if needed,
    then summarise;
  * a second click, or a call already summarised, costs nothing;
  * making a summary again is for managers and admins.
"""
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.ai.constants import InsightStatus
from apps.ai.models import CallInsight
from apps.ai.views import CallSummariseView, RecordedCallListView
from apps.authentication.models import Agent
from apps.calls.models import CallLog, CallRecording
from apps.calls.views import CallRecordingUploadView
from apps.core.constants import AgentRole

pytestmark = pytest.mark.django_db

CLOUD = "https://res.cloudinary.com/demo/video/upload/v1/call_recordings/crm/call_"
AI_ON = override_settings(GEMINI_API_KEY="test-key")


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="asha@s.l", name="Asha", password="Pw@12345678")


@pytest.fixture
def ravi():
    return Agent.objects.create_agent(email="ravi@s.l", name="Ravi", password="Pw@12345678")


@pytest.fixture
def manager():
    return Agent.objects.create_agent(email="m@s.l", name="Mona", password="Pw@12345678",
                                      role=AgentRole.MANAGER)


def _call(agent, *, connected=True, recorded=True, transcript=""):
    call = CallLog.objects.create(agent=agent, phone_number="+919812300001",
                                  is_connected=connected, duration_seconds=40 if connected else 0)
    if recorded:
        CallRecording.objects.create(
            call=call, cloud_url=f"{CLOUD}{call.pk}.mp3", format="mp3", duration_seconds=40,
            transcript=transcript, transcript_status="done" if transcript else "pending",
        )
    return call


def _req(method, user, data=None, query="", features=True):
    request = getattr(APIRequestFactory(), method)(f"/x/{query}", data or {}, format="json")
    force_authenticate(request, user=user)
    request.has_feature = (lambda key: True) if features is True else features
    return request


def _summarise(user, call, data=None, features=True):
    with patch("apps.ai.views.transcribe_call.delay") as transcribe, \
            patch("apps.ai.views.analyse_call.delay") as analyse:
        response = CallSummariseView.as_view()(_req("post", user, data, features=features), pk=call.pk)
    return response, transcribe, analyse


def _list(user, query=""):
    return RecordedCallListView.as_view()(_req("get", user, query=query)).data


# ============================================================
# Upload spends nothing
# ============================================================

def _upload(agent, call):
    stored = {"url": f"{CLOUD}{call.pk}.mp3", "public_id": f"call_{call.pk}", "bytes": 5000,
              "duration": 30, "duration_exact": 30.0, "format": "mp3"}
    request = APIRequestFactory().post(
        f"/api/v1/calls/{call.pk}/recording/",
        {"file": SimpleUploadedFile("x.mp3", b"\x00" * 5000, content_type="audio/mpeg"),
         "matched_by": "filename_number"},
        format="multipart",
    )
    force_authenticate(request, user=agent)
    request.has_feature = lambda key: True
    with patch("apps.core.cloudinary_utils.upload_call_recording", return_value=stored), \
            patch("apps.ai.tasks.transcribe_call.delay") as transcribe:
        response = CallRecordingUploadView.as_view()(request, pk=call.pk)
    return response, transcribe


def test_uploading_a_recording_no_longer_summarises_it(asha):
    call = _call(asha, recorded=False)
    response, transcribe = _upload(asha, call)
    assert response.status_code == 201
    transcribe.assert_not_called()
    assert not CallInsight.objects.exists()


@override_settings(AI_AUTO_SUMMARISE=True)
def test_the_old_automatic_behaviour_can_be_switched_back_on(asha):
    call = _call(asha, recorded=False)
    _, transcribe = _upload(asha, call)
    transcribe.assert_called_once()


# ============================================================
# The list
# ============================================================

def test_lists_every_connected_recorded_call_summarised_or_not(asha):
    plain = _call(asha)
    summarised = _call(asha)
    CallInsight.objects.create(call=summarised, status=InsightStatus.DONE, summary="Asked for a quote",
                               sentiment="positive")
    _call(asha, connected=False)          # not answered
    _call(asha, recorded=False)           # no recording

    rows = _list(asha)["results"]
    assert {r["call"] for r in rows} == {str(plain.pk), str(summarised.pk)}
    by_id = {r["call"]: r for r in rows}
    assert by_id[str(plain.pk)]["insight"] is None
    assert by_id[str(plain.pk)]["recording_url"].endswith(".mp3")
    assert by_id[str(summarised.pk)]["insight"]["summary"] == "Asked for a quote"

    assert [r["call"] for r in _list(asha, "?summary=none")["results"]] == [str(plain.pk)]
    assert [r["call"] for r in _list(asha, "?summary=done")["results"]] == [str(summarised.pk)]
    assert [r["call"] for r in _list(asha, "?sentiment=positive")["results"]] == [str(summarised.pk)]


def test_agents_see_only_their_own_calls(asha, ravi, manager):
    _call(asha)
    _call(ravi)
    assert _list(asha)["count"] == 1
    assert _list(manager)["count"] == 2


# ============================================================
# Summarise one call
# ============================================================

@AI_ON
def test_summarise_transcribes_first_when_there_is_no_transcript(asha):
    call = _call(asha)
    r, transcribe, analyse = _summarise(asha, call)
    assert r.status_code == 202 and r.data["transcribing"] is True
    transcribe.assert_called_once()
    analyse.assert_not_called()
    assert CallInsight.objects.get(call=call).status == InsightStatus.PROCESSING


@AI_ON
def test_summarise_uses_an_existing_transcript(asha):
    call = _call(asha, transcript="Customer: what is the price of the 2BHK? " * 5)
    r, transcribe, analyse = _summarise(asha, call)
    assert r.status_code == 202 and r.data["transcribing"] is False
    analyse.assert_called_once()
    transcribe.assert_not_called()


@AI_ON
def test_a_second_click_does_not_pay_twice(asha):
    call = _call(asha)
    _summarise(asha, call)
    r, transcribe, analyse = _summarise(asha, call)
    assert r.status_code == 202 and r.data["already_running"] is True
    transcribe.assert_not_called()
    analyse.assert_not_called()


@AI_ON
def test_a_finished_summary_is_returned_not_made_again(asha, manager):
    call = _call(asha)
    CallInsight.objects.create(call=call, status=InsightStatus.DONE, summary="Done already")
    r, transcribe, analyse = _summarise(asha, call)
    assert r.status_code == 200 and r.data["already_done"] is True
    transcribe.assert_not_called()
    analyse.assert_not_called()

    # Making it again: managers yes, agents no.
    r, _, _ = _summarise(asha, call, {"force": True})
    assert r.status_code == 403
    r, transcribe, _ = _summarise(manager, call, {"force": True})
    assert r.status_code == 202
    transcribe.assert_called_once()


@AI_ON
def test_calls_that_cannot_be_summarised_are_refused(asha, ravi):
    r, transcribe, _ = _summarise(asha, _call(asha, connected=False))
    assert r.status_code == 400
    r, _, _ = _summarise(asha, _call(asha, recorded=False))
    assert r.status_code == 400
    r, _, _ = _summarise(asha, _call(ravi))       # someone else's call
    assert r.status_code == 404
    no_transcription = lambda key: key != "ai_call_transcription"  # noqa: E731
    r, transcribe, _ = _summarise(asha, _call(asha), features=no_transcription)
    assert r.status_code == 402
    transcribe.assert_not_called()


def test_without_an_api_key_nothing_is_queued(asha):
    with override_settings(GEMINI_API_KEY=""):
        r, transcribe, analyse = _summarise(asha, _call(asha))
    assert r.status_code == 503
    transcribe.assert_not_called()
