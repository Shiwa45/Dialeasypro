"""
The AI call summary pipeline: recording → audio Gemini can read → transcript
→ summary.

What was wrong:
  * .amr / .3gp recordings were refused, and .m4a / .mp4 (the app's own
    microphone recordings, Samsung's recorder) were sent labelled
    "audio/aac" although they are MP4 containers — most phones' recordings
    could never be summarised. They are now converted to MP3 (Cloudinary
    delivers MP3 on request; ffmpeg otherwise).
  * Nothing showed that a recording was waiting, or why: no summary row
    existed until analysis finished, and a missing GEMINI_API_KEY left every
    recording "pending" with no message anywhere.
  * A recording with no speech, or an unreadable file, was retried three
    times — three more paid requests that fail the same way.
  * "Re-transcribe" did nothing for a call already transcribed.
"""
import io
import shutil
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from django.db import connection
from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.ai import tasks, views as ai_views
from apps.ai.constants import InsightStatus
from apps.ai.models import CallInsight
from apps.ai.services import audio, transcription
from apps.authentication.models import Agent
from apps.calls.models import CallLog, CallRecording

pytestmark = pytest.mark.django_db

CLOUD = "https://res.cloudinary.com/demo/video/upload/v1/call_recordings/crm/call_x"


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(email="adm@ai.l", name="Adm", password="Pw@12345678")


@pytest.fixture
def rec(admin):
    call = CallLog.objects.create(agent=admin, phone_number="+919812300001", is_connected=True,
                                  duration_seconds=40)
    return CallRecording.objects.create(call=call, cloud_url=CLOUD + ".mp3", format="mp3",
                                        duration_seconds=40)


def _resp(content=b"ID3audio", status=200):
    r = MagicMock()
    r.status_code = status
    r.content = content
    return r


# ============================================================
# Audio Gemini can read
# ============================================================

def test_mp3_is_sent_as_it_is(rec):
    with patch("apps.ai.services.audio.requests.get", return_value=_resp()) as get:
        data, mime = audio.prepare(rec)
    assert mime == "audio/mp3" and data == b"ID3audio"
    get.assert_called_once_with(CLOUD + ".mp3", timeout=audio.FETCH_TIMEOUT)


@pytest.mark.parametrize("fmt", ["m4a", "mp4", "amr", "3gp"])
def test_other_formats_are_fetched_from_cloudinary_as_mp3(rec, fmt):
    rec.cloud_url = f"{CLOUD}.{fmt}"
    rec.format = fmt
    with patch("apps.ai.services.audio.requests.get", return_value=_resp()) as get:
        data, mime = audio.prepare(rec)
    assert mime == "audio/mp3"
    get.assert_called_once_with(CLOUD + ".mp3", timeout=audio.FETCH_TIMEOUT)


