"""
TeleCRM Backend — apps/calls/serializers.py
"""
from rest_framework import serializers
from apps.calls.models import CallDisposition, CallLog, CallRecording


class CallDispositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CallDisposition
        fields = ["id", "name", "slug", "is_positive", "auto_followup_hours"]


class CallRecordingSerializer(serializers.ModelSerializer):
    playback_url = serializers.SerializerMethodField()

    class Meta:
        model = CallRecording
        fields = [
            "id", "duration_seconds", "format", "transcript", "transcript_status",
            "transcript_language", "transcribed_at",
            "playback_url", "source_filename", "matched_by", "uploaded_at",
        ]

    def get_playback_url(self, obj):
        try:
            return obj.get_presigned_url()
        except Exception:
            return None


class CallLogSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source="agent.name", read_only=True)
    lead_name = serializers.CharField(source="lead.name", read_only=True)
    duration_display = serializers.CharField(read_only=True)
    disposition_name = serializers.CharField(source="disposition.name", read_only=True)
    recording = CallRecordingSerializer(read_only=True)

    class Meta:
        model = CallLog
        fields = [
            "id", "agent", "agent_name", "lead", "lead_name",
            "direction", "phone_number", "started_at", "ended_at",
            "duration_seconds", "duration_display", "is_connected",
            "disposition", "disposition_name", "notes",
            "provider", "provider_call_id", "call_cost_paise",
            "recording", "created_at",
        ]
        read_only_fields = ["id", "created_at", "duration_seconds", "is_connected"]


class CallLogCreateSerializer(serializers.ModelSerializer):
    """For manual call entry by agents."""

    class Meta:
        model = CallLog
        fields = [
            "id", "lead", "direction", "phone_number", "started_at",
            "duration_seconds", "is_connected", "disposition", "notes",
        ]
        read_only_fields = ["id"]

    def validate_phone_number(self, value):
        from apps.core.utils import normalize_indian_phone
        normalized = normalize_indian_phone(value)
        if not normalized:
            raise serializers.ValidationError("Invalid Indian phone number.")
        return normalized


class ClickToCallSerializer(serializers.Serializer):
    """Initiate a click-to-call request."""
    lead_id = serializers.IntegerField()
    phone_number = serializers.CharField(max_length=15, required=False)

    def validate_phone_number(self, value):
        if value:
            from apps.core.utils import normalize_indian_phone
            normalized = normalize_indian_phone(value)
            if not normalized:
                raise serializers.ValidationError("Invalid phone number.")
            return normalized
        return value
