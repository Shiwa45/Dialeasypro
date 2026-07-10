"""
TeleCRM Backend — apps/communications/serializers.py
"""
from rest_framework import serializers
from apps.communications.models import (
    BulkCampaign, CampaignRecipient, EmailLog,
    SMSLog, WhatsAppConfig, WhatsAppMessage, WhatsAppTemplate,
)


# Which credential keys each provider expects. Drives the settings form and
# lets us mask secrets on read without ever shipping their values to the client.
PROVIDER_CREDENTIAL_FIELDS = {
    "meta_cloud": ["access_token", "phone_number_id", "business_account_id"],
    "interakt": ["api_key"],
    "aisensy": ["api_key", "text_campaign"],
    "wati": ["access_token", "api_endpoint"],
    "gupshup": ["api_key", "app_name", "source_number"],
    "twilio": ["account_sid", "auth_token", "from_number"],
    "360dialog": ["api_key"],
}

# Keys whose values must never be echoed back to the client.
_SECRET_KEYS = {"access_token", "api_key", "auth_token", "account_sid"}


class WhatsAppConfigSerializer(serializers.ModelSerializer):
    """
    A tenant's WhatsApp connection.

    Credentials are write-only: the client sends `{provider, credentials}` and
    reads back only `configured_fields` (which keys are set) — the secret values
    never leave the server once stored.
    """

    credentials = serializers.DictField(write_only=True, required=False)
    configured_fields = serializers.SerializerMethodField()
    required_fields = serializers.SerializerMethodField()

    class Meta:
        model = WhatsAppConfig
        fields = [
            "provider", "is_active", "default_language",
            "credentials", "configured_fields", "required_fields",
            "last_verified_at", "last_error", "updated_at",
        ]
        read_only_fields = ["is_active", "last_verified_at", "last_error", "updated_at"]

    def get_configured_fields(self, obj) -> dict:
        """{key: masked_or_value} — secrets shown only as a set/unset flag."""
        creds = obj.credentials or {}
        out = {}
        for key, value in creds.items():
            if key in _SECRET_KEYS:
                out[key] = "••••••••" if value else ""
            else:
                out[key] = value  # non-secret (endpoint URL, app name, phone id)
        return out

    def get_required_fields(self, obj) -> list:
        return PROVIDER_CREDENTIAL_FIELDS.get(obj.provider, [])

    def update(self, instance, validated_data):
        new_creds = validated_data.pop("credentials", None)
        instance.provider = validated_data.get("provider", instance.provider)
        instance.default_language = validated_data.get("default_language", instance.default_language)
        if new_creds is not None:
            # Merge, so a client can update one secret without resending all of
            # them — but drop blanks and the mask placeholder so an untouched
            # masked field doesn't overwrite the real secret with dots.
            merged = dict(instance.credentials or {})
            for key, value in new_creds.items():
                if value in ("", None) or value == "••••••••":
                    continue
                merged[key] = value
            instance.credentials = merged
        # Any credential change forces re-verification before sends resume.
        instance.is_active = False
        instance.last_error = ""
        instance.save()
        return instance


class WhatsAppTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhatsAppTemplate
        fields = [
            "id", "name", "category", "language",
            "header_type", "header_text", "header_media_url",
            "body_text", "footer_text",
            "variable_mapping", "provider", "status",
            "is_active", "usage_count",
        ]
        read_only_fields = ["id", "usage_count"]


class WhatsAppMessageSerializer(serializers.ModelSerializer):
    lead_name = serializers.CharField(source="lead.name", read_only=True)
    sent_by_name = serializers.CharField(source="sent_by.name", read_only=True)

    class Meta:
        model = WhatsAppMessage
        fields = [
            "id", "lead", "lead_name", "sent_by", "sent_by_name",
            "direction", "message_type", "content", "template",
            "status", "sent_at", "delivered_at", "read_at",
            "error_message", "created_at",
        ]
        read_only_fields = ["id", "direction", "status", "sent_at", "created_at"]


class SendWhatsAppSerializer(serializers.Serializer):
    """Send a single WhatsApp message from lead detail."""
    lead_id = serializers.IntegerField()
    message = serializers.CharField(max_length=4096, required=False, allow_blank=True)
    template_id = serializers.IntegerField(required=False)

    def validate(self, data):
        if not data.get("message") and not data.get("template_id"):
            raise serializers.ValidationError("Provide either a message or a template_id.")
        return data


class SendSMSSerializer(serializers.Serializer):
    lead_id = serializers.IntegerField()
    message = serializers.CharField(max_length=1600)
    sender_id = serializers.CharField(max_length=11, required=False, default="")


class BulkCampaignSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.name", read_only=True)
    delivery_rate = serializers.FloatField(read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = BulkCampaign
        fields = [
            "id", "name", "channel", "created_by", "created_by_name",
            "audience_filters", "estimated_recipients",
            "template", "email_subject", "email_body", "sms_text", "sms_sender_id",
            "status", "scheduled_at", "started_at", "completed_at",
            "total_recipients", "sent_count", "delivered_count",
            "failed_count", "replied_count", "delivery_rate", "progress_percent",
            "created_at",
        ]
        read_only_fields = [
            "id", "status", "started_at", "completed_at",
            "total_recipients", "sent_count", "delivered_count",
            "failed_count", "replied_count", "created_at",
        ]


class BulkCampaignCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BulkCampaign
        fields = [
            "name", "channel", "audience_filters",
            "template", "email_subject", "email_body",
            "sms_text", "sms_sender_id", "scheduled_at",
        ]

    def validate(self, data):
        channel = data.get("channel")
        if channel == "whatsapp" and not data.get("template"):
            raise serializers.ValidationError({"template": "Template required for WhatsApp campaigns."})
        if channel == "email" and not data.get("email_subject"):
            raise serializers.ValidationError({"email_subject": "Subject required for email campaigns."})
        if channel == "sms" and not data.get("sms_text"):
            raise serializers.ValidationError({"sms_text": "Message text required for SMS campaigns."})
        return data
