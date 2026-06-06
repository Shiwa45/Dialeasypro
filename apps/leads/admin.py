"""
TeleCRM Backend — apps/leads/admin.py

Unfold-themed Django admin for Lead management.
Primarily used by super admins for support/debugging.
Tenant admins use the MVT web UI at /crm/leads/.
"""
from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from apps.leads.models import (
    CustomField,
    CustomFieldValue,
    FollowUp,
    Lead,
    LeadActivity,
    LeadImportJob,
    LeadNote,
)
from apps.core.constants import LeadPriority, LeadStatus


class FollowUpInline(TabularInline):
    model = FollowUp
    extra = 0
    fields = ("followup_type", "scheduled_at", "is_completed", "notes")
    readonly_fields = ("completed_at",)
    ordering = ("scheduled_at",)
    max_num = 10


class LeadNoteInline(TabularInline):
    model = LeadNote
    extra = 0
    fields = ("agent", "content", "is_pinned", "created_at")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
    max_num = 10


class CustomFieldValueInline(TabularInline):
    model = CustomFieldValue
    extra = 0
    fields = ("field", "value")
    max_num = 20


@admin.register(Lead)
class LeadAdmin(ModelAdmin):
    list_display = [
        "name",
        "phone_masked",
        "status_badge",
        "priority_badge",
        "source",
        "assigned_to_name",
        "score",
        "next_followup_display",
        "created_at",
    ]
    list_filter = ["status", "priority", "source", "is_deleted", "is_dnd"]
    search_fields = ["name", "phone", "email", "city"]
    readonly_fields = [
        "created_at", "updated_at", "last_contacted_at",
        "contact_count", "assigned_at",
    ]
    ordering = ["-created_at"]
    inlines = [FollowUpInline, LeadNoteInline, CustomFieldValueInline]
    actions = ["assign_to_me", "mark_as_lost"]

    fieldsets = (
        ("Contact", {"fields": ("name", "phone", "alternate_phone", "email")}),
        ("Location", {"fields": ("city", "state", "pincode", "address"), "classes": ("collapse",)}),
        ("Classification", {"fields": ("source", "status", "priority", "tags", "score")}),
        ("Assignment", {"fields": ("assigned_to", "territory_manager", "assigned_at")}),
        ("Sales", {"fields": ("budget", "requirement", "deal_value", "expected_close_date"), "classes": ("collapse",)}),
        ("Pipeline", {"fields": ("pipeline_stage", "next_followup_at", "last_contacted_at", "contact_count"), "classes": ("collapse",)}),
        ("Flags", {"fields": ("is_dnd", "is_deleted")}),
        ("Source Metadata", {"fields": ("source_meta", "source_lead_id"), "classes": ("collapse",)}),
    )

    @display(description="Phone")
    def phone_masked(self, obj):
        from apps.core.utils import mask_phone_number
        return mask_phone_number(obj.phone)

    @display(description="Status", ordering="status")
    def status_badge(self, obj):
        colors = {
            LeadStatus.NEW: "#6366F1",
            LeadStatus.ATTEMPTED: "#F59E0B",
            LeadStatus.CONTACTED: "#3B82F6",
            LeadStatus.INTERESTED: "#10B981",
            LeadStatus.FOLLOW_UP: "#8B5CF6",
            LeadStatus.NEGOTIATION: "#F97316",
            LeadStatus.WON: "#059669",
            LeadStatus.LOST: "#EF4444",
            LeadStatus.NOT_INTERESTED: "#9CA3AF",
        }
        color = colors.get(obj.status, "#6B7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            color, obj.get_status_display(),
        )

    @display(description="Priority")
    def priority_badge(self, obj):
        colors = {LeadPriority.HOT: "#EF4444", LeadPriority.WARM: "#F59E0B", LeadPriority.COLD: "#6B7280"}
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            colors.get(obj.priority, "#374151"), obj.get_priority_display(),
        )

    @display(description="Agent")
    def assigned_to_name(self, obj):
        return obj.assigned_to.name if obj.assigned_to else "—"

    @display(description="Next Follow-up")
    def next_followup_display(self, obj):
        if not obj.next_followup_at:
            return "—"
        if obj.followup_overdue:
            return format_html('<span style="color:#EF4444;font-weight:600">⚠ OVERDUE</span>')
        return obj.next_followup_at.strftime("%d %b %H:%M")


@admin.register(CustomField)
class CustomFieldAdmin(ModelAdmin):
    list_display = ["name", "field_key", "field_type", "is_required", "is_active", "sort_order"]
    list_editable = ["is_active", "sort_order"]
    search_fields = ["name", "field_key"]
    ordering = ["sort_order"]


@admin.register(LeadImportJob)
class LeadImportJobAdmin(ModelAdmin):
    list_display = [
        "original_filename", "imported_by_name", "status", "progress_display",
        "total_rows", "successful_rows", "failed_rows", "created_at",
    ]
    list_filter = ["status"]
    readonly_fields = [
        "id", "file", "original_filename", "total_rows", "processed_rows",
        "successful_rows", "failed_rows", "duplicate_rows", "row_errors",
        "completed_at", "celery_task_id", "created_at",
    ]

    def has_add_permission(self, request):
        return False

    @display(description="Imported By")
    def imported_by_name(self, obj):
        return obj.imported_by.name if obj.imported_by else "—"

    @display(description="Progress")
    def progress_display(self, obj):
        pct = obj.progress_percent
        color = "#10B981" if pct == 100 else "#3B82F6"
        return format_html(
            '<div style="width:80px;background:#E5E7EB;border-radius:4px">'
            '<div style="width:{}%;background:{};height:8px;border-radius:4px"></div>'
            '</div> {}%', pct, color, pct,
        )
