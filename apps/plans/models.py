"""
TeleCRM Backend — apps/plans/models.py

Subscription and billing models.
All in the PUBLIC schema (accessible from any tenant context).

Plan          → Defines a subscription tier (Starter/Growth/Business/Enterprise)
PlanFeature   → Feature flags enabled/disabled per plan
Subscription  → A tenant's active subscription to a plan
Invoice       → GST-compliant invoice for each billing cycle (Indian tax law)
"""
import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.constants import (
    FeatureKey,
    GSTState,
    ModuleKey,
    PlanSlug,
    SubscriptionStatus,
)
from apps.core.models import SortableModel, TimeStampedModel


class Plan(TimeStampedModel, SortableModel):
    """
    A subscription plan tier.
    All capacity limits enforced here — agents, leads, bulk messages, storage.
    """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=50, unique=True, choices=PlanSlug.CHOICES)
    description = models.TextField(blank=True, default="")

    # ---- Pricing (INR) ------------------------------------
    price_monthly = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Monthly price in INR (pre-GST).",
    )
    price_yearly = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Yearly price in INR (pre-GST). Usually ~20% discount.",
    )

    # ---- Razorpay Plan IDs (created in Razorpay dashboard) --
    razorpay_monthly_plan_id = models.CharField(max_length=100, blank=True, default="")
    razorpay_yearly_plan_id = models.CharField(max_length=100, blank=True, default="")

    # ---- Capacity Limits ----------------------------------
    max_agents = models.PositiveIntegerField(
        default=5, help_text="Max number of agents allowed."
    )
    max_leads = models.PositiveIntegerField(
        default=5000, help_text="Max total leads stored."
    )
    max_leads_per_day = models.PositiveIntegerField(
        default=200, help_text="Max new leads per day (from all sources)."
    )
    max_whatsapp_bulk_per_day = models.PositiveIntegerField(
        default=0, help_text="Max WhatsApp bulk messages per day."
    )
    max_email_bulk_per_day = models.PositiveIntegerField(
        default=0, help_text="Max bulk emails per day."
    )
    max_sms_per_day = models.PositiveIntegerField(
        default=0, help_text="Max SMS per day."
    )
    storage_gb = models.PositiveIntegerField(
        default=5, help_text="Storage limit in GB (call recordings, attachments)."
    )
    custom_fields_limit = models.PositiveIntegerField(
        default=10, help_text="Max custom CRM fields allowed."
    )
    lead_sources_limit = models.PositiveIntegerField(
        default=2, help_text="Max lead source integrations enabled simultaneously."
    )
    whatsapp_templates_limit = models.PositiveIntegerField(
        default=5, help_text="Max saved WhatsApp message templates."
    )
    data_retention_days = models.PositiveIntegerField(
        default=180, help_text="Days to retain lead/call data before archiving."
    )

    # ---- Display & Availability ---------------------------
    is_active = models.BooleanField(
        default=True, db_index=True, help_text="Inactive plans cannot be selected."
    )
    is_public = models.BooleanField(
        default=True,
        help_text="Show on public pricing page. Enterprise plans are typically private.",
    )

    class Meta:
        verbose_name = "Plan"
        verbose_name_plural = "Plans"
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.name} (₹{self.price_monthly}/mo)"

    @property
    def yearly_savings_percent(self) -> int:
        """Calculate discount percentage for yearly plan."""
        if not self.price_monthly or not self.price_yearly:
            return 0
        monthly_equivalent = self.price_monthly * 12
        if monthly_equivalent == 0:
            return 0
        savings = ((monthly_equivalent - self.price_yearly) / monthly_equivalent) * 100
        return int(savings)

    def get_feature_dict(self) -> dict:
        """Return all features for this plan as {feature_key: is_enabled}."""
        return {
            pf.feature_key: pf.is_enabled
            for pf in self.features.all()
        }


