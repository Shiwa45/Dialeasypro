"""TeleCRM Backend — apps/communications/admin.py"""
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from django.utils.html import format_html
from apps.communications.models import (
    BulkCampaign, CampaignRecipient, EmailLog,
    SMSLog, WhatsAppMessage, WhatsAppTemplate,
)

@admin.register(WhatsAppTemplate)
class WhatsAppTemplateAdmin(ModelAdmin):
    list_display = ["name", "category", "provider", "status", "usage_count", "is_active"]
    list_filter = ["status", "provider", "category"]
    search_fields = ["name"]

@admin.register(BulkCampaign)
class BulkCampaignAdmin(ModelAdmin):
    list_display = ["name", "channel", "status", "total_recipients", "sent_count",
                    "delivered_count", "failed_count", "created_at"]
    list_filter = ["channel", "status"]
    search_fields = ["name"]
    readonly_fields = ["total_recipients", "sent_count", "delivered_count",
                       "failed_count", "replied_count", "started_at", "completed_at"]

@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(ModelAdmin):
    list_display = ["lead_name", "direction", "status", "sent_at", "created_at"]
    list_filter = ["direction", "status", "provider"]
    readonly_fields = ["id", "provider_message_id", "sent_at", "delivered_at", "read_at"]

    @display(description="Lead")
    def lead_name(self, obj):
        return obj.lead.name if obj.lead else "—"
