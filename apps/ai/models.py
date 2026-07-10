"""
TeleCRM Backend — apps/ai/models.py

Per-tenant AI artefacts derived from call recordings.

The transcript itself lives on `calls.CallRecording` (it predates this app and
is already serialised to the React client). This app owns the *analysis* of
that transcript, plus the token/second counters the tenant is billed on.
"""
from django.db import models

from apps.ai.constants import InsightStatus, Sentiment
from apps.core.models import TimeStampedModel


class CallInsight(TimeStampedModel):
    """
    Gemini's read of one call: what happened, how it went, what to do next.

    One row per call. Regenerating overwrites in place — an insight is a
    derived view of the transcript, not an audit record.
    """

    call = models.OneToOneField(
        "calls.CallLog",
        on_delete=models.CASCADE,
        related_name="insight",
    )

    status = models.CharField(
        max_length=20,
        choices=InsightStatus.CHOICES,
        default=InsightStatus.PENDING,
        db_index=True,
    )
    error = models.TextField(blank=True, default="")

    # ---- The analysis --------------------------------------
    summary = models.TextField(
        blank=True, default="",
        help_text="Two or three sentences on what was discussed and agreed.",
    )
    sentiment = models.CharField(
        max_length=10, choices=Sentiment.CHOICES, blank=True, default="", db_index=True,
        help_text="The lead's disposition towards the offer, not the agent's tone.",
    )
    sentiment_score = models.FloatField(
        null=True, blank=True,
        help_text="-1.0 (hostile) to 1.0 (enthusiastic).",
    )
    key_points = models.JSONField(
        default=list, blank=True,
        help_text="List of strings: the facts worth carrying into the next call.",
    )
    objections = models.JSONField(
        default=list, blank=True,
        help_text="List of strings: reasons the lead gave for not buying.",
    )
    next_action = models.TextField(
        blank=True, default="",
        help_text="The single most useful thing the agent should do next.",
    )
    suggested_disposition = models.ForeignKey(
        "calls.CallDisposition",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="ai_suggestions",
        help_text="Only ever one of the tenant's own active dispositions.",
    )
    coaching_notes = models.TextField(
        blank=True, default="",
        help_text="Feedback for the agent — what to do differently next time.",
    )

    # ---- Provenance & cost ---------------------------------
    model = models.CharField(max_length=60, blank=True, default="")
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    generated_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "Call Insight"
        verbose_name_plural = "Call Insights"
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["sentiment", "generated_at"]),
            models.Index(fields=["status", "generated_at"]),
        ]

    def __str__(self):
        return f"Insight for call {self.call_id} ({self.status})"
