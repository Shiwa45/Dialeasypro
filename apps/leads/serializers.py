"""
TeleCRM Backend — apps/leads/serializers.py

DRF serializers for all lead-related models.
"""
from django.utils import timezone
from rest_framework import serializers

from apps.authentication.models import Agent
from apps.core.constants import FollowUpType, LeadPriority, LeadSource, LeadStatus
from apps.core.utils import normalize_indian_phone
from apps.leads.models import (
    CallQueue,
    CallQueueMembership,
    CustomField,
    CustomFieldValue,
    FollowUp,
    Lead,
    LeadActivity,
    LeadBatch,
    LeadImportJob,
    LeadNote,
)


# ============================================================
# Custom Field Serializers
# ============================================================

class CustomFieldSerializer(serializers.ModelSerializer):
    field_key = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = CustomField
        fields = [
            "id", "name", "field_key", "field_type", "is_required",
            "is_active", "sort_order", "options", "placeholder",
        ]
        read_only_fields = ["id"]


class CustomFieldValueSerializer(serializers.ModelSerializer):
    field_key = serializers.CharField(source="field.field_key", read_only=True)
    field_name = serializers.CharField(source="field.name", read_only=True)

    class Meta:
        model = CustomFieldValue
        fields = ["field", "field_key", "field_name", "value"]


# ============================================================
# Lead Serializers
# ============================================================

class FollowUpSerializer(serializers.ModelSerializer):
    followup_type_display = serializers.CharField(source="get_followup_type_display", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.name", read_only=True)
    is_overdue = serializers.SerializerMethodField()
    # Who the follow-up is with. A reminder that says "follow up with lead 54"
    # is useless on a phone's lock screen, and the mobile app had no way to
    # resolve the name without a request per follow-up.
    lead_name = serializers.CharField(source="lead.name", read_only=True)
    lead_phone = serializers.CharField(source="lead.phone", read_only=True)

    class Meta:
        model = FollowUp
        fields = [
            "id", "lead", "lead_name", "lead_phone",
            "assigned_to", "assigned_to_name",
            "followup_type", "followup_type_display",
            "scheduled_at", "notes", "is_completed",
            "completed_at", "completion_notes", "is_overdue",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "completed_at"]

    def get_is_overdue(self, obj):
        return not obj.is_completed and obj.scheduled_at < timezone.now()


from datetime import timedelta


class FollowUpCreateSerializer(serializers.ModelSerializer):
    """Used when creating a new follow-up from a lead detail view."""

    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=Agent.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = FollowUp
        fields = ["followup_type", "scheduled_at", "notes", "assigned_to"]

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, "copy") else dict(data)
        if "assigned_to" in data and (data["assigned_to"] in (0, "0", "", None)):
            data["assigned_to"] = None
        return super().to_internal_value(data)

    def validate_scheduled_at(self, value):
        if value < (timezone.now() - timedelta(minutes=5)):
            raise serializers.ValidationError(
                "Follow-up time must be in the future."
            )
        return value


class LeadNoteSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source="agent.name", read_only=True)
    agent_photo = serializers.SerializerMethodField()

    class Meta:
        model = LeadNote
        fields = [
            "id", "lead", "agent", "agent_name", "agent_photo",
            "content", "is_pinned", "attachment", "created_at",
        ]
        read_only_fields = ["id", "agent", "created_at"]

    def get_agent_photo(self, obj):
        if obj.agent and obj.agent.profile_photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.agent.profile_photo.url)
        return None


class LeadActivitySerializer(serializers.ModelSerializer):
    performed_by_name = serializers.CharField(source="performed_by.name", read_only=True)

    class Meta:
        model = LeadActivity
        fields = [
            "id", "activity_type", "description", "performed_by",
            "performed_by_name", "meta", "timestamp",
        ]
        read_only_fields = ["id", "timestamp"]


class LeadListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views — no nested objects."""

    assigned_to_name = serializers.CharField(source="assigned_to.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)
    followup_overdue = serializers.BooleanField(read_only=True)
    phone = serializers.SerializerMethodField()
    batch_label = serializers.SerializerMethodField()
    batch_number = serializers.IntegerField(source="batch.number", read_only=True, default=None)

    class Meta:
        model = Lead
        fields = [
            "id", "name", "phone", "email", "city",
            "status", "status_display", "priority", "priority_display",
            "source", "source_display", "score",
            "assigned_to", "assigned_to_name",
            "next_followup_at", "followup_overdue",
            "last_contacted_at", "contact_count",
            "deal_value", "pipeline_stage",
            "campaign_name", "ad_name",
            "batch", "batch_number", "batch_label",
            "tags", "is_dnd", "created_at",
        ]

    def get_batch_label(self, obj) -> str | None:
        # `label` is a property, so it cannot be reached with a source path.
        return obj.batch.label if obj.batch_id and obj.batch else None

    def get_phone(self, obj):
        """Mask phone number for non-admin agents."""
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            from apps.core.constants import AgentRole
            if request.user.role in [AgentRole.ADMIN, AgentRole.MANAGER]:
                return obj.phone
        from apps.core.utils import mask_phone_number
        return mask_phone_number(obj.phone)


class LeadDetailSerializer(serializers.ModelSerializer):
    """Full serializer for lead detail view — includes nested data."""

    assigned_to_name = serializers.CharField(source="assigned_to.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)
    followups = FollowUpSerializer(many=True, read_only=True)
    notes = LeadNoteSerializer(many=True, read_only=True)
    activities = LeadActivitySerializer(many=True, read_only=True)
    custom_field_values = CustomFieldValueSerializer(many=True, read_only=True)
    followup_overdue = serializers.BooleanField(read_only=True)
    days_since_last_contact = serializers.IntegerField(read_only=True)
    whatsapp_attribution = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            "id", "name", "phone", "alternate_phone", "email",
            "city", "state", "pincode", "address",
            "status", "status_display", "priority", "priority_display",
            "source", "source_display", "score",
            "assigned_to", "assigned_to_name", "assigned_at",
            "budget", "requirement", "deal_value", "expected_close_date",
            "campaign_name", "ad_name", "whatsapp_attribution",
            "pipeline_stage", "next_followup_at", "followup_overdue",
            "last_contacted_at", "days_since_last_contact", "contact_count",
            "is_dnd", "tags",
            "followups", "notes", "activities", "custom_field_values",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "assigned_at"]

    def get_whatsapp_attribution(self, obj) -> dict | None:
        """
        Where a Click-to-WhatsApp lead actually came from: the ad, its ad set
        and campaign, the ad copy the customer tapped, and their first message.

        Returns None for a lead with no ad-referred WhatsApp conversation, and
        inside `attribution` only the keys Meta genuinely supplied — the
        campaign/ad-set/ad NAMES are absent unless the Marketing API lookup
        succeeded, so the UI must render what is present rather than assume a
        fixed shape.
        """
        conversation = (
            obj.whatsapp_conversations.filter(is_ad_referred=True)
            .order_by("-created_at")
            .first()
        )
        if conversation is None:
            return None

        first_message = (
            conversation.messages.filter(direction="inbound")
            .order_by("wa_timestamp", "created_at")
            .first()
        )
        return {
            "conversation_id": str(conversation.pk),
            "channel": conversation.channel,
            "source": "Meta Click-to-WhatsApp",
            "attribution": conversation.attribution,
            "first_message": first_message.content if first_message else "",
            "first_message_at": conversation.first_message_at,
        }


class LeadCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new lead (manual entry or API)."""

    custom_fields = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False, write_only=True,
        help_text="Dict of {field_key: value} for custom fields.",
    )

    class Meta:
        model = Lead
        fields = [
            "name", "phone", "alternate_phone", "email",
            "city", "state", "pincode",
            "source", "status", "priority",
            # deal_value was missing while both clients send it on the new-lead
            # form, so an expected deal size typed at creation was accepted by
            # the API and silently never stored.
            "assigned_to", "budget", "deal_value", "requirement",
            "tags", "custom_fields",
        ]

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, "copy") else dict(data)
        for field in ["budget", "deal_value", "assigned_to", "email", "expected_close_date", "alternate_phone", "city", "state", "pincode"]:
            if field in data and (data[field] == "" or data[field] is None):
                data[field] = None
        return super().to_internal_value(data)

    def validate_phone(self, value):
        normalized = normalize_indian_phone(value)
        if not normalized:
            raise serializers.ValidationError(
                "Invalid Indian mobile number. Enter a 10-digit number."
            )
        return normalized

    def validate_alternate_phone(self, value):
        if value:
            normalized = normalize_indian_phone(value)
            if not normalized:
                raise serializers.ValidationError("Invalid alternate phone number.")
            return normalized
        return value

    def validate(self, data):
        # Check for duplicate phone within this tenant
        phone = data.get("phone")
        if phone:
            if Lead.objects.filter(phone=phone, is_deleted=False).exists():
                raise serializers.ValidationError(
                    {"phone": "A lead with this phone number already exists."}
                )
        return data

    def create(self, validated_data):
        from apps.core.quotas import enforce_lead_quota, note_leads_created

        custom_fields_data = validated_data.pop("custom_fields", {})

        # Plan capacity: raises 402 with the limit details.
        enforce_lead_quota(1)

        lead = Lead.objects.create(**validated_data)
        note_leads_created(1)

        # Save custom field values
        if custom_fields_data:
            for field_key, value in custom_fields_data.items():
                try:
                    field = CustomField.objects.get(field_key=field_key, is_active=True)
                    CustomFieldValue.objects.create(lead=lead, field=field, value=value)
                except CustomField.DoesNotExist:
                    pass

        # Log creation activity
        LeadActivity.objects.create(
            lead=lead,
            activity_type="other",
            description=f"Lead created via {lead.get_source_display()}",
        )
        return lead


