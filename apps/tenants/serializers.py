"""
TeleCRM Backend — apps/tenants/serializers.py

DRF serializers for Tenant registration and public API.
"""
import re

from rest_framework import serializers

from apps.core.constants import Industry
from apps.core.utils import make_unique_schema_name, validate_gstin
from apps.tenants.models import Domain, Tenant


class TenantRegistrationSerializer(serializers.Serializer):
    """
    Serializer for new tenant registration (public API endpoint).
    Validates and creates a new Tenant + Domain.
    """

    # Company
    company_name = serializers.CharField(max_length=200)
    industry = serializers.ChoiceField(choices=Industry.CHOICES, default=Industry.OTHER)
    gstin = serializers.CharField(max_length=15, required=False, allow_blank=True, default="")

    # Primary Contact
    primary_contact_name = serializers.CharField(max_length=150)
    primary_contact_email = serializers.EmailField()
    primary_contact_phone = serializers.CharField(max_length=15)

    # Billing Address
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=2, required=False, allow_blank=True)
    pincode = serializers.CharField(max_length=6, required=False, allow_blank=True)

    # Plan selection
    plan_slug = serializers.CharField(default="starter")

    def validate_primary_contact_phone(self, value):
        from apps.core.utils import normalize_indian_phone
        normalized = normalize_indian_phone(value)
        if not normalized:
            raise serializers.ValidationError(
                "Invalid Indian mobile number. Please enter a valid 10-digit number."
            )
        return normalized

    def validate_gstin(self, value):
        if value and not validate_gstin(value):
            raise serializers.ValidationError("Invalid GSTIN format.")
        return value.upper() if value else ""

    def validate_company_name(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError(
                "Company name must be at least 3 characters."
            )
        return value.strip()

    def validate_primary_contact_email(self, value):
        # Check for duplicate email across tenants
        if Tenant.objects.filter(
            primary_contact_email__iexact=value
        ).exists():
            raise serializers.ValidationError(
                "An account with this email already exists. "
                "Please log in or use a different email."
            )
        return value.lower()

    def create(self, validated_data):
        """Create Tenant + Domain + Subscription."""
        from apps.plans.models import Plan
        from apps.core.constants import PlanSlug

        plan_slug = validated_data.pop("plan_slug", PlanSlug.STARTER)

        # Generate unique schema name from company name
        schema_name = make_unique_schema_name(validated_data["company_name"])

        # Get plan
        plan = Plan.objects.filter(slug=plan_slug, is_active=True).first()

        # Create tenant (auto_create_schema=True → creates PG schema + runs migrations)
        tenant = Tenant(
            schema_name=schema_name,
            company_name=validated_data["company_name"],
            industry=validated_data.get("industry", Industry.OTHER),
            gstin=validated_data.get("gstin", ""),
            primary_contact_name=validated_data["primary_contact_name"],
            primary_contact_email=validated_data["primary_contact_email"],
            primary_contact_phone=validated_data["primary_contact_phone"],
            city=validated_data.get("city", ""),
            state=validated_data.get("state", ""),
            pincode=validated_data.get("pincode", ""),
            plan=plan,
        )
        tenant.save()  # ← This triggers schema creation + post_schema_sync signal
        # NOTE: Domain registration is handled by _register_tenant_domains()
        # in the post_schema_sync signal, which creates domains for ALL
        # configured BASE_DOMAINS (supporting multi-domain migration).

        return tenant


class TenantPublicSerializer(serializers.ModelSerializer):
    """Public-safe tenant info (no sensitive data)."""

    class Meta:
        model = Tenant
        fields = [
            "company_name",
            "schema_name",
            "industry",
            "subscription_status",
            "logo",
            "primary_color",
        ]