class PlanFeature(models.Model):
    """
    A feature flag for a specific plan.
    Allows granular feature gating per plan tier.
    """

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="features")
    feature_key = models.CharField(
        max_length=100,
        choices=FeatureKey.CHOICES,
        help_text="Feature identifier from FeatureKey constants.",
    )
    is_enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = ("plan", "feature_key")
        verbose_name = "Plan Feature"
        verbose_name_plural = "Plan Features"
        ordering = ["feature_key"]

    def __str__(self):
        status = "✅" if self.is_enabled else "❌"
        label = FeatureKey.LABELS.get(self.feature_key, self.feature_key)
        return f"{status} {self.plan.name} — {label}"


class TenantEntitlement(TimeStampedModel):
    """
    A per-tenant feature grant or revoke, layered ON TOP of the plan's features.

    This is what makes add-on modules sellable independently of the plan tier
    ("Growth plan + HRMS module"). Resolution order, computed in
    TenantFeatureFlagMiddleware:

        effective = plan's PlanFeature set, then entitlements applied over it

    An entitlement with is_enabled=False explicitly REVOKES a feature the plan
    would otherwise grant (useful for abuse control or bespoke deals).
    Expired rows are ignored entirely.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="entitlements"
    )
    feature_key = models.CharField(
        max_length=100,
        choices=FeatureKey.CHOICES,
        db_index=True,
        help_text="Feature identifier from FeatureKey constants.",
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text="True = grant this feature. False = explicitly revoke it.",
    )
    module_key = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Which add-on module granted this (provenance, for bulk revoke).",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this entitlement lapses. Null = never expires.",
    )
    note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        unique_together = ("tenant", "feature_key")
        verbose_name = "Tenant Entitlement"
        verbose_name_plural = "Tenant Entitlements"
        ordering = ["tenant", "feature_key"]
        indexes = [
            models.Index(fields=["tenant", "feature_key"], name="entl_tenant_feature_idx"),
        ]

    def __str__(self):
        state = "grant" if self.is_enabled else "revoke"
        label = FeatureKey.LABELS.get(self.feature_key, self.feature_key)
        return f"{self.tenant.schema_name}: {state} {label}"

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now())

    # ---- Module helpers ------------------------------------

    @classmethod
    def grant_module(cls, tenant, module_key: str, expires_at=None, note: str = ""):
        """Grant every feature in a module to a tenant. Returns rows touched."""
        keys = ModuleKey.FEATURES.get(module_key)
        if not keys:
            raise ValueError(f"Unknown module: {module_key}")
        rows = []
        for key in keys:
            row, _ = cls.objects.update_or_create(
                tenant=tenant,
                feature_key=key,
                defaults={
                    "is_enabled": True,
                    "module_key": module_key,
                    "expires_at": expires_at,
                    "note": note,
                },
            )
            rows.append(row)
        cls._invalidate(tenant)
        return rows

    @classmethod
    def revoke_module(cls, tenant, module_key: str) -> int:
        """Remove a module's entitlements from a tenant. Returns rows deleted."""
        deleted, _ = cls.objects.filter(tenant=tenant, module_key=module_key).delete()
        cls._invalidate(tenant)
        return deleted

    @staticmethod
    def _invalidate(tenant):
        """Drop the cached feature map so the change takes effect immediately."""
        from apps.core.middleware import TenantFeatureFlagMiddleware
        TenantFeatureFlagMiddleware.invalidate_cache(tenant.schema_name)