class LeadUpdateSerializer(serializers.ModelSerializer):
    """Partial update serializer — handles status changes, reassignment, etc."""

    custom_fields = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False, write_only=True,
        help_text="Dict of {field_key: value} for custom fields.",
    )

    class Meta:
        model = Lead
        fields = [
            "name", "phone", "alternate_phone", "email",
            "city", "state", "pincode",
            "status", "priority", "score",
            "assigned_to", "budget", "requirement",
            "deal_value", "expected_close_date",
            "pipeline_stage", "tags", "custom_fields",
        ]

    def validate_phone(self, value):
        normalized = normalize_indian_phone(value)
        if not normalized:
            raise serializers.ValidationError("Invalid Indian mobile number.")
        # Check duplicate but exclude this lead
        if Lead.objects.filter(phone=normalized, is_deleted=False).exclude(
            pk=self.instance.pk
        ).exists():
            raise serializers.ValidationError("Another lead with this phone already exists.")
        return normalized

    def update(self, instance, validated_data):
        custom_fields_data = validated_data.pop("custom_fields", None)
        lead = super().update(instance, validated_data)

        if custom_fields_data is not None:
            for field_key, value in custom_fields_data.items():
                try:
                    field = CustomField.objects.get(field_key=field_key, is_active=True)
                    CustomFieldValue.objects.update_or_create(
                        lead=lead, field=field,
                        defaults={"value": value}
                    )
                except CustomField.DoesNotExist:
                    pass

        return lead


