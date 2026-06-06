"""
TeleCRM Backend — apps/authentication/admin.py

Unfold-themed Django admin for Agent, Team, and AgentLoginSession.

NOTE: These models live in TENANT schemas, not public.
      This admin is useful for super admins who need to inspect
      individual tenant schemas. In production most tenant management
      is done via the MVT web UI at /crm/.
"""
from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from apps.authentication.models import Agent, AgentLoginSession, AgentTeam, Team
from apps.core.constants import AgentRole


class AgentTeamInline(TabularInline):
    """Show team memberships inline within Agent detail."""
    model = AgentTeam
    extra = 0
    fields = ("team", "is_team_lead", "joined_at")
    readonly_fields = ("joined_at",)


class AgentLoginSessionInline(TabularInline):
    """Show recent login sessions inline within Agent detail."""
    model = AgentLoginSession
    extra = 0
    fields = ("login_time", "logout_time", "ip_address", "device_type", "is_active")
    readonly_fields = ("login_time", "logout_time", "ip_address", "device_type")
    ordering = ("-login_time",)
    max_num = 10
    can_delete = False


@admin.register(Agent)
class AgentAdmin(ModelAdmin):
    """Agent management — per-tenant."""

    list_display = [
        "name",
        "email",
        "role_badge",
        "is_active_display",
        "is_tenant_admin",
        "online_status",
        "total_login_count",
        "last_login",
    ]
    list_filter = ["role", "is_active", "is_tenant_admin"]
    search_fields = ["email", "name", "phone", "employee_id"]
    readonly_fields = [
        "last_login",
        "last_login_ip",
        "total_login_count",
        "last_active_at",
        "created_at",
        "updated_at",
    ]
    ordering = ["name"]
    inlines = [AgentTeamInline, AgentLoginSessionInline]
    actions = ["activate_agents", "deactivate_agents", "force_password_change"]

    fieldsets = (
        (
            "Identity",
            {"fields": ("email", "name", "phone", "employee_id", "profile_photo")},
        ),
        (
            "Role & Permissions",
            {"fields": ("role", "is_tenant_admin", "is_active")},
        ),
        (
            "Security",
            {
                "fields": ("must_change_password", "last_login", "last_login_ip", "total_login_count"),
                "classes": ("collapse",),
            },
        ),
        (
            "Schedule",
            {
                "fields": ("shift_start", "shift_end", "working_days"),
                "classes": ("collapse",),
            },
        ),
        (
            "Locale",
            {"fields": ("timezone", "language_preference"), "classes": ("collapse",)},
        ),
        (
            "Activity",
            {
                "fields": ("last_active_at", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @display(description="Role", ordering="role")
    def role_badge(self, obj):
        colors = {
            AgentRole.ADMIN: "#7C3AED",
            AgentRole.MANAGER: "#2563EB",
            AgentRole.SENIOR_AGENT: "#059669",
            AgentRole.AGENT: "#374151",
            AgentRole.TRAINEE: "#9CA3AF",
        }
        color = colors.get(obj.role, "#374151")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px">{}</span>',
            color,
            obj.get_role_display(),
        )

    @display(description="Active", boolean=True)
    def is_active_display(self, obj):
        return obj.is_active

    @display(description="Online")
    def online_status(self, obj):
        if obj.is_online:
            return format_html(
                '<span style="color:#10B981;font-weight:700">● Online</span>'
            )
        return format_html('<span style="color:#9CA3AF">○ Offline</span>')

    @action(description="Activate selected agents")
    def activate_agents(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"✅ {count} agent(s) activated.")

    @action(description="Deactivate selected agents")
    def deactivate_agents(self, request, queryset):
        # Don't deactivate tenant admins via bulk action
        count = queryset.filter(is_tenant_admin=False).update(is_active=False)
        self.message_user(request, f"✅ {count} agent(s) deactivated.")

    @action(description="Force password change on next login")
    def force_password_change(self, request, queryset):
        count = queryset.update(must_change_password=True)
        self.message_user(request, f"✅ Password change required for {count} agent(s).")


@admin.register(Team)
class TeamAdmin(ModelAdmin):
    """Team management."""

    list_display = ["name", "member_count_display", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    ordering = ["name"]

    @display(description="Members")
    def member_count_display(self, obj):
        return obj.member_count


@admin.register(AgentLoginSession)
class AgentLoginSessionAdmin(ModelAdmin):
    """Read-only login session history."""

    list_display = [
        "agent_name",
        "login_time",
        "logout_time",
        "ip_address",
        "device_type",
        "is_active",
    ]
    list_filter = ["is_active", "device_type"]
    search_fields = ["agent__email", "agent__name", "ip_address"]
    readonly_fields = [
        "agent", "login_time", "logout_time", "ip_address",
        "user_agent", "device_type", "is_active", "jwt_jti",
    ]
    ordering = ["-login_time"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @display(description="Agent")
    def agent_name(self, obj):
        return obj.agent.name
