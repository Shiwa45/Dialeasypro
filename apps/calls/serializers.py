"""
TeleCRM Backend — apps/calls/serializers.py
"""
import logging

from django.utils.text import slugify

from rest_framework import serializers
from apps.calls.models import CallDisposition, CallLog, CallRecording

logger = logging.getLogger(__name__)


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
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = CallDisposition
        fields = [
            "id", "name", "slug", "category", "category_display", "is_positive", "is_active",
            "sort_order", "auto_followup_hours", "lead_status", "sets_dnd",
            "is_system", "marks_connected",
        ]
        # marks_connected is derived from category (kept for older app builds).
        read_only_fields = ["is_system", "marks_connected"]

    def to_internal_value(self, data):
        # An older settings screen sends marks_connected instead of category.
        if isinstance(data, dict) and "category" not in data and data.get("marks_connected") in (True, False):
            data = {**data, "category": "connected" if data["marks_connected"] else "not_connected"}
        return super().to_internal_value(data)

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
        # A seeded outcome keeps its slug and group: the app, the reports and
        # the AI suggestions refer to them.
        if self.instance is not None and self.instance.is_system:
            if attrs.get("slug") and attrs["slug"] != self.instance.slug:
                raise serializers.ValidationError({"slug": "A built-in outcome's slug can't be changed."})
            if "category" in attrs and attrs["category"] != self.instance.category:
                raise serializers.ValidationError(
                    {"category": "A built-in outcome can't move to the other group. Add a new outcome instead."}
                )
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
    lead_name = serializers.SerializerMethodField()
    duration_display = serializers.CharField(read_only=True)
    disposition_name = serializers.CharField(source="disposition.name", read_only=True)
    disposition_category = serializers.CharField(source="disposition.category", read_only=True, default=None)
    recording = CallRecordingSerializer(read_only=True)

    def get_lead_name(self, obj):
        # The name at the time of the call when the lead has since been deleted.
        if obj.lead_id and obj.lead is not None:
            return obj.lead.name
        return obj.lead_label or None

    class Meta:
        model = CallLog
        fields = [
            "id", "agent", "agent_name", "lead", "lead_name",
            "direction", "phone_number", "started_at", "ended_at",
            "duration_seconds", "duration_display", "is_connected",
            "disposition", "disposition_name", "disposition_category", "notes",
            "provider", "provider_call_id", "call_cost_paise", "client_call_id",
            "recording", "created_at",
        ]
        read_only_fields = ["id", "created_at", "duration_seconds", "is_connected"]


class CallLogCreateSerializer(serializers.ModelSerializer):
    """
    A call logged by an agent (the app's post-call screen, the web's Log call).

    * An outcome is required — a call with none was invisible to every
      outcome report and moved nothing on the lead.
    * The outcome must belong to the call status: an answered call takes a
      "connected" outcome, an unanswered one a "not connected" outcome.
      Clients that send client_call_id (current web and app) get a 400 on a
      mismatch. Older app builds are let through with the status they sent,
      and the mismatch is logged, until they are retired.
    * client_call_id makes a retry safe (see CallLogListCreateView.create).
    """

    disposition = serializers.PrimaryKeyRelatedField(
        queryset=CallDisposition.objects.all(),
        error_messages={"required": "Choose the call outcome.", "null": "Choose the call outcome."},
    )
    is_connected = serializers.BooleanField(required=False)
    client_call_id = serializers.CharField(max_length=64, required=False, allow_blank=True)

    class Meta:
        model = CallLog
        # ended_at was missing, so every call the app logged was saved with
        # no end time (the app always sends one).
        fields = [
            "id", "lead", "direction", "phone_number", "started_at", "ended_at",
            "duration_seconds", "is_connected", "disposition", "notes", "client_call_id",
        ]
        read_only_fields = ["id"]

    def validate_disposition(self, disposition):
        if disposition is not None and not disposition.is_active:
            raise serializers.ValidationError(f'"{disposition.name}" is switched off. Choose another outcome.')
        return disposition

    def validate_phone_number(self, value):
        from apps.core.utils import normalize_indian_phone
        normalized = normalize_indian_phone(value)
        if not normalized:
            raise serializers.ValidationError("Invalid Indian phone number.")
        return normalized

    def validate_lead(self, lead):
        """
        Only a lead this agent may see. Logging a call marks the lead worked,
        moves it from new to attempted, clears its queue lock and writes to
        its history — and any agent could do that to any lead in the tenant.
        """
        if lead is None:
            return lead
        request = self.context.get("request")
        if request is not None:
            from apps.leads.views import leads_visible_to

            if not leads_visible_to(request.user).filter(pk=lead.pk).exists():
                raise serializers.ValidationError("Lead not found.")
        return lead

    def validate(self, data):
        started, ended = data.get("started_at"), data.get("ended_at")
        if started and ended and ended < started:
            raise serializers.ValidationError({"ended_at": "A call cannot end before it starts."})

        from apps.calls.services.outcomes import OutcomeMismatch, check_outcome_matches
        from apps.core.constants import DispositionCategory

        disposition = data.get("disposition")
        if "is_connected" not in data:
            # Not said: the outcome's group says it.
            data["is_connected"] = disposition.category == DispositionCategory.CONNECTED
        else:
            try:
                check_outcome_matches(disposition, data["is_connected"])
            except OutcomeMismatch as exc:
                if data.get("client_call_id"):
                    raise serializers.ValidationError({"disposition": str(exc)})
                logger.warning("[Calls] Outcome/status mismatch from an older client: %s", exc)
        return data


class CallOutcomeSerializer(serializers.Serializer):
    """Set the outcome of a call that was saved without one."""

    disposition = serializers.PrimaryKeyRelatedField(
        queryset=CallDisposition.objects.filter(is_active=True),
        error_messages={"required": "Choose the call outcome.", "null": "Choose the call outcome."},
    )
    is_connected = serializers.BooleanField(required=False)
    duration_seconds = serializers.IntegerField(min_value=0, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        from apps.calls.services.outcomes import OutcomeMismatch, check_outcome_matches
        from apps.core.constants import DispositionCategory

        if "is_connected" not in data:
            data["is_connected"] = data["disposition"].category == DispositionCategory.CONNECTED
        try:
            check_outcome_matches(data["disposition"], data["is_connected"])
        except OutcomeMismatch as exc:
            raise serializers.ValidationError({"disposition": str(exc)})
        return data


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
