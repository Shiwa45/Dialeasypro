"""
TeleCRM Backend — apps/plans/admin.py

Django Admin (Unfold) for Plans, Subscriptions, and Invoices.
"""
from django.contrib import admin
from django.db.models import Count, Q
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from apps.core.constants import FeatureKey, SubscriptionStatus
from apps.tenants.models import Tenant
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

    def delete_queryset(self, request, queryset):
        # "Delete selected" skips delete_model: without this a revoked add-on
        # kept working for up to five minutes (the feature cache's lifetime).
        tenants = {e.tenant for e in queryset.select_related("tenant")}
        super().delete_queryset(request, queryset)
        for tenant in tenants:
            TenantEntitlement._invalidate(tenant)




def _invalidate_plan_tenants(plan) -> None:
    """
    Drop the cached feature map of every tenant on this plan. Editing a
    plan's features in the panel used to take up to five minutes to reach
    its tenants (the cache's lifetime).
    """
    from apps.core.middleware import TenantFeatureFlagMiddleware
    from apps.plans.models import Subscription
    from apps.tenants.models import Tenant

    schemas = set(Subscription.objects.filter(plan=plan).values_list("tenant__schema_name", flat=True))
    schemas |= set(Tenant.objects.filter(plan=plan).values_list("schema_name", flat=True))
    for schema in schemas:
        TenantFeatureFlagMiddleware.invalidate_cache(schema)

def _missing_feature_keys(plan) -> list[str]:
    """Features this plan has no row for (a missing row means "off")."""
    have = set(plan.features.values_list("feature_key", flat=True)) if plan and plan.pk else set()
    return [key for key in FeatureKey.ALL if key not in have]


class PlanFeatureInline(TabularInline):
    """
    Every feature on the plan page, one row each.

    Only features that already had a row were listed, so a feature added to
    the product later (Recruitment, Agent Web Panel...) could not be switched
    on from the plan page at all, and a new plan opened with 64 blank rows
    whose feature had to be picked by hand. The missing ones are now listed
    pre-filled and switched off; ticking one saves it, leaving it unticked
    saves nothing.
    """

    model = PlanFeature
    extra = 0
    fields = ("feature_key", "is_enabled")
    ordering = ("feature_key",)

    def get_extra(self, request, obj=None, **kwargs):
        return len(_missing_feature_keys(obj))


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

    def get_formset_kwargs(self, request, obj, inline, prefix):
        kwargs = super().get_formset_kwargs(request, obj, inline, prefix)
        if isinstance(inline, PlanFeatureInline):
            kwargs["initial"] = [
                {"feature_key": key, "is_enabled": False} for key in _missing_feature_keys(obj)
            ]
        return kwargs

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _features_on=Count("features", filter=Q(features__is_enabled=True)),
        )

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
        # Out of every feature the product has, not out of the rows this plan
        # happens to have: Starter read "9/10" — nearly everything — while it
        # has 9 of 64.
        count = getattr(obj, "_features_on", None)
        if count is None:
            count = obj.features.filter(is_enabled=True).count()
        return format_html(
            '<span style="color:#6B7280">{}/{}</span>', count, len(FeatureKey.ALL)
        )

    @display(description="Active", boolean=True)
    def is_active_display(self, obj):
        return obj.is_active

    actions = ["sync_all_features"]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        _invalidate_plan_tenants(form.instance)

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
            _invalidate_plan_tenants(plan)

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

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        _invalidate_plan_tenants(obj.plan)

    def delete_model(self, request, obj):
        plan = obj.plan
        super().delete_model(request, obj)
        _invalidate_plan_tenants(plan)

    def delete_queryset(self, request, queryset):
        # "Delete selected" skips delete_model, so tenants kept the deleted
        # features for up to five minutes.
        plans = {pf.plan for pf in queryset.select_related("plan")}
        super().delete_queryset(request, queryset)
        for plan in plans:
            _invalidate_plan_tenants(plan)


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

    def save_model(self, request, obj, form, change):
        """
        Keep the tenant's plan in step and make the change take effect now.
        The sync signal only ran on a status change, so moving a subscription
        to another plan left the tenant on the old one for up to five minutes
        (and Tenant.plan wrong for good). A subscription made usable here does
        not lift a super-admin suspension: Tenant.is_active stays off.
        """
        super().save_model(request, obj, form, change)
        tenant = obj.tenant
        if obj.status in SubscriptionStatus.ACTIVE_STATUSES and tenant.plan_id != obj.plan_id:
            Tenant.objects.filter(pk=tenant.pk).update(plan=obj.plan)
        from apps.core.middleware import TenantFeatureFlagMiddleware

        TenantFeatureFlagMiddleware.invalidate_cache(tenant.schema_name)

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
