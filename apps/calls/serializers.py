"""
TeleCRM Backend — apps/calls/serializers.py
"""
from django.utils.text import slugify

from rest_framework import serializers
from apps.calls.models import CallDisposition, CallLog, CallRecording


class CallDispositionSerializer(serializers.ModelSerializer):
    """
    A call outcome, as the settings screen writes it and the dialer reads it.

    `slug` is the stable handle: signals auto-schedule follow-ups from the
    disposition, and the AI insight picks one of these slugs when it suggests
    an outcome. Admins should not have to invent it, so it is optional here
    and derived from the name — but it stays editable, because an existing
    tenant's slugs are already referred to elsewhere.
    """

    slug = serializers.SlugField(max_length=50, required=False, allow_blank=True)

    class Meta:
        model = CallDisposition
        fields = [
            "id", "name", "slug", "is_positive", "is_active",
            "sort_order", "auto_followup_hours",
        ]

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Give the outcome a name.")

        clash = CallDisposition.objects.filter(name__iexact=name)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        existing = clash.first()
        if existing:
            raise serializers.ValidationError(
                f'"{existing.name}" already exists'
                + ("" if existing.is_active else " but is switched off — switch it back on instead.")
            )
        return name

    def validate(self, attrs):
        # A blank slug on create means "name it for me". On update, a blank
        # one means "leave it alone" — regenerating it there would rename a
        # handle that call history and AI suggestions already point at.
        if not attrs.get("slug"):
            attrs.pop("slug", None)
            if self.instance is None:
                attrs["slug"] = self._unique_slug(attrs.get("name", ""))
        return attrs

    @staticmethod
    def _unique_slug(name):
        base = slugify(name)[:50] or "disposition"
        slug, n = base, 2
        while CallDisposition.objects.filter(slug=slug).exists():
            suffix = f"-{n}"
            slug = f"{base[:50 - len(suffix)]}{suffix}"
            n += 1
        return slug


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
