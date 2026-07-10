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

    class Meta:
        model = CallInsight
        fields = [
            "id", "call", "status", "error",
            "summary", "sentiment", "sentiment_score",
            "key_points", "objections", "next_action",
            "suggested_disposition", "suggested_disposition_name",
            "suggested_disposition_slug", "coaching_notes",
            "model", "input_tokens", "output_tokens", "generated_at",
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
