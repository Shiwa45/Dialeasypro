"""
TeleCRM Backend — apps/ai/services/transcription.py

Speech-to-text for call recordings, via Gemini's native audio input.

Indian sales calls are code-switched Hindi/English, so we ask for the spoken
words transliterated as heard rather than translated into English — translating
at this stage would destroy the phrasing the insights step needs to read tone
and objections.
"""
import logging
import os

import requests

from apps.ai.constants import MAX_RECORDING_SECONDS
from apps.ai.services.gemini import (
    INLINE_AUDIO_LIMIT,
    GeminiError,
    GeminiUnavailable,
    get_client,
    is_enabled,
    mime_for,
    raise_if_blocked,
    transcribe_model_name,
)

logger = logging.getLogger(__name__)

FETCH_TIMEOUT = 60

# Gemini's own hard cap is far higher, but a call recording past this is not a
# call recording.
MAX_AUDIO_BYTES = 100 * 1024 * 1024

PROMPT = """\
Transcribe this recording of a sales phone call between an agent and a lead.

- Write exactly what is said. Do not translate. If the speakers mix Hindi and \
English, transliterate the Hindi into Latin script as spoken.
- Label each turn `Agent:` or `Lead:` when you can tell them apart. Use \
`Speaker 1:` / `Speaker 2:` when you cannot.
- Do not summarise, comment, or add anything that was not said.
- If the audio contains no intelligible speech, reply with exactly: NO_SPEECH
"""

# Re-exported so callers can keep catching the same names.
TranscriptionError = GeminiError
TranscriptionUnavailable = GeminiUnavailable

__all__ = [
    "TranscriptionError",
    "TranscriptionUnavailable",
    "is_enabled",
    "transcribe",
]


def _audio_bytes(recording) -> bytes:
    """
    Pull the recording's audio into memory.

    Recordings live in one of three places depending on tenant setup:
    Cloudinary (the norm), a local media volume (Cloudinary unconfigured), or a
    Django storage backend. Try them in that order.
    """
    if recording.cloud_url:
        resp = requests.get(recording.cloud_url, timeout=FETCH_TIMEOUT)
        if resp.status_code != 200:
            raise GeminiError(f"Could not fetch recording audio: HTTP {resp.status_code}")
        data = resp.content
    elif recording.file:
        with recording.file.open("rb") as fh:
            data = fh.read()
    else:
        raise GeminiError("Recording has no audio file.")

    if not data:
        raise GeminiError("Recording audio is empty.")
    if len(data) > MAX_AUDIO_BYTES:
        raise GeminiError(f"Recording is {len(data) // (1024 * 1024)} MB; refusing to transcribe.")
    return data


def _audio_part(client, data: bytes, mime: str):
    """
    Inline the audio when it's small, upload it when it isn't.

    Gemini caps a whole request at 20 MB, so anything near that has to go
    through the file API and be referenced by handle.
    """
    from google.genai import types

    if len(data) <= INLINE_AUDIO_LIMIT:
        return types.Part.from_bytes(data=data, mime_type=mime), None

    import io

    uploaded = client.files.upload(
        file=io.BytesIO(data),
        config=types.UploadFileConfig(mime_type=mime),
    )
    return uploaded, uploaded


def transcribe(recording) -> dict:
    """
    Transcribe one `calls.CallRecording`.

    Returns {"text": str, "language": str, "provider": str}.
    Raises TranscriptionUnavailable when unconfigured, TranscriptionError
    otherwise.
    """
    if not is_enabled():
        raise GeminiUnavailable("GEMINI_API_KEY is not set.")

    if recording.duration_seconds and recording.duration_seconds > MAX_RECORDING_SECONDS:
        raise GeminiError(
            f"Recording is {recording.duration_seconds}s; refusing to transcribe "
            f"anything over {MAX_RECORDING_SECONDS}s."
        )

    # Prefer the stored format; fall back to the URL's extension.
    fmt = recording.format
    if not fmt and recording.cloud_url:
        fmt = os.path.splitext(recording.cloud_url.split("?", 1)[0])[1]
    mime = mime_for(fmt)

    client = get_client()
    data = _audio_bytes(recording)
    part, uploaded = _audio_part(client, data, mime)

    model = transcribe_model_name()
    try:
        response = client.models.generate_content(model=model, contents=[part, PROMPT])
        raise_if_blocked(response)
        text = (response.text or "").strip()
    finally:
        # The file API bills storage; don't leave call audio sitting in it.
        if uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except Exception as exc:  # noqa: BLE001 — cleanup must not mask the real error
                logger.warning("Could not delete uploaded audio %s: %s", uploaded.name, exc)

    if not text or text == "NO_SPEECH":
        raise GeminiError("The recording contains no intelligible speech.")

    return {"text": text, "language": "", "provider": model[:60]}
