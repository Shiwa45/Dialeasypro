"""
TeleCRM Backend — apps/communications/serializers.py
"""
from django.utils import timezone
from rest_framework import serializers
from apps.communications.models import (
    BulkCampaign, CampaignRecipient, EmailLog,
    SMSLog, WhatsAppConfig, WhatsAppConversation, WhatsAppMessage, WhatsAppTemplate,
)


# Which credential keys each provider expects. Drives the settings form and
# lets us mask secrets on read without ever shipping their values to the client.
PROVIDER_CREDENTIAL_FIELDS = {
    # verify_token / app_secret are only used by the inbound Click-to-WhatsApp
    # webhook; ads_access_token is optional and only needed to resolve
    # campaign/ad names for ad-referred conversations.
    "meta_cloud": [
        "access_token", "phone_number_id", "business_account_id",
        "verify_token", "app_secret", "ads_access_token",
    ],
    "interakt": ["api_key"],
    "aisensy": ["api_key", "text_campaign"],
    "wati": ["access_token", "api_endpoint"],
    "gupshup": ["api_key", "app_name", "source_number"],
    "twilio": ["account_sid", "auth_token", "from_number"],
    "360dialog": ["api_key"],
}

# Keys whose values must never be echoed back to the client.
# The verify token is included on purpose: it is what lets anyone claim to be
# Meta at the verification handshake, so it is set-once and never read back.
_SECRET_KEYS = {
    "access_token", "api_key", "auth_token", "account_sid",
    "app_secret", "verify_token", "ads_access_token",
}


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
    webhook = serializers.SerializerMethodField()

    class Meta:
        model = WhatsAppConfig
        fields = [
            "provider", "is_active", "default_language",
            "credentials", "configured_fields", "required_fields",
            "last_verified_at", "last_error", "updated_at",
            # ---- Inbound / Click-to-WhatsApp ----
            "inbound_enabled", "create_leads_from_inbound", "ctwa_leads_only",
            "inbound_assign_to", "reopen_lead_on_inbound", "graph_api_version",
            "last_webhook_at", "last_webhook_error", "total_inbound_messages",
            "webhook",
        ]
        read_only_fields = [
            "is_active", "last_verified_at", "last_error", "updated_at",
            "last_webhook_at", "last_webhook_error", "total_inbound_messages",
        ]

    def get_webhook(self, obj) -> dict:
        """
        Everything the admin needs to finish the Meta side, and no secret.

        `callback_url` is built from the request host so it is always this
        tenant's own domain — the value that goes into the Meta app's WhatsApp
        webhook configuration.
        """
        from django.conf import settings

        request = self.context.get("request")
        path = "/api/v1/integrations/meta/whatsapp/"
        callback_url = request.build_absolute_uri(path) if request is not None else path
        creds = obj.credentials or {}
        return {
            "callback_url": callback_url,
            "https": callback_url.startswith("https://"),
            "verify_token_set": bool(creds.get("verify_token")),
            "app_secret_set": bool(creds.get("app_secret")),
            "access_token_set": bool(creds.get("access_token")),
            "ads_token_set": bool(creds.get("ads_access_token")),
            "graph_api_version": (
                obj.graph_api_version or settings.META_GRAPH_API_VERSION
            ),
            "subscribe_fields": ["messages"],
            "signature_enforced": bool(
                getattr(settings, "META_WHATSAPP_VERIFY_SIGNATURE", True)
            ),
        }

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

    #: Plain (non-secret) settings a client may PUT.
    _WRITABLE = (
        "provider", "default_language", "inbound_enabled",
        "create_leads_from_inbound", "ctwa_leads_only", "inbound_assign_to",
        "reopen_lead_on_inbound", "graph_api_version",
    )

    def validate_graph_api_version(self, value):
        """Guard the one field that is interpolated straight into a Graph URL."""
        import re

        if value and not re.fullmatch(r"v\d{1,3}\.\d{1,2}", value):
            raise serializers.ValidationError(
                "Use a Graph API version like v26.0, or leave blank for the default."
            )
        return value

    def update(self, instance, validated_data):
        new_creds = validated_data.pop("credentials", None)
        for attr in self._WRITABLE:
            if attr in validated_data:
                setattr(instance, attr, validated_data[attr])
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
    pending_count = serializers.SerializerMethodField()

    def get_pending_count(self, obj) -> int:
        """
        Recipients not yet attempted. Only meaningful now that Pause actually
        stops a run: it is the number of people who will be messaged if the
        campaign is resumed, which is the question an admin has at that point.
        """
        return obj.recipients.filter(status="pending").count()

    class Meta:
        model = BulkCampaign
        fields = [
            "id", "name", "channel", "created_by", "created_by_name",
            "audience_filters", "estimated_recipients",
            "template", "email_subject", "email_body", "sms_text", "sms_sender_id",
            "status", "failure_reason", "scheduled_at", "started_at", "completed_at",
            "total_recipients", "sent_count", "delivered_count",
            "failed_count", "replied_count", "delivery_rate", "progress_percent",
            "pending_count", "created_at",
        ]
        read_only_fields = [
            "id", "status", "failure_reason", "started_at", "completed_at",
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
        if channel == "email":
            if not data.get("email_subject"):
                raise serializers.ValidationError({"email_subject": "Subject required for email campaigns."})
            # A subject with no body sends blank emails to the whole audience.
            if not (data.get("email_body") or "").strip():
                raise serializers.ValidationError({"email_body": "Body required for email campaigns."})
        if channel == "sms" and not data.get("sms_text"):
            raise serializers.ValidationError({"sms_text": "Message text required for SMS campaigns."})

        scheduled_at = data.get("scheduled_at")
        if scheduled_at and scheduled_at <= timezone.now():
            raise serializers.ValidationError(
                {"scheduled_at": "Pick a time in the future, or launch the campaign now."}
            )
        return data

    def create(self, validated_data):
        # Without this a campaign with scheduled_at stayed "draft", and
        # launch_scheduled_campaigns only ever looks for status="scheduled" —
        # so every scheduled campaign sat there and never sent. The status is
        # read-only on the serializer, hence setting it here.
        if validated_data.get("scheduled_at"):
            validated_data["status"] = "scheduled"
        return super().create(validated_data)


class WhatsAppConversationSerializer(serializers.ModelSerializer):
    """
    A WhatsApp thread with its Meta ad attribution.

    `attribution` carries only the values Meta actually supplied, so a UI can
    render "Campaign: ..." strictly when a campaign is genuinely known instead
    of showing an empty row that looks like missing data.
    """

    attribution = serializers.DictField(read_only=True)
    channel = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    first_message = serializers.SerializerMethodField()

    class Meta:
        model = WhatsAppConversation
        fields = [
            "id", "lead", "channel", "status", "status_display",
            "contact_wa_id", "contact_phone", "whatsapp_profile_name",
            "business_display_phone", "business_phone_number_id",
            "is_ad_referred", "attribution", "first_message",
            "first_message_at", "last_message_at", "message_count",
            "created_at",
        ]
        read_only_fields = fields

    def get_first_message(self, obj) -> str:
        message = (
            obj.messages.filter(direction="inbound")
            .order_by("wa_timestamp", "created_at")
            .first()
        )
        return message.content if message else ""
