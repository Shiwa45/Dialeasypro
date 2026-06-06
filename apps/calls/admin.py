"""
TeleCRM Backend — apps/calls/admin.py
"""
from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display

from apps.calls.models import CallDisposition, CallLog, CallRecording


@admin.register(CallDisposition)
class CallDispositionAdmin(ModelAdmin):
    list_display = ["name", "slug", "is_positive", "is_active", "sort_order", "auto_followup_hours"]
    list_editable = ["is_active", "sort_order"]
    search_fields = ["name", "slug"]
    ordering = ["sort_order"]


@admin.register(CallLog)
class CallLogAdmin(ModelAdmin):
    list_display = [
        "started_at", "agent_name", "lead_name", "direction_badge",
        "phone_number", "duration_display", "is_connected", "disposition",
        "provider",
    ]
    list_filter = ["direction", "is_connected", "provider", "disposition"]
    search_fields = ["phone_number", "agent__name", "lead__name", "provider_call_id"]
    readonly_fields = [
        "id", "started_at", "connected_at", "ended_at",
        "duration_seconds", "provider_call_id", "provider_meta",
        "call_cost_paise", "created_at",
    ]
    ordering = ["-started_at"]
    date_hierarchy = "started_at"

    def has_add_permission(self, request):
        return False

    @display(description="Agent")
    def agent_name(self, obj):
        return obj.agent.name if obj.agent else "—"

    @display(description="Lead")
    def lead_name(self, obj):
        return obj.lead.name if obj.lead else "—"

    @display(description="Direction")
    def direction_badge(self, obj):
        if obj.direction == "outbound":
            return format_html('<span style="color:#3B82F6">↗ Out</span>')
        return format_html('<span style="color:#10B981">↙ In</span>')

    @display(description="Duration")
    def duration_display(self, obj):
        return obj.duration_display


@admin.register(CallRecording)
class CallRecordingAdmin(ModelAdmin):
    list_display = ["call", "duration_seconds", "format", "transcript_status", "uploaded_at"]
    list_filter = ["transcript_status", "format"]
    readonly_fields = ["call", "file_size_bytes", "duration_seconds", "uploaded_at"]