class LeadBulkAssignSerializer(serializers.Serializer):
    """Bulk assign multiple leads to an agent."""
    lead_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, max_length=500)
    assigned_to = serializers.IntegerField()

    def validate_assigned_to(self, value):
        from apps.authentication.models import Agent
        try:
            return Agent.objects.get(pk=value, is_active=True)
        except Agent.DoesNotExist:
            raise serializers.ValidationError("Agent not found or inactive.")


class LeadDistributeSerializer(serializers.Serializer):
    """
    Distribute leads matching a filter across one or more agents in a single
    action. If multiple agents are given, leads are split round-robin (evenly).
    This replaces tedious one-by-one / checkbox assignment.
    """
    agent_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=200,
    )
    only_unassigned = serializers.BooleanField(default=True)
    # Restrict to specific consignments. Combines with the other filters, so
    # "batch 3, only the hot ones" is expressible.
    batch_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list, max_length=100,
    )
    method = serializers.CharField(default="round_robin")
    max_per_agent = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=100000, default=None,
    )
    statuses = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    priorities = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    sources = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    search = serializers.CharField(required=False, allow_blank=True, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=20000, allow_null=True)

    def validate_agent_ids(self, value):
        from apps.authentication.models import Agent
        # Preserve caller order, drop invalid/inactive ids.
        valid = {
            a.pk: a for a in Agent.objects.filter(pk__in=value, is_active=True)
        }
        agents = [valid[pk] for pk in value if pk in valid]
        if not agents:
            raise serializers.ValidationError("No valid active agents provided.")
        return agents

    def validate_method(self, value):
        from apps.leads.services.distribution import Method

        if value not in Method.ALL:
            raise serializers.ValidationError(
                f"Unknown method '{value}'. One of: {', '.join(Method.ALL)}."
            )
        return value


class LeadImportJobSerializer(serializers.ModelSerializer):
    imported_by_name = serializers.CharField(source="imported_by.name", read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)
    # The batch this import created, so the client can link straight to it
    # when the job finishes. Null until the file has parsed.
    batch_id = serializers.IntegerField(source="batch.id", read_only=True, default=None)
    batch_number = serializers.IntegerField(source="batch.number", read_only=True, default=None)
    batch_label = serializers.SerializerMethodField()

    class Meta:
        model = LeadImportJob
        fields = [
            "id", "original_filename", "status", "imported_by_name",
            "total_rows", "processed_rows", "successful_rows",
            "failed_rows", "duplicate_rows", "progress_percent",
            "duplicate_action", "created_at", "completed_at",
            "batch_name", "batch_id", "batch_number", "batch_label",
            "auto_assign", "assign_method", "assign_to_agents",
            "assign_max_per_agent", "assignment_result",
        ]
        read_only_fields = [
            "id", "status", "total_rows", "processed_rows",
            "successful_rows", "failed_rows", "duplicate_rows",
            "completed_at", "created_at", "assignment_result",
        ]

    def get_batch_label(self, obj) -> str | None:
        batch = getattr(obj, "batch", None)
        return batch.label if batch else None


# ============================================================
# Call Queue Serializers
# ============================================================

