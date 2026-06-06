"""
TeleCRM Backend — apps/communications/serializers.py
"""
from rest_framework import serializers
from apps.communications.models import (
    BulkCampaign, CampaignRecipient, EmailLog,
    SMSLog, WhatsAppMessage, WhatsAppTemplate,
)


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
