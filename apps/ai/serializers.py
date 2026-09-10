"""
TeleCRM Backend — apps/ai/serializers.py

Every field is read-only. An insight is the model's output; a client that could
edit it would be editing the audit trail of what the model actually said.
"""
from rest_framework import serializers

from apps.ai.models import CallInsight


class CallInsightSerializer(serializers.ModelSerializer):
    suggested_disposition_name = serializers.CharField(
        source="suggested_disposition.name", read_only=True, default=None,
    )
    suggested_disposition_slug = serializers.CharField(
        source="suggested_disposition.slug", read_only=True, default=None,
    )

    # Who made the call, to whom, when, and for how long.
    #
    # The review queue is a manager triaging other people's calls, and none of
    # this reached the client: a row could say a call went badly without saying
    # whose it was. InsightListView already select_related()s call, call__agent
    # and call__lead, so the joins were being paid for and then discarded.
    agent = serializers.IntegerField(source="call.agent_id", read_only=True, default=None)
    agent_name = serializers.CharField(source="call.agent.name", read_only=True, default=None)
    lead = serializers.IntegerField(source="call.lead_id", read_only=True, default=None)
    lead_name = serializers.CharField(source="call.lead.name", read_only=True, default=None)
    phone_number = serializers.CharField(source="call.phone_number", read_only=True, default="")
    direction = serializers.CharField(source="call.direction", read_only=True, default="")
    call_started_at = serializers.DateTimeField(source="call.started_at", read_only=True, default=None)
    duration_seconds = serializers.IntegerField(
        source="call.duration_seconds", read_only=True, default=0,
    )

    class Meta:
        model = CallInsight
        fields = [
            "id", "call", "status", "error",
            "summary", "sentiment", "sentiment_score",
            "key_points", "objections", "next_action",
            "suggested_disposition", "suggested_disposition_name",
            "suggested_disposition_slug", "coaching_notes",
            "model", "input_tokens", "output_tokens", "generated_at",
            "agent", "agent_name", "lead", "lead_name", "phone_number",
            "direction", "call_started_at", "duration_seconds",
        ]
        read_only_fields = fields


class TranscriptSerializer(serializers.Serializer):
    """The transcript half of the pipeline, read off calls.CallRecording."""

    call = serializers.UUIDField(source="call_id", read_only=True)
    transcript = serializers.CharField(read_only=True)
    transcript_status = serializers.CharField(read_only=True)
    transcript_language = serializers.CharField(read_only=True)
    transcript_provider = serializers.CharField(read_only=True)
    transcript_error = serializers.CharField(read_only=True)
    transcribed_at = serializers.DateTimeField(read_only=True)
    duration_seconds = serializers.IntegerField(read_only=True)
