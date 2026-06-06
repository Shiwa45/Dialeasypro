"""
TeleCRM Backend — apps/tenants/models.py

Tenant and Domain models — the core of the multi-tenant architecture.

Tenant  : Extends django-tenants TenantMixin. Each row = one client company.
          Creating a Tenant record auto-creates a PostgreSQL schema.
Domain  : Subdomain or custom domain mapping to a Tenant.
          e.g. acmerealty.telecrm.in → Tenant(schema_name='acme_realty')

These models live in the PUBLIC schema (shared across all tenants).
"""
import logging

from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django_tenants.models import DomainMixin, TenantMixin

from apps.core.constants import Industry, SubscriptionStatus
from apps.core.models import TimeStampedModel

logger = logging.getLogger(__name__)


class Tenant(TenantMixin, TimeStampedModel):
    """
    Represents one CRM client company (tenant).

    Key fields:
      schema_name   : PostgreSQL schema name. Must be unique, lowercase,
                      no spaces. Auto-set from company name at creation.
      is_active     : Master switch — if False, all logins blocked.
      plan          : FK to Plan (in plans app). May be null before subscription.

    django-tenants behaviour:
      auto_create_schema = True → Calling .save() creates the PG schema
                                   and runs all TENANT_APPS migrations.
    """

    auto_create_schema = True

    # ---- Company Info --------------------------------------
    company_name = models.CharField(max_length=200, db_index=True)
    industry = models.CharField(
        max_length=50,
        choices=Industry.CHOICES,
        default=Industry.OTHER,
        blank=True,
    )
    gstin = models.CharField(
        max_length=15,
        blank=True,
        default="",
        help_text="GST Identification Number (15 chars). Optional.",
    )

    # ---- Billing Address (for GST invoices) ----------------
    billing_address = models.TextField(blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(
        max_length=2,
        blank=True,
        default="",
        help_text="2-letter Indian state code for GST (e.g., MH, DL, KA).",
    )
    pincode = models.CharField(max_length=6, blank=True, default="")

    # ---- Primary Contact -----------------------------------
    primary_contact_name = models.CharField(max_length=150)
    primary_contact_email = models.EmailField(db_index=True)
    primary_contact_phone = models.CharField(
        max_length=15,
        validators=[
            RegexValidator(
                r"^\+91[6-9]\d{9}$",
                "Enter a valid Indian mobile number (+91XXXXXXXXXX).",
            )
        ],
    )

    # ---- Plan & Subscription --------------------------------
    # ForeignKey to plans.Plan — set when subscription is created.
    # Deliberately kept as a simple FK to avoid circular import complexity.
    plan = models.ForeignKey(
        "plans.Plan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenants",
    )
    subscription_status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.CHOICES,
        default=SubscriptionStatus.TRIAL,
        db_index=True,
    )
    trial_ends_at = models.DateTimeField(null=True, blank=True)

    # ---- Platform Status -----------------------------------
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Master kill-switch. Set to False to block all logins.",
    )
    onboarding_completed = models.BooleanField(default=False)
    onboarding_step = models.PositiveSmallIntegerField(
        default=0,
        help_text="Current onboarding step (1–5).",
    )

    # ---- Branding (for white-label tenants) ----------------
    logo = models.ImageField(
        upload_to="tenant_logos/",
        blank=True,
        null=True,
    )
    primary_color = models.CharField(
        max_length=7,
        default="#4F46E5",
        help_text="Hex color code for brand primary color.",
    )

    # ---- Locale --------------------------------------------
    timezone = models.CharField(
        max_length=50,
        default="Asia/Kolkata",
    )
    language_preference = models.CharField(
        max_length=5,
        choices=[("en", "English"), ("hi", "Hindi")],
        default="en",
    )

    # ---- Custom Domain (for white-label) -------------------
    custom_domain = models.CharField(
        max_length=253,
        blank=True,
        default="",
        help_text="Custom domain for white-label tenants (e.g., crm.acmerealty.in).",
    )

    # ---- Internal Notes (Super Admin only) -----------------
    internal_notes = models.TextField(
        blank=True,
        default="",
        help_text="Internal notes visible only to TeleCRM super admins.",
    )

    # ---- Usage Stats (updated daily by Celery) -------------
    total_agents = models.PositiveIntegerField(default=0)
    total_leads = models.PositiveIntegerField(default=0)
    total_calls_today = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company_name} ({self.schema_name})"

    # ---- Properties ----------------------------------------

    @property
    def is_trial(self) -> bool:
        return self.subscription_status == SubscriptionStatus.TRIAL

    @property
    def is_trial_expired(self) -> bool:
        if not self.is_trial:
            return False
        if not self.trial_ends_at:
            return False
        return timezone.now() > self.trial_ends_at

    @property
    def trial_days_remaining(self) -> int:
        if not self.trial_ends_at or not self.is_trial:
            return 0
        delta = self.trial_ends_at - timezone.now()
        return max(0, delta.days)

    @property
    def is_subscription_active(self) -> bool:
        return self.subscription_status in SubscriptionStatus.ACTIVE_STATUSES

    @property
    def subdomain_url(self) -> str:
        from django.conf import settings
        return f"https://{self.schema_name}.{settings.BASE_DOMAIN}"

    # ---- Methods -------------------------------------------

    def suspend(self, reason: str = ""):
        """Suspend the tenant account."""
        self.subscription_status = SubscriptionStatus.SUSPENDED
        self.is_active = False
        if reason:
            self.internal_notes += f"\n[SUSPENDED {timezone.now().date()}] {reason}"
        self.save(update_fields=["subscription_status", "is_active", "internal_notes"])
        logger.info(f"[Tenant] Suspended: {self.schema_name} — {reason}")

    def activate(self):
        """Activate (or reactivate) the tenant account."""
        self.subscription_status = SubscriptionStatus.ACTIVE
        self.is_active = True
        self.save(update_fields=["subscription_status", "is_active"])
        logger.info(f"[Tenant] Activated: {self.schema_name}")

    def set_trial(self, days: int = 14):
        """Set or reset the trial period."""
        from datetime import timedelta
        self.subscription_status = SubscriptionStatus.TRIAL
        self.trial_ends_at = timezone.now() + timedelta(days=days)
        self.is_active = True
        self.save(update_fields=["subscription_status", "trial_ends_at", "is_active"])

    def has_feature(self, feature_key: str) -> bool:
        """
        Check if tenant's plan has a specific feature enabled.
        NOTE: In request context, use request.has_feature() instead
        (it's cached in Redis). This method always hits the DB.
        """
        from apps.plans.models import PlanFeature, Subscription

        try:
            subscription = Subscription.objects.filter(
                tenant=self,
                status__in=SubscriptionStatus.ACTIVE_STATUSES,
            ).select_related("plan").first()

            if not subscription:
                return False

            return PlanFeature.objects.filter(
                plan=subscription.plan,
                feature_key=feature_key,
                is_enabled=True,
            ).exists()
        except Exception:
            return False


class Domain(DomainMixin):
    """
    Maps a domain/subdomain to a Tenant.

    django-tenants uses this to route requests:
    1. Request hits acmerealty.telecrm.in
    2. django-tenants queries Domain for this domain
    3. Sets connection schema to tenant.schema_name
    4. Request proceeds in tenant's PostgreSQL schema

    Multiple domains can map to one tenant (e.g., custom domain + subdomain).
    Only one should have is_primary=True.
    """

    class Meta:
        verbose_name = "Domain"
        verbose_name_plural = "Domains"

    def __str__(self):
        return f"{self.domain} → {self.tenant.company_name}"
