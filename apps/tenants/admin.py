"""
TeleCRM Backend — apps/tenants/admin.py

Django Admin (Unfold-themed) for Tenant and Domain management.
Accessible only to Django superusers at /superadmin/
"""
from django.contrib import admin
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from apps.core.constants import SubscriptionStatus
from apps.tenants.models import Domain, Tenant


class DomainInline(TabularInline):
    """Show domains inline within Tenant detail view."""

    model = Domain
    extra = 1
    fields = ("domain", "is_primary")
    show_change_link = True


@admin.register(Tenant)
class TenantAdmin(ModelAdmin):
    """
    Full Tenant management in the super admin panel.
    Supports bulk suspend/activate and plan assignment.
    """

    list_display = [
        "company_name_display",
        "schema_name",
        "primary_contact_email",
        "subscription_status_badge",
        "plan_name",
        "total_agents",
        "total_leads",
        "trial_days_left",
        "is_active_badge",
        "created_at",
    ]
    list_filter = [
        "subscription_status",
        "is_active",
        "industry",
        "plan",
        "onboarding_completed",
    ]
    search_fields = [
        "company_name",
        "schema_name",
        "primary_contact_email",
        "primary_contact_phone",
        "gstin",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "total_agents",
        "total_leads",
        "total_calls_today",
    ]

    def get_readonly_fields(self, request, obj=None):
        base = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            # schema_name must not change after creation (would break PG schema)
            base.append("schema_name")
        return base
    ordering = ["-created_at"]
    inlines = [DomainInline]
    actions = ["suspend_tenants", "activate_tenants", "reset_trial", "sync_subscriptions", "send_welcome_emails"]

    def save_model(self, request, obj, form, change):
        """When saving from admin, ensure the Subscription row matches the tenant's plan."""
        super().save_model(request, obj, form, change)
        
        if obj.plan:
            from apps.plans.models import Subscription
            # Find the active subscription and update it, or create one
            sub = Subscription.objects.filter(
                tenant=obj, 
                status__in=SubscriptionStatus.ACTIVE_STATUSES
            ).first()
            
            if sub:
                if sub.plan != obj.plan:
                    sub.plan = obj.plan
                    sub.save(update_fields=["plan"])
            else:
                # No active subscription? Create one to match the tenant status
                Subscription.objects.create(
                    tenant=obj,
                    plan=obj.plan,
                    status=obj.subscription_status,
                    trial_end=obj.trial_ends_at
                )
            
            # Invalidate cache
            from apps.core.middleware import TenantFeatureFlagMiddleware
            TenantFeatureFlagMiddleware.invalidate_cache(obj.schema_name)

    @action(description="Sync Plan to Subscription table")
    def sync_subscriptions(self, request, queryset):
        """Forces the Subscription table to match the Tenant's assigned Plan."""
        from apps.plans.models import Subscription
        from apps.core.middleware import TenantFeatureFlagMiddleware
        
        count = 0
        for tenant in queryset.exclude(schema_name="public"):
            if not tenant.plan:
                continue
                
            sub = Subscription.objects.filter(
                tenant=tenant, 
                status__in=SubscriptionStatus.ACTIVE_STATUSES
            ).first()
            
            if sub:
                sub.plan = tenant.plan
                sub.save(update_fields=["plan"])
            else:
                Subscription.objects.create(
                    tenant=tenant,
                    plan=tenant.plan,
                    status=tenant.subscription_status,
                    trial_end=tenant.trial_ends_at
                )
            
            TenantFeatureFlagMiddleware.invalidate_cache(tenant.schema_name)
            count += 1
            
        self.message_user(request, f"✅ Synced subscriptions for {count} tenant(s).")

    @action(description="Send / Resend Welcome Email")
    def send_welcome_emails(self, request, queryset):
        """
        Manually trigger the welcome email for selected tenants.
        If an admin agent already exists, resets their password to a new temporary one
        (only if they haven't set their own password yet, i.e. must_change_password=True).
        """
        from apps.tenants.signals import _create_default_tenant_admin, _generate_temp_password
        from apps.tenants.tasks import send_tenant_welcome_email
        from django.db import connection
        from django.contrib import messages
        
        count = 0
        for tenant in queryset.exclude(schema_name="public"):
            if not tenant.primary_contact_email:
                continue
                
            previous_schema = connection.schema_name
            temp_password = None
            
            try:
                connection.set_schema(tenant.schema_name)
                from apps.authentication.models import Agent
                
                admin_agent = Agent.objects.filter(is_tenant_admin=True).first()
                if not admin_agent:
                    # Admin doesn't exist, create it (this sets tenant._temp_admin_password)
                    _create_default_tenant_admin(tenant)
                    temp_password = getattr(tenant, "_temp_admin_password", None)
                else:
                    # Admin exists. If they haven't set their own password yet, we can reset it safely.
                    if admin_agent.must_change_password:
                        temp_password = _generate_temp_password()
                        admin_agent.set_password(temp_password)
                        admin_agent.save(update_fields=["password"])
                    else:
                        # User has already set their own password, don't overwrite it.
                        # We just send the email without the temp_password (it will say '[Check your registration email]').
                        temp_password = None
                        
                # Queue the email
                send_tenant_welcome_email.apply_async(
                    kwargs={
                        "tenant_id": tenant.pk,
                        "temp_password": temp_password,
                    },
                    queue="notifications",
                )
                count += 1
                        
            except Exception as e:
                self.message_user(request, f"❌ Failed to process {tenant.schema_name}: {e}", level=messages.ERROR)
                continue
            finally:
                connection.set_schema(previous_schema)
            
        self.message_user(request, f"✅ Queued welcome emails for {count} tenant(s).", level=messages.SUCCESS)

    fieldsets = (
        (
            "Company Information",
            {
                "fields": (
                    "company_name",
                    "schema_name",
                    "industry",
                    "gstin",
                    "logo",
                )
            },
        ),
        (
            "Billing Address",
            {
                "fields": ("billing_address", "city", "state", "pincode"),
                "classes": ("collapse",),
            },
        ),
        (
            "Primary Contact",
            {
                "fields": (
                    "primary_contact_name",
                    "primary_contact_email",
                    "primary_contact_phone",
                )
            },
        ),
        (
            "Plan & Subscription",
            {
                "fields": (
                    "plan",
                    "subscription_status",
                    "trial_ends_at",
                    "is_active",
                )
            },
        ),
        (
            "Onboarding",
            {
                "fields": ("onboarding_completed", "onboarding_step"),
                "classes": ("collapse",),
            },
        ),
        (
            "Branding",
            {
                "fields": ("primary_color", "custom_domain"),
                "classes": ("collapse",),
            },
        ),
        (
            "Locale",
            {
                "fields": ("timezone", "language_preference"),
                "classes": ("collapse",),
            },
        ),
        (
            "Usage Statistics",
            {
                "fields": ("total_agents", "total_leads", "total_calls_today"),
                "classes": ("collapse",),
            },
        ),
        (
            "Internal Notes",
            {
                "fields": ("internal_notes",),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    # ---- Custom Display Columns ----------------------------

    @display(description="Company", ordering="company_name")
    def company_name_display(self, obj):
        return format_html(
            '<strong>{}</strong><br><small style="color:#888">{}</small>',
            obj.company_name,
            obj.schema_name,
        )

    @display(description="Status", ordering="subscription_status")
    def subscription_status_badge(self, obj):
        colors = {
            SubscriptionStatus.TRIAL: "#F59E0B",
            SubscriptionStatus.ACTIVE: "#10B981",
            SubscriptionStatus.PAST_DUE: "#EF4444",
            SubscriptionStatus.PAUSED: "#6B7280",
            SubscriptionStatus.CANCELLED: "#EF4444",
            SubscriptionStatus.SUSPENDED: "#DC2626",
        }
        color = colors.get(obj.subscription_status, "#6B7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            color,
            obj.get_subscription_status_display(),
        )

    @display(description="Plan")
    def plan_name(self, obj):
        if obj.plan:
            return obj.plan.name
        return format_html('<span style="color:#9CA3AF">—</span>')

    @display(description="Trial Days")
    def trial_days_left(self, obj):
        if not obj.is_trial:
            return "—"
        days = obj.trial_days_remaining
        color = "#EF4444" if days <= 3 else "#F59E0B" if days <= 7 else "#10B981"
        return format_html(
            '<span style="color:{};font-weight:600">{} days</span>', color, days
        )

    @display(description="Active", boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active

    # ---- Bulk Actions --------------------------------------

    @action(description="Suspend selected tenants")
    def suspend_tenants(self, request, queryset):
        count = 0
        for tenant in queryset.exclude(schema_name="public"):
            tenant.suspend(reason=f"Suspended by super admin: {request.user.email}")
            count += 1
        self.message_user(request, f"✅ {count} tenant(s) suspended.")

    @action(description="Activate selected tenants")
    def activate_tenants(self, request, queryset):
        count = 0
        for tenant in queryset.exclude(schema_name="public"):
            tenant.activate()
            count += 1
        self.message_user(request, f"✅ {count} tenant(s) activated.")

    @action(description="Reset trial (14 days)")
    def reset_trial(self, request, queryset):
        count = 0
        for tenant in queryset.exclude(schema_name="public"):
            tenant.set_trial(days=14)
            count += 1
        self.message_user(request, f"✅ Trial reset for {count} tenant(s).")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .exclude(schema_name="public")
            .select_related("plan")
        )


@admin.register(Domain)
class DomainAdmin(ModelAdmin):
    """Manage domain-to-tenant mappings."""

    list_display = ["domain", "tenant_name", "is_primary"]
    list_filter = ["is_primary"]
    search_fields = ["domain", "tenant__company_name", "tenant__schema_name"]
    raw_id_fields = ["tenant"]

    @display(description="Tenant")
    def tenant_name(self, obj):
        return obj.tenant.company_name
