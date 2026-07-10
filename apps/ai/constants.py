"""
TeleCRM Backend — apps/ai/constants.py
"""


class Sentiment:
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"

    CHOICES = [(POSITIVE, "Positive"), (NEUTRAL, "Neutral"), (NEGATIVE, "Negative")]
    ALL = [POSITIVE, NEUTRAL, NEGATIVE]


class InsightStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"  # nothing to analyse (empty transcript, too short)

    CHOICES = [
        (PENDING, "Pending"), (PROCESSING, "Processing"), (DONE, "Done"),
        (FAILED, "Failed"), (SKIPPED, "Skipped"),
    ]


class TranscriptStatus:
    """Mirrors the choices already declared on calls.CallRecording."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


# A sales call transcript that is shorter than this carries no signal — a
# ring-out, a wrong number, or a two-word "not interested". Don't pay for it.
MIN_TRANSCRIPT_CHARS = 120

# Gemini's context window is far larger, but a single call transcript should
# never come close. Anything past this is a runaway transcription, not a call.
MAX_TRANSCRIPT_CHARS = 200_000

# Recordings longer than this are almost certainly not a single sales call.
MAX_RECORDING_SECONDS = 60 * 60
