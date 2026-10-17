"""
TeleCRM Backend — apps/ai/services/transcription.py

Speech-to-text for call recordings, via Gemini's native audio input.

Indian sales calls are code-switched Hindi/English, so we ask for the spoken
words transliterated as heard rather than translated into English — translating
at this stage would destroy the phrasing the insights step needs to read tone
and objections.
"""
import logging

from apps.ai.constants import MAX_RECORDING_SECONDS
from apps.ai.services import audio
from apps.ai.services.gemini import (
    INLINE_AUDIO_LIMIT,
    GeminiError,
    GeminiUnavailable,
    get_client,
    is_enabled,
    raise_if_blocked,
    transcribe_model_name,
)

logger = logging.getLogger(__name__)

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


class NoSpeech(GeminiError):
    """The recording holds no intelligible speech. Retrying won't change that."""


# Failures that are about the recording itself, not about Gemini being busy:
# retrying only burns audio tokens.
PERMANENT_ERRORS = (NoSpeech, audio.AudioError)

__all__ = [
    "NoSpeech",
    "PERMANENT_ERRORS",
    "TranscriptionError",
    "TranscriptionUnavailable",
    "is_enabled",
    "transcribe",
]


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
    Raises TranscriptionUnavailable when unconfigured, NoSpeech / AudioError
    for a recording that can't be transcribed, TranscriptionError otherwise.
    """
    if not is_enabled():
        raise GeminiUnavailable("GEMINI_API_KEY is not set.")

    if recording.duration_seconds and recording.duration_seconds > MAX_RECORDING_SECONDS:
        raise audio.AudioError(
            f"Recording is {recording.duration_seconds}s; refusing to transcribe "
            f"anything over {MAX_RECORDING_SECONDS}s."
        )

    # Converted to MP3 first when the phone wrote a format Gemini can't read
    # (.amr, .3gp, .m4a) — see services/audio.py.
    data, mime = audio.prepare(recording)

    client = get_client()
    part, uploaded = _audio_part(client, data, mime)

    model = transcribe_model_name()
    try:
        try:
            response = client.models.generate_content(model=model, contents=[part, PROMPT])
        except GeminiError:
            raise
        except Exception as exc:  # SDK / transport errors — retryable
            raise GeminiError(f"Gemini request failed: {exc}") from exc
        raise_if_blocked(response)
        text = (response.text or "").strip()
    finally:
        # The file API bills storage; don't leave call audio sitting in it.
        if uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except Exception as exc:  # noqa: BLE001 — cleanup must not mask the real error
                logger.warning("Could not delete uploaded audio %s: %s", uploaded.name, exc)

    if not text or text.strip(" .`'\"").upper() == "NO_SPEECH":
        raise NoSpeech("The recording contains no intelligible speech.")

    return {"text": text, "language": "", "provider": model[:60]}
