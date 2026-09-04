"""TeleCRM Backend — apps/integrations/serializers.py"""
from rest_framework import serializers
from apps.core.constants import LeadSource
from apps.integrations.models import LeadSourceConfig, WebhookLog

# Lead sources that have a dedicated webhook path (vs the generic token URL).
DEDICATED_WEBHOOK_PATHS = {
    "meta_facebook": "/api/v1/integrations/meta/",
    "meta_instagram": "/api/v1/integrations/meta/",
    "google_ads": "/api/v1/integrations/google/",
    "indiamart": "/api/v1/integrations/indiamart/",
}


# Sources that are NOT configured through LeadSourceConfig. Click-to-WhatsApp
# and organic WhatsApp inbound are driven by the tenant's WhatsAppConfig (the
# Meta Cloud credentials, the verify token, the inbound switches) and land on a
# dedicated signed webhook — a LeadSourceConfig row for them would hand the
# admin a generic token URL that nothing reads, and an "API key" field that
# nothing uses. They still appear on WebhookLog rows, which is a different
# thing: that records what arrived, not how it was configured.
NON_CONFIGURABLE_SOURCES = {
    LeadSource.META_CTWA: (
        "Click-to-WhatsApp is configured on the WhatsApp connection, not here. "
        "Use the 'Meta — Click to WhatsApp' card on the Integrations screen "
        "(or PUT /api/v1/comms/whatsapp/config/)."
    ),
    LeadSource.WHATSAPP: (
        "Inbound WhatsApp is configured on the WhatsApp connection, not here. "
        "Use the 'Meta — Click to WhatsApp' card on the Integrations screen."
    ),
}


class LeadSourceConfigSerializer(serializers.ModelSerializer):
    source_display = serializers.CharField(source="get_source_display", read_only=True)
    webhook_url = serializers.SerializerMethodField()
    credentials_status = serializers.SerializerMethodField()
    # Write-only: the UI submits provider credentials here; they are never read back.
    credentials = serializers.JSONField(write_only=True, required=False)

    class Meta:
        model = LeadSourceConfig
        fields = [
            "id", "source", "source_display", "is_active", "status",
            "options", "credentials", "credentials_status",
            "webhook_token", "webhook_url",
            "total_leads_received", "last_received_at", "error_message",
        ]
        read_only_fields = [
            "id", "webhook_token", "total_leads_received",
            "last_received_at", "error_message", "status",
        ]

    def validate_source(self, value):
        """Reject a source whose real configuration lives somewhere else."""
        if message := NON_CONFIGURABLE_SOURCES.get(value):
            raise serializers.ValidationError(message)
        return value

    def get_webhook_url(self, obj):
        """
        Absolute, source-aware webhook URL the tenant pastes into the provider.
        Built from the request host so it is always the tenant's own domain
        (e.g. https://demo.telecrm.in/api/v1/integrations/meta/).
        """
        path = DEDICATED_WEBHOOK_PATHS.get(obj.source) or (
            f"/api/v1/integrations/webhook/{obj.webhook_token}/"
        )
        request = self.context.get("request")
        if request is not None:
            return request.build_absolute_uri(path)
        return path

    def get_credentials_status(self, obj):
        """
        Non-secret view of which credentials are configured. The verify_token
        is a shared (non-secret) value the tenant also enters in Meta, so it is
        returned in clear; real secrets are masked to booleans.
        """
        creds = obj.credentials or {}
        return {
            "verify_token": creds.get("verify_token", ""),
            "has_app_secret": bool(creds.get("app_secret")),
            "has_access_token": bool(creds.get("access_token")),
            "has_api_key": bool(creds.get("api_key")),
        }

    def update(self, instance, validated_data):
        # Merge credentials so a partial update never wipes existing secrets:
        # only keys sent with a non-empty value are overwritten.
        new_creds = validated_data.pop("credentials", None)
        if new_creds is not None:
            merged = dict(instance.credentials or {})
            for key, value in new_creds.items():
                if value not in (None, ""):
                    merged[key] = value
            instance.credentials = merged
        return super().update(instance, validated_data)


class WebhookLogSerializer(serializers.ModelSerializer):
    source_display = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = WebhookLog
        fields = [
            "id", "source", "source_display", "processed",
            "leads_created", "leads_updated", "error", "created_at",
        ]