def test_without_cloudinary_or_ffmpeg_the_reason_is_given(rec):
    rec.cloud_url = "https://media.example.com/call.amr"
    rec.format = "amr"
    with patch("apps.ai.services.audio.requests.get", return_value=_resp(b"#!AMR...")), \
            patch("apps.ai.services.audio.ffmpeg_binary", return_value=None):
        with pytest.raises(audio.AudioError, match="ffmpeg is not installed"):
            audio.prepare(rec)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_ffmpeg_converts_a_real_m4a_to_mp3(tmp_path):
    src = tmp_path / "tone.m4a"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-c:a", "aac", str(src)], check=True)
    out = audio.to_mp3(src.read_bytes(), "m4a")
    assert out[:3] == b"ID3" or out[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")


# ============================================================
# Pipeline states
# ============================================================

@pytest.fixture
def ai_on():
    with patch("apps.ai.tasks._tenant_has", return_value=True), \
            patch("apps.ai.tasks.analyse_call.delay") as analyse:
        yield analyse


def _run(rec, **kw):
    return tasks.transcribe_call.run(connection.schema_name, str(rec.call_id), **kw)


@override_settings(GEMINI_API_KEY="")
def test_a_missing_api_key_is_shown_on_the_summary(rec, ai_on):
    assert _run(rec) == {"skipped": "no_api_key_configured"}
    insight = CallInsight.objects.get(call_id=rec.call_id)
    assert insight.status == InsightStatus.PENDING and "GEMINI_API_KEY" in insight.error


@override_settings(GEMINI_API_KEY="k")
def test_a_call_with_no_speech_is_skipped_not_retried(rec, ai_on):
    with patch("apps.ai.services.transcription.transcribe", side_effect=transcription.NoSpeech("no speech")):
        result = _run(rec)
    assert result["skipped"] == "not_transcribable"
    rec.refresh_from_db()
    assert rec.transcript_status == "failed"
    assert CallInsight.objects.get(call_id=rec.call_id).status == InsightStatus.SKIPPED


@override_settings(GEMINI_API_KEY="k")
def test_an_unreadable_file_fails_with_its_reason_not_retried(rec, ai_on):
    with patch("apps.ai.services.transcription.transcribe",
               side_effect=audio.AudioError("Could not convert")):
        result = _run(rec)
    assert result["skipped"] == "not_transcribable"
    insight = CallInsight.objects.get(call_id=rec.call_id)
    assert insight.status == InsightStatus.FAILED and "Could not convert" in insight.error


@override_settings(GEMINI_API_KEY="k")
def test_transcript_then_analysis(rec, ai_on):
    with patch("apps.ai.services.transcription.transcribe",
               return_value={"text": "Agent: hello", "language": "", "provider": "gemini"}):
        assert _run(rec)["transcribed"] is True
    rec.refresh_from_db()
    assert rec.transcript == "Agent: hello" and rec.transcript_status == "done"
    ai_on.assert_called_once()


@override_settings(GEMINI_API_KEY="k")
def test_force_transcribes_again(rec, ai_on):
    rec.transcript, rec.transcript_status = "old", "done"
    rec.save()
    with patch("apps.ai.services.transcription.transcribe",
               return_value={"text": "new", "language": "", "provider": "g"}) as t:
        assert _run(rec)["skipped"] == "already_transcribed"
        t.assert_not_called()
        _run(rec, force=True)
    rec.refresh_from_db()
    assert rec.transcript == "new"


@override_settings(GEMINI_API_KEY="k")
def test_no_speech_reply_from_gemini_is_recognised(rec):
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(
        text="NO_SPEECH", prompt_feedback=None,
        candidates=[MagicMock(finish_reason="STOP")],
    )
    with patch("apps.ai.services.audio.prepare", return_value=(b"x", "audio/mp3")), \
            patch("apps.ai.services.transcription.get_client", return_value=client):
        with pytest.raises(transcription.NoSpeech):
            transcription.transcribe(rec)


# ============================================================
# Views
# ============================================================

def _call(view, method, user, data=None, **kw):
    req = getattr(APIRequestFactory(), method)("/x/", data or {}, format="json")
    force_authenticate(req, user=user)
    req.has_feature = lambda k: True
    r = view.as_view()(req, **kw)
    r.render()
    return r


def test_retranscribe_forces_a_new_transcript(admin, rec):
    with patch("apps.ai.views.transcribe_call.delay") as delay:
        r = _call(ai_views.CallTranscribeView, "post", admin, pk=rec.call_id)
    assert r.status_code == 202, r.data
    assert delay.call_args.kwargs.get("force") is True


@override_settings(GEMINI_API_KEY="")
def test_usage_says_whether_gemini_is_configured(admin, rec):
    r = _call(ai_views.AIUsageView, "get", admin)
    assert r.status_code == 200, r.data
    assert r.data["gemini_configured"] is False and r.data["recordings_waiting"] == 1


def test_reanalyse_without_a_transcript_transcribes_first(admin, rec):
    # A transcript that failed (retired model) used to leave Re-analyse stuck
    # on a 400 — the website has no Transcribe button to get past it.
    with patch("apps.ai.views.transcribe_call.delay") as transcribe, \
         patch("apps.ai.views.analyse_call.delay") as analyse:
        r = _call(ai_views.CallAnalyseView, "post", admin, pk=rec.call_id)
    assert r.status_code == 202, r.data
    assert transcribe.call_args.kwargs.get("force") is True
    analyse.assert_not_called()  # the transcription task queues it when done


def test_reanalyse_with_a_transcript_analyses_straight_away(admin, rec):
    rec.transcript = "Agent: Hello. Customer: Hi."
    rec.save(update_fields=["transcript"])
    with patch("apps.ai.views.transcribe_call.delay") as transcribe, \
         patch("apps.ai.views.analyse_call.delay") as analyse:
        r = _call(ai_views.CallAnalyseView, "post", admin, pk=rec.call_id)
    assert r.status_code == 202, r.data
    analyse.assert_called_once()
    transcribe.assert_not_called()
