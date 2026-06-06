"""
TeleCRM Backend — apps/superadmin/admin.py

Django Admin (Unfold) for AuditLog, GlobalSettings, SupportNote.
"""
from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display

from apps.superadmin.models import AuditLog, GlobalSettings, SupportNote


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    """Read-only audit log viewer. No add/change/delete permissions."""

    list_display = [
        "timestamp",
        "actor_email",
        "actor_type_badge",
        "action_badge",
        "entity_type",
        "entity_repr",
        "tenant_schema",
        "actor_ip",
    ]
    list_filter = ["action", "actor_type", "tenant_schema"]
    search_fields = [
        "actor_email", "entity_repr", "tenant_schema", "description", "actor_ip"
    ]
    readonly_fields = [
        "id", "timestamp", "actor_type", "actor_id", "actor_email",
        "actor_ip", "actor_user_agent", "tenant_schema", "action",
        "entity_type", "entity_id", "entity_repr", "changes", "description",
    ]
    ordering = ["-timestamp"]
    date_hierarchy = "timestamp"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="Actor", ordering="actor_type")
    def actor_type_badge(self, obj):
        colors = {
            "super_admin": "#7C3AED",
            "tenant_admin": "#2563EB",
            "agent": "#059669",
            "system": "#6B7280",
            "api": "#D97706",
        }
        color = colors.get(obj.actor_type, "#6B7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:1px 6px;'
            'border-radius:3px;font-size:10px">{}</span>',
            color, obj.get_actor_type_display(),
        )

    @display(description="Action", ordering="action")
    def action_badge(self, obj):
        danger_actions = ["delete", "suspend", "impersonate"]
        color = "#EF4444" if obj.action in danger_actions else "#374151"
        return format_html(
            '<code style="color:{};font-size:11px">{}</code>',
            color, obj.action,
        )


@admin.register(GlobalSettings)
class GlobalSettingsAdmin(ModelAdmin):
    """Manage platform-wide settings."""

    list_display = ["key", "value_preview", "updated_by", "updated_at"]
    search_fields = ["key", "value", "description"]
    readonly_fields = ["updated_at", "created_at"]
    ordering = ["key"]

    fieldsets = (
        (None, {"fields": ("key", "value", "description", "updated_by")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user.email
        super().save_model(request, obj, form, change)

    @display(description="Value")
    def value_preview(self, obj):
        return obj.value[:80] + "..." if len(obj.value) > 80 else obj.value


@admin.register(SupportNote)
class SupportNoteAdmin(ModelAdmin):
    """Manage internal support notes on tenants."""

    list_display = ["tenant_name", "note_preview", "created_by", "is_pinned", "created_at"]
    list_filter = ["is_pinned"]
    search_fields = ["tenant__company_name", "note", "created_by"]
    raw_id_fields = ["tenant"]
    ordering = ["-is_pinned", "-created_at"]

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user.email
        super().save_model(request, obj, form, change)

    @display(description="Tenant")
    def tenant_name(self, obj):
        return obj.tenant.company_name

    @display(description="Note")
    def note_preview(self, obj):
        return obj.note[:100] + "..." if len(obj.note) > 100 else obj.note
