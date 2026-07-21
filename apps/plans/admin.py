"""
TeleCRM Backend — apps/plans/admin.py

Django Admin (Unfold) for Plans, Subscriptions, and Invoices.
"""
from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from apps.core.constants import FeatureKey, SubscriptionStatus
from apps.plans.models import (
    Invoice,
    Plan,
    PlanFeature,
    Subscription,
    TenantEntitlement,
)


@admin.register(TenantEntitlement)
class TenantEntitlementAdmin(ModelAdmin):
    """
    Per-tenant feature grants/revokes layered over the plan — this is how
    add-on modules (HRMS / ERP / AI Suite) are sold without changing tier.
    """

    list_display = ["tenant", "feature_key", "is_enabled", "module_key", "expires_at"]
    list_filter = ["is_enabled", "module_key", "feature_key"]
    search_fields = ["tenant__company_name", "tenant__schema_name", "feature_key"]
    raw_id_fields = ["tenant"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Feature maps are cached in Redis — drop it so the change is immediate.
        TenantEntitlement._invalidate(obj.tenant)

    def delete_model(self, request, obj):
        tenant = obj.tenant
        super().delete_model(request, obj)
        TenantEntitlement._invalidate(tenant)


class PlanFeatureInline(TabularInline):
    """Edit plan features inline within Plan detail."""

    model = PlanFeature
    extra = 0
    fields = ("feature_key", "is_enabled")
    ordering = ("feature_key",)

    def get_extra(self, request, obj=None, **kwargs):
        # Show all features as rows for a new plan
        return 0 if obj else len(FeatureKey.ALL)


@admin.register(Plan)
class PlanAdmin(ModelAdmin):
    """Plan management — create and configure subscription tiers."""

    list_display = [
        "name",
        "slug",
        "price_monthly_display",
        "price_yearly_display",
        "max_agents",
        "max_leads",
        "storage_gb",
        "feature_count",
        "is_active",
        "is_public",
        "sort_order",
    ]
    list_filter = ["is_active", "is_public"]
    list_editable = ["sort_order", "is_active", "is_public"]
    search_fields = ["name", "slug"]
    ordering = ["sort_order"]
    inlines = [PlanFeatureInline]

    fieldsets = (
        (
            "Plan Details",
            {"fields": ("name", "slug", "description", "sort_order")},
        ),
        (
            "Pricing (INR, pre-GST)",
            {
                "fields": ("price_monthly", "price_yearly"),
                "description": "GST (18%) is added on top during invoicing.",
            },
        ),
        (
            "Razorpay Plan IDs",
            {
                "fields": ("razorpay_monthly_plan_id", "razorpay_yearly_plan_id"),
                "classes": ("collapse",),
                "description": "Create these in the Razorpay Dashboard and paste IDs here.",
            },
        ),
        (
            "Capacity Limits",
            {
                "fields": (
                    "max_agents",
                    "max_leads",
                    "max_leads_per_day",
                    "max_whatsapp_bulk_per_day",
                    "max_email_bulk_per_day",
                    "max_sms_per_day",
                    "storage_gb",
                    "custom_fields_limit",
                    "lead_sources_limit",
                    "whatsapp_templates_limit",
                    "data_retention_days",
                ),
            },
        ),
        (
            "Visibility",
            {"fields": ("is_active", "is_public")},
        ),
    )

    @display(description="Monthly Price")
    def price_monthly_display(self, obj):
        if obj.price_monthly == 0:
            return format_html('<span style="color:#6B7280">Custom</span>')
        return f"₹{obj.price_monthly:,.0f}"

    @display(description="Yearly Price")
    def price_yearly_display(self, obj):
        if obj.price_yearly == 0:
            return "—"
        savings = obj.yearly_savings_percent
        formatted_price = f"₹{obj.price_yearly:,.0f}"
        return format_html(
            "{} <small style='color:#10B981'>({}% off)</small>",
            formatted_price,
            savings,
        )

    @display(description="Features")
    def feature_count(self, obj):
        count = obj.features.filter(is_enabled=True).count()
        total = obj.features.count()
        return format_html(
            '<span style="color:#6B7280">{}/{}</span>', count, total
        )

    @display(description="Active", boolean=True)
    def is_active_display(self, obj):
        return obj.is_active

    actions = ["sync_all_features"]

    @action(description="Sync all available features to selected plans (disabled by default)")
    def sync_all_features(self, request, queryset):
        """
        For each selected plan, checks all known FeatureKeys.
        If a feature is missing from the plan, creates it as disabled by default.
        """
        from apps.core.constants import FeatureKey
        from apps.plans.models import PlanFeature

        features_created = 0
        plans_updated = 0

        for plan in queryset:
            existing_features = set(plan.features.values_list("feature_key", flat=True))
            new_features = []
            
            for key in FeatureKey.ALL:
                if key not in existing_features:
                    # Enable ALL features if it's the Business or Enterprise plan
                    # Otherwise default to False so they can be manually enabled
                    is_enabled = plan.slug in ["business", "enterprise"]
                    new_features.append(
                        PlanFeature(plan=plan, feature_key=key, is_enabled=is_enabled)
                    )
            
            if new_features:
                PlanFeature.objects.bulk_create(new_features)
                features_created += len(new_features)
                plans_updated += 1
                
            # Clear feature cache for any tenants on this plan
            from apps.core.middleware import TenantFeatureFlagMiddleware
            from apps.plans.models import Subscription
            for sub in Subscription.objects.filter(plan=plan):
                TenantFeatureFlagMiddleware.invalidate_cache(sub.tenant.schema_name)

        self.message_user(
            request,
            f"Successfully synced features for {plans_updated} plans. "
            f"Added {features_created} new feature flags.",
        )


@admin.register(PlanFeature)
class PlanFeatureAdmin(ModelAdmin):
    """Manage individual plan features."""

    list_display = ["feature_label", "plan", "is_enabled"]
    list_filter = ["plan", "is_enabled"]
    list_editable = ["is_enabled"]
    search_fields = ["feature_key", "plan__name"]
    ordering = ["plan__sort_order", "feature_key"]

    @display(description="Feature")
    def feature_label(self, obj):
        return FeatureKey.LABELS.get(obj.feature_key, obj.feature_key)


@admin.register(Subscription)
class SubscriptionAdmin(ModelAdmin):
    """View and manage tenant subscriptions."""

    list_display = [
        "tenant_name",
        "plan_name",
        "status_badge",
        "billing_cycle",
        "current_period_end",
        "cancel_at_period_end",
        "razorpay_subscription_id",
        "created_at",
    ]
    list_filter = ["status", "billing_cycle", "plan"]
    search_fields = [
        "tenant__company_name",
        "tenant__schema_name",
        "razorpay_subscription_id",
    ]
    readonly_fields = [
        "id",
        "razorpay_subscription_id",
        "razorpay_customer_id",
        "created_at",
        "updated_at",
    ]
    raw_id_fields = ["tenant"]
    ordering = ["-created_at"]

    fieldsets = (
        ("Subscription", {"fields": ("id", "tenant", "plan", "status", "billing_cycle")}),
        (
            "Razorpay",
            {
                "fields": ("razorpay_subscription_id", "razorpay_customer_id"),
                "classes": ("collapse",),
            },
        ),
        (
            "Period",
            {
                "fields": (
                    "current_period_start",
                    "current_period_end",
                    "trial_end",
                    "cancel_at_period_end",
                    "cancelled_at",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @display(description="Tenant")
    def tenant_name(self, obj):
        return obj.tenant.company_name

    @display(description="Plan")
    def plan_name(self, obj):
        return obj.plan.name

    @display(description="Status", ordering="status")
    def status_badge(self, obj):
        colors = {
            SubscriptionStatus.TRIAL: "#F59E0B",
            SubscriptionStatus.ACTIVE: "#10B981",
            SubscriptionStatus.PAST_DUE: "#EF4444",
            SubscriptionStatus.CANCELLED: "#6B7280",
            SubscriptionStatus.SUSPENDED: "#DC2626",
        }
        color = colors.get(obj.status, "#6B7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px">{}</span>',
            color,
            obj.get_status_display(),
        )


@admin.register(Invoice)
class InvoiceAdmin(ModelAdmin):
    """GST invoice management."""

    list_display = [
        "invoice_number",
        "tenant_name",
        "base_amount",
        "total_amount",
        "payment_status_badge",
        "invoice_date",
        "billing_period_display",
        "razorpay_payment_id",
    ]
    list_filter = ["payment_status", "is_interstate", "invoice_date"]
    search_fields = [
        "invoice_number",
        "tenant__company_name",
        "razorpay_payment_id",
        "razorpay_order_id",
    ]
    readonly_fields = [
        "id",
        "invoice_number",
        "razorpay_payment_id",
        "razorpay_order_id",
        "paid_at",
        "created_at",
    ]
    ordering = ["-invoice_date"]

    @display(description="Tenant")
    def tenant_name(self, obj):
        return obj.tenant.company_name

    @display(description="Payment Status")
    def payment_status_badge(self, obj):
        colors = {
            "paid": "#10B981",
            "pending": "#F59E0B",
            "failed": "#EF4444",
            "refunded": "#6B7280",
        }
        color = colors.get(obj.payment_status, "#6B7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px">{}</span>',
            color,
            obj.get_payment_status_display(),
        )

    @display(description="Period")
    def billing_period_display(self, obj):
        if obj.billing_period_start and obj.billing_period_end:
            return f"{obj.billing_period_start} → {obj.billing_period_end}"
        return "—"
