"""TeleCRM Backend — apps/communications/admin.py"""
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from django.utils.html import format_html
from apps.communications.models import (
    BulkCampaign, CampaignRecipient, EmailLog,
    SMSLog, WhatsAppConfig, WhatsAppConversation, WhatsAppMessage, WhatsAppTemplate,
)


@admin.register(WhatsAppConfig)
class WhatsAppConfigAdmin(ModelAdmin):
    # Credentials are an encrypted blob — never surface them in the changelist.
    list_display = [
        "provider", "is_active", "inbound_enabled",
        "total_inbound_messages", "last_webhook_at", "last_error",
    ]
    readonly_fields = [
        "last_verified_at", "singleton",
        "last_webhook_at", "last_webhook_error", "total_inbound_messages",
    ]

    def has_add_permission(self, request):
        # Singleton, created on first access via GET /comms/whatsapp/config/
        # (WhatsAppConfig.get_solo()) — the admin never creates the first row.
        #
        # Deliberately no DB query here: Django's admin index builds its
        # sidebar by calling this with no schema context guaranteed — the
        # PUBLIC schema (where /superadmin-secure/ lives) enumerates every
        # registered admin including this tenant-only app's, and this table
        # doesn't exist there at all. A query here 500s the entire superadmin
        # panel, not just this page.
        return False

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


@admin.register(WhatsAppConversation)
class WhatsAppConversationAdmin(ModelAdmin):
    """
    Inbound WhatsApp threads and the Meta ad that started them.

    Read-only: every field is written from Meta's webhook, and a hand-edited
    attribution would quietly poison campaign reporting.
    """

    list_display = [
        "contact_wa_id", "lead_name", "status", "ad_referred",
        "meta_campaign_name", "message_count", "last_message_at",
    ]
    list_filter = ["status", "is_ad_referred", "provider"]
    search_fields = [
        "contact_wa_id", "contact_phone", "whatsapp_profile_name",
        "meta_campaign_name", "meta_ad_id", "referral_source_id",
    ]
    readonly_fields = [f.name for f in WhatsAppConversation._meta.fields]

    @display(description="Lead")
    def lead_name(self, obj):
        return obj.lead.name if obj.lead_id else "-"

    @display(description="From ad", boolean=True)
    def ad_referred(self, obj):
        return obj.is_ad_referred

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