class Subscription(TimeStampedModel):
    """
    A tenant's subscription to a plan.
    Tracks billing status, Razorpay subscription ID, and period dates.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )

    # ---- Razorpay IDs (set when subscription is created) --
    razorpay_subscription_id = models.CharField(
        max_length=100, blank=True, default="", db_index=True
    )
    razorpay_customer_id = models.CharField(max_length=100, blank=True, default="")

    # ---- Status -------------------------------------------
    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.CHOICES,
        default=SubscriptionStatus.TRIAL,
        db_index=True,
    )

    # ---- Billing Cycle ------------------------------------
    billing_cycle = models.CharField(
        max_length=10,
        choices=[("monthly", "Monthly"), ("yearly", "Yearly")],
        default="monthly",
    )
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"
        ordering = ["-created_at"]
        get_latest_by = "created_at"

    def __str__(self):
        return (
            f"{self.tenant.company_name} — {self.plan.name} "
            f"[{self.get_status_display()}]"
        )

    @property
    def is_active(self) -> bool:
        return self.status in SubscriptionStatus.ACTIVE_STATUSES

    @property
    def is_trial(self) -> bool:
        return self.status == SubscriptionStatus.TRIAL

    @property
    def days_until_renewal(self) -> int:
        if not self.current_period_end:
            return 0
        delta = self.current_period_end - timezone.now()
        return max(0, delta.days)

    def cancel(self, immediately: bool = False):
        """Cancel subscription."""
        if immediately:
            self.status = SubscriptionStatus.CANCELLED
            self.cancelled_at = timezone.now()
        else:
            self.cancel_at_period_end = True
        self.save(
            update_fields=["status", "cancelled_at", "cancel_at_period_end"]
        )


class Invoice(TimeStampedModel):
    """
    GST-compliant invoice for each billing event.

    Follows Indian GST rules:
    - Intra-state (same state as TeleCRM): CGST (9%) + SGST (9%)
    - Inter-state (different state): IGST (18%)
    - SAC code: 998315 (Information technology software services)
    - Invoice number format: TCRM/2024-25/00001
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="invoices",
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        related_name="invoices",
    )

    # ---- Invoice Details ----------------------------------
    invoice_number = models.CharField(max_length=50, unique=True, db_index=True)
    invoice_date = models.DateField(default=timezone.now)

    # ---- Amounts (all in INR) ----------------------------
    base_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Pre-tax amount.",
    )
    cgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    sgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    igst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    sgst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    igst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    # ---- GST Fields (Indian compliance) ------------------
    hsn_sac_code = models.CharField(
        max_length=10, default=GSTState.SAC_CODE, help_text="SAC code for SaaS."
    )
    is_interstate = models.BooleanField(default=False)
    customer_gstin = models.CharField(max_length=15, blank=True, default="")
    customer_state = models.CharField(max_length=2, blank=True, default="")

    # ---- Billing Address Snapshot (at time of invoice) --
    billing_name = models.CharField(max_length=200, blank=True, default="")
    billing_address_snapshot = models.TextField(blank=True, default="")

    # ---- Payment ------------------------------------------
    payment_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("paid", "Paid"),
            ("failed", "Failed"),
            ("refunded", "Refunded"),
        ],
        default="pending",
        db_index=True,
    )
    razorpay_payment_id = models.CharField(max_length=100, blank=True, default="")
    razorpay_order_id = models.CharField(max_length=100, blank=True, default="")

    # ---- Period ------------------------------------------
    billing_period_start = models.DateField(null=True, blank=True)
    billing_period_end = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    # ---- PDF Storage ------------------------------------
    invoice_pdf = models.FileField(
        upload_to="invoices/",
        blank=True,
        null=True,
        help_text="Generated PDF invoice.",
    )

    class Meta:
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"
        ordering = ["-invoice_date"]

    def __str__(self):
        return (
            f"{self.invoice_number} — {self.tenant.company_name} "
            f"— ₹{self.total_amount}"
        )

    @classmethod
    def generate_invoice_number(cls) -> str:
        """
        Generate sequential GST invoice number.
        Format: TCRM/YYYY-YY/NNNNN
        Example: TCRM/2024-25/00001
        """
        from django.utils import timezone as tz
        now = tz.now()
        # Indian financial year: April to March
        if now.month >= 4:
            fy = f"{now.year}-{str(now.year + 1)[2:]}"
        else:
            fy = f"{now.year - 1}-{str(now.year)[2:]}"

        # Find next sequence number for this FY
        prefix = f"TCRM/{fy}/"
        last_invoice = (
            cls.objects.filter(invoice_number__startswith=prefix)
            .order_by("-invoice_number")
            .first()
        )
        if last_invoice:
            last_num = int(last_invoice.invoice_number.split("/")[-1])
            next_num = last_num + 1
        else:
            next_num = 1

        return f"{prefix}{next_num:05d}"

    def mark_paid(self, razorpay_payment_id: str):
        """Mark invoice as paid."""
        self.payment_status = "paid"
        self.razorpay_payment_id = razorpay_payment_id
        self.paid_at = timezone.now()
        self.save(update_fields=["payment_status", "razorpay_payment_id", "paid_at"])
