"""
TeleCRM Backend — apps/ai/services/insights.py

Turns a call transcript into structured coaching output using Claude.

The model never picks a free-text disposition: it must choose from the
tenant's own active CallDisposition slugs, and we re-validate its choice
against that set before saving. A hallucinated disposition would otherwise
flow straight into the follow-up automation that `auto_followup_hours` drives.
"""
import logging

import anthropic
from django.conf import settings
from pydantic import BaseModel, Field

from apps.ai.constants import MAX_TRANSCRIPT_CHARS, MIN_TRANSCRIPT_CHARS, Sentiment

logger = logging.getLogger(__name__)

MODEL = "claude-opus-4-8"
MAX_TOKENS = 8000

SYSTEM_PROMPT = """\
You are a sales-call analyst for an Indian telecalling CRM. You read a \
transcript of one call between an agent and a lead and return a structured \
assessment of it.

Calls are usually code-switched between Hindi and English. The transcript is \
machine-generated and will contain speech-recognition errors, dropped words, \
and unreliable speaker attribution — read past them rather than quoting them.

Rules:
- `sentiment` describes the *lead's* disposition towards the offer. An agent \
who is upbeat while the lead stonewalls is a negative call.
- `key_points` are facts that would change how the next call goes: budget, \
timeline, decision-maker, competitor, specific requirement. Not pleasantries.
- `objections` are the lead's stated reasons for not buying. Empty list if the \
lead raised none.
- `next_action` is one concrete instruction for the agent, in the imperative.
- `coaching_notes` is candid feedback for the agent, addressed to them. Say \
what to do differently, not what they did well.
- Write in plain English regardless of the language spoken on the call.
- If the transcript is too garbled or too short to support a conclusion, say \
so in `summary` and leave the other fields empty rather than inventing content.
"""


class InsightSchema(BaseModel):
    """The shape Claude must return. Mirrors ai.CallInsight."""

    summary: str = Field(description="Two or three sentences on what was discussed and agreed.")
    sentiment: str = Field(description="One of: positive, neutral, negative.")
    sentiment_score: float = Field(description="-1.0 for hostile, 0.0 for neutral, 1.0 for enthusiastic.")
    key_points: list[str] = Field(description="Facts worth carrying into the next call.")
    objections: list[str] = Field(description="The lead's stated reasons for not buying.")
    next_action: str = Field(description="One concrete instruction for the agent, imperative mood.")
    suggested_disposition: str = Field(description="Exactly one slug from the allowed list, or empty string.")
    coaching_notes: str = Field(description="Candid feedback addressed to the agent.")


class InsightError(Exception):
    """Analysis failed; the call should be marked failed and retried later."""


class InsightUnavailable(InsightError):
    """No Anthropic API key configured — not the tenant's fault."""


class TranscriptTooShort(InsightError):
    """Nothing to analyse. Mark skipped, never retry."""


def is_enabled() -> bool:
    return bool(getattr(settings, "ANTHROPIC_API_KEY", ""))


def _client() -> anthropic.Anthropic:
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        raise InsightUnavailable("ANTHROPIC_API_KEY is not set.")
    return anthropic.Anthropic(api_key=api_key)


def _user_prompt(transcript: str, *, disposition_slugs: list[str], meta: dict) -> str:
    allowed = ", ".join(disposition_slugs) if disposition_slugs else "(none configured)"
    lines = [
        "<call_metadata>",
        f"direction: {meta.get('direction', 'unknown')}",
        f"duration_seconds: {meta.get('duration_seconds', 0)}",
        f"lead_name: {meta.get('lead_name') or 'unknown'}",
        "</call_metadata>",
        "",
        "<allowed_dispositions>",
        allowed,
        "</allowed_dispositions>",
        "",
        "<transcript>",
        transcript,
        "</transcript>",
        "",
        "Analyse this call. `suggested_disposition` must be exactly one slug "
        "from <allowed_dispositions>, or an empty string if none fits.",
    ]
    return "\n".join(lines)


def analyse(transcript: str, *, disposition_slugs: list[str], meta: dict) -> dict:
    """
    Run one transcript through Claude.

    Returns a dict of InsightSchema fields plus `model`, `input_tokens` and
    `output_tokens`. `suggested_disposition` is guaranteed to be either the
    empty string or a member of `disposition_slugs`.
    """
    transcript = (transcript or "").strip()
    if len(transcript) < MIN_TRANSCRIPT_CHARS:
        raise TranscriptTooShort(
            f"Transcript is {len(transcript)} chars; need at least {MIN_TRANSCRIPT_CHARS}."
        )
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        # Truncating a transcript loses the close of the call, which is where
        # the commitment lives. Refuse rather than analyse the wrong half.
        raise InsightError(
            f"Transcript is {len(transcript)} chars, over the "
            f"{MAX_TRANSCRIPT_CHARS} limit. Likely a stuck ASR run."
        )

    client = _client()
    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": _user_prompt(
                    transcript, disposition_slugs=disposition_slugs, meta=meta
                ),
            }],
            output_format=InsightSchema,
        )
    except anthropic.RateLimitError as exc:
        raise InsightError(f"Rate limited by the Claude API: {exc}") from exc
    except anthropic.APIStatusError as exc:
        raise InsightError(f"Claude API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise InsightError(f"Could not reach the Claude API: {exc}") from exc

    if response.stop_reason == "refusal":
        raise InsightError("Claude declined to analyse this transcript.")

    parsed: InsightSchema = response.parsed_output
    if parsed is None:
        raise InsightError("Claude returned no structured output.")

    sentiment = parsed.sentiment.strip().lower()
    if sentiment not in Sentiment.ALL:
        sentiment = Sentiment.NEUTRAL

    disposition = parsed.suggested_disposition.strip()
    if disposition not in disposition_slugs:
        # The model invented a slug. Drop it — a wrong disposition would fire
        # the wrong follow-up automation.
        if disposition:
            logger.warning("Claude suggested unknown disposition %r; discarding.", disposition)
        disposition = ""

    return {
        "summary": parsed.summary.strip(),
        "sentiment": sentiment,
        "sentiment_score": max(-1.0, min(1.0, float(parsed.sentiment_score))),
        "key_points": [p.strip() for p in parsed.key_points if p.strip()],
        "objections": [o.strip() for o in parsed.objections if o.strip()],
        "next_action": parsed.next_action.strip(),
        "suggested_disposition": disposition,
        "coaching_notes": parsed.coaching_notes.strip(),
        "model": response.model,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
