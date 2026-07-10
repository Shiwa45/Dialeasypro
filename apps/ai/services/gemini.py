"""
TeleCRM Backend — apps/ai/services/gemini.py

Shared Google Gemini client for the AI Suite.

Gemini takes audio natively, so one provider covers both halves of the
pipeline: transcription (audio → text) and insights (text → structured
analysis). There is no separate speech-to-text vendor.

Config (settings / .env):
    GEMINI_API_KEY              required; the module is dormant without it
    GEMINI_MODEL               default "gemini-2.5-flash"
    GEMINI_TRANSCRIBE_MODEL    default = GEMINI_MODEL
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# The Gemini file API is required past this size; below it, audio rides inline
# in the request. Gemini's own inline ceiling is 20 MB for the whole request,
# so leave headroom for the prompt.
INLINE_AUDIO_LIMIT = 18 * 1024 * 1024

# Container/codec → the MIME type Gemini accepts.
# Deliberately absent: amr and 3gp. Some Android OEM call recorders still emit
# those, and Gemini rejects them — we surface a clear error rather than a 400.
AUDIO_MIME_TYPES = {
    "mp3": "audio/mp3",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
    "aac": "audio/aac",
    "aiff": "audio/aiff",
    # The app's mic fallback records AAC-LC into an .m4a/.mp4 container.
    "m4a": "audio/aac",
    "mp4": "audio/aac",
}

UNSUPPORTED_AUDIO = {"amr", "3gp", "3gpp"}


class GeminiError(Exception):
    """Any Gemini failure the caller should treat as retryable."""


class GeminiUnavailable(GeminiError):
    """No API key configured — a misconfiguration, not a bad recording."""


def is_enabled() -> bool:
    return bool(getattr(settings, "GEMINI_API_KEY", ""))


def get_client():
    """Build a Gemini client. Import is lazy so the web process boots without it."""
    from google import genai

    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise GeminiUnavailable("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=api_key)


def model_name() -> str:
    return getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")


def transcribe_model_name() -> str:
    return getattr(settings, "GEMINI_TRANSCRIBE_MODEL", "") or model_name()


def mime_for(fmt: str) -> str:
    """Resolve a recording's `format` column to a MIME type Gemini accepts."""
    fmt = (fmt or "").lower().lstrip(".")
    if fmt in UNSUPPORTED_AUDIO:
        raise GeminiError(
            f"Gemini cannot read .{fmt} audio. This device's recorder produces a "
            f"format the model does not accept; convert to mp3 or m4a first."
        )
    mime = AUDIO_MIME_TYPES.get(fmt)
    if not mime:
        raise GeminiError(f"Unsupported audio format: .{fmt}")
    return mime


def token_counts(response) -> tuple[int, int]:
    """(input, output) tokens. Gemini omits usage on some error paths."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return 0, 0
    return (
        getattr(usage, "prompt_token_count", 0) or 0,
        getattr(usage, "candidates_token_count", 0) or 0,
    )


def raise_if_blocked(response) -> None:
    """
    Gemini returns HTTP 200 with no candidates when a safety filter fires.
    Reading `.text` or `.parsed` on that response raises something opaque, so
    check first and fail with a message that names the cause.
    """
    feedback = getattr(response, "prompt_feedback", None)
    if feedback is not None and getattr(feedback, "block_reason", None):
        raise GeminiError(f"Gemini blocked the prompt: {feedback.block_reason}")

    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise GeminiError("Gemini returned no candidates.")

    finish = getattr(candidates[0], "finish_reason", None)
    # `STOP` and `MAX_TOKENS` are normal; anything else means the model bailed.
    if finish is not None and str(finish).upper().endswith(("SAFETY", "RECITATION", "BLOCKLIST")):
        raise GeminiError(f"Gemini stopped early: {finish}")
