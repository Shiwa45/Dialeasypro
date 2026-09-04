"""TeleCRM Backend — apps/integrations/admin.py"""
from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from apps.integrations.models import LeadSourceConfig, MetaWhatsAppEvent, WebhookLog


@admin.register(LeadSourceConfig)
class LeadSourceConfigAdmin(ModelAdmin):
    list_display = ["source", "is_active", "status", "total_leads_received", "last_received_at"]
    list_editable = ["is_active"]
    search_fields = ["source"]

    def get_exclude(self, request, obj=None):
        # Exclude credentials from non-superusers
        if not request.user.is_superuser:
            return ["credentials"]
        return []


@admin.register(WebhookLog)
class WebhookLogAdmin(ModelAdmin):
    list_display = ["source", "processed", "leads_created", "leads_updated", "error", "created_at"]
    list_filter = ["source", "processed"]
    readonly_fields = ["id", "source", "config", "method", "headers", "payload",
                       "processed", "leads_created", "leads_updated", "error", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MetaWhatsAppEvent)
class MetaWhatsAppEventAdmin(ModelAdmin):
    """
    The Click-to-WhatsApp idempotency ledger — read-only by design.

    Deleting a row here would let Meta's next retry of that event create a
    second lead, so the ledger is not editable from the admin at all. Use it to
    answer "did we receive that message, and what did it do?".
    """

    list_display = ["message_id", "kind", "status", "created_lead", "lead", "processed_at"]
    list_filter = ["kind", "status", "created_lead"]
    search_fields = ["message_id", "dedupe_key"]
    readonly_fields = [
        "id", "dedupe_key", "message_id", "kind", "status", "lead",
        "conversation_id", "created_lead", "webhook_log", "error",
        "processed_at", "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
