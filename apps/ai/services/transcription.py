"""
TeleCRM Backend — apps/ai/services/transcription.py

Speech-to-text for call recordings.

Claude has no audio input, so transcription is the one part of the AI suite
that necessarily talks to a different vendor. Rather than hard-wire one, this
speaks the OpenAI `/v1/audio/transcriptions` multipart shape, which is what
OpenAI Whisper, Groq, Fireworks, and self-hosted `faster-whisper-server` all
expose. Point the three settings at whichever one you run:

    AI_TRANSCRIPTION_URL      https://api.openai.com/v1/audio/transcriptions
    AI_TRANSCRIPTION_API_KEY  sk-...
    AI_TRANSCRIPTION_MODEL    whisper-1

Leave AI_TRANSCRIPTION_URL empty and transcription is simply off — every
recording stays at `transcript_status="pending"` and no insight is generated.
Indian calls are code-switched Hindi/English, so we let the model auto-detect
the language rather than forcing `language=en`, which mangles Hinglish.
"""
import logging
import os

import requests
from django.conf import settings

from apps.ai.constants import MAX_RECORDING_SECONDS

logger = logging.getLogger(__name__)

# Whisper-family APIs reject uploads over 25 MB.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
FETCH_TIMEOUT = 60
TRANSCRIBE_TIMEOUT = 300


class TranscriptionError(Exception):
    """Raised for any failure that should mark the recording as failed."""


class TranscriptionUnavailable(TranscriptionError):
    """No ASR provider is configured — not the tenant's fault, don't mark failed."""


def is_enabled() -> bool:
    return bool(getattr(settings, "AI_TRANSCRIPTION_URL", ""))


def _audio_bytes(recording) -> tuple[bytes, str]:
    """
    Pull the recording's audio into memory, returning (bytes, filename).

    Recordings live in one of three places depending on how the tenant is set
    up: Cloudinary (the norm), a local media volume (Cloudinary unconfigured),
    or a Django storage backend (`file`). Try them in that order.
    """
    if recording.cloud_url:
        resp = requests.get(recording.cloud_url, timeout=FETCH_TIMEOUT)
        if resp.status_code != 200:
            raise TranscriptionError(
                f"Could not fetch recording audio: HTTP {resp.status_code}"
            )
        data = resp.content
        name = os.path.basename(recording.cloud_url.split("?", 1)[0]) or "call.mp3"
    elif recording.file:
        with recording.file.open("rb") as fh:
            data = fh.read()
        name = os.path.basename(recording.file.name)
    else:
        raise TranscriptionError("Recording has no audio file.")

    if not data:
        raise TranscriptionError("Recording audio is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise TranscriptionError(
            f"Recording is {len(data) // (1024 * 1024)} MB; the transcription "
            f"API accepts at most {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )

    # Whisper-family APIs sniff the codec from the filename extension.
    if "." not in name:
        name = f"{name}.{recording.format or 'mp3'}"
    return data, name


def transcribe(recording) -> dict:
    """
    Transcribe one `calls.CallRecording`.

    Returns {"text": str, "language": str, "provider": str}.
    Raises TranscriptionUnavailable when no provider is configured, and
    TranscriptionError for anything else.
    """
    url = getattr(settings, "AI_TRANSCRIPTION_URL", "")
    if not url:
        raise TranscriptionUnavailable("AI_TRANSCRIPTION_URL is not set.")

    if recording.duration_seconds and recording.duration_seconds > MAX_RECORDING_SECONDS:
        raise TranscriptionError(
            f"Recording is {recording.duration_seconds}s; refusing to transcribe "
            f"anything over {MAX_RECORDING_SECONDS}s."
        )

    model = getattr(settings, "AI_TRANSCRIPTION_MODEL", "whisper-1")
    api_key = getattr(settings, "AI_TRANSCRIPTION_API_KEY", "")

    data, filename = _audio_bytes(recording)

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    resp = requests.post(
        url,
        headers=headers,
        files={"file": (filename, data)},
        data={"model": model, "response_format": "verbose_json"},
        timeout=TRANSCRIBE_TIMEOUT,
    )
    if resp.status_code != 200:
        raise TranscriptionError(
            f"Transcription API returned HTTP {resp.status_code}: {resp.text[:300]}"
        )

    try:
        payload = resp.json()
    except ValueError:
        # Some self-hosted servers ignore response_format and return plain text.
        payload = {"text": resp.text}

    text = (payload.get("text") or "").strip()
    if not text:
        raise TranscriptionError("Transcription API returned no text.")

    return {
        "text": text,
        "language": (payload.get("language") or "")[:20],
        "provider": model[:60],
    }