class CallQueueSerializer(serializers.ModelSerializer):
    """Admin CRUD serializer for calling queues."""

    agent_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False,
        help_text="Agent IDs that may work this queue.",
    )
    agents = serializers.SerializerMethodField(read_only=True)
    created_by_name = serializers.CharField(source="created_by.name", read_only=True)

    class Meta:
        model = CallQueue
        fields = [
            "id", "name", "description", "is_active",
            "filter_statuses", "filter_priorities", "filter_sources", "filter_tags",
            "only_unworked", "only_followup_due", "exclude_dnd",
            "order_by", "mode", "redial_cooldown_hours", "lock_ttl_minutes",
            "agent_ids", "agents", "created_by_name", "created_at",
        ]
        read_only_fields = ["id", "created_at", "created_by_name"]

    def get_agents(self, obj):
        return [
            {"id": m.agent_id, "name": m.agent.name, "role": m.agent.role}
            for m in obj.memberships.select_related("agent").all()
        ]

    def _sync_agents(self, queue, agent_ids):
        from apps.authentication.models import Agent
        valid_ids = set(
            Agent.objects.filter(pk__in=agent_ids, is_active=True)
            .values_list("pk", flat=True)
        )
        # Remove memberships no longer present.
        queue.memberships.exclude(agent_id__in=valid_ids).delete()
        existing = set(queue.memberships.values_list("agent_id", flat=True))
        for aid in valid_ids - existing:
            CallQueueMembership.objects.create(queue=queue, agent_id=aid)

    def create(self, validated_data):
        agent_ids = validated_data.pop("agent_ids", [])
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            validated_data["created_by"] = request.user
        queue = CallQueue.objects.create(**validated_data)
        self._sync_agents(queue, agent_ids)
        return queue

    def update(self, instance, validated_data):
        agent_ids = validated_data.pop("agent_ids", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if agent_ids is not None:
            self._sync_agents(instance, agent_ids)
        return instance


class CallQueueSummarySerializer(serializers.ModelSerializer):
    """Lightweight serializer for the agent's available-queues list."""

    pending_count = serializers.SerializerMethodField()

    class Meta:
        model = CallQueue
        fields = [
            "id", "name", "description", "mode", "order_by", "pending_count",
        ]

    def get_pending_count(self, obj):
        agent = self.context.get("agent")
        if not agent:
            return 0
        return obj.eligible_leads(agent).count()


# ============================================================
# Lead batches
# ============================================================

class LeadBatchSerializer(serializers.ModelSerializer):
    """
    A batch as the admin sees it. `label` is the display name — their own name
    if they set one, otherwise a generated one — so the client never has to
    reimplement that fallback.
    """

    label = serializers.CharField(read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)
    created_by_name = serializers.CharField(source="created_by.name", read_only=True, default=None)
    assigned_count = serializers.IntegerField(read_only=True)
    unassigned_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = LeadBatch
        fields = [
            "id", "number", "name", "label", "kind", "source", "source_display",
            "status", "collection_date", "import_job", "created_by", "created_by_name",
            "total_leads", "assigned_count", "unassigned_count",
            "notes", "closed_at", "created_at",
        ]
        # Everything except the label and notes is decided by the system — a
        # client must not be able to renumber a batch or restate its counts.
        read_only_fields = [
            "id", "number", "kind", "source", "status", "collection_date",
            "import_job", "created_by", "total_leads", "closed_at", "created_at",
        ]


class LeadBatchDistributeSerializer(serializers.Serializer):
    """Distribute the leads in one or more batches across agents."""

    batch_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=100,
    )
    agent_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=200,
    )
    method = serializers.CharField(default="round_robin")
    only_unassigned = serializers.BooleanField(default=True)
    max_per_agent = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=100000, default=None,
    )
    limit = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=50000, default=None,
    )

    def validate_method(self, value):
        from apps.leads.services.distribution import Method

        if value not in Method.ALL:
            raise serializers.ValidationError(
                f"Unknown method '{value}'. One of: {', '.join(Method.ALL)}."
            )
        return value

    def validate_agent_ids(self, value):
        from apps.authentication.models import Agent

        # Caller order is preserved — round robin starts with the first agent
        # the admin picked, which is what they expect to see in the result.
        valid = {a.pk: a for a in Agent.objects.filter(pk__in=value, is_active=True)}
        agents = [valid[pk] for pk in value if pk in valid]
        if not agents:
            raise serializers.ValidationError("No valid active agents provided.")
        return agents

    def validate_batch_ids(self, value):
        from apps.leads.models import LeadBatch

        found = set(LeadBatch.objects.filter(pk__in=value).values_list("pk", flat=True))
        missing = [pk for pk in value if pk not in found]
        if missing:
            raise serializers.ValidationError(f"Batch(es) not found: {missing}.")
        return value
