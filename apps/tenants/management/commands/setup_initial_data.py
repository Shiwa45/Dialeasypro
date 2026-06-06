"""
TeleCRM Backend — apps/tenants/management/commands/setup_initial_data.py

Seeds all required initial data for a fresh TeleCRM installation:
  1. Plans: Starter, Growth, Business, Enterprise
  2. Plan features for each plan
  3. Django superuser (for /superadmin/ panel)
  4. Default global settings

Run this AFTER migrations:
    python manage.py migrate_schemas --shared
    python manage.py create_public_tenant
    python manage.py setup_initial_data

For development with test tenant:
    python manage.py setup_initial_data --create-demo-tenant
"""
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed initial TeleCRM data: plans, features, super admin user."

    def add_arguments(self, parser):
        parser.add_argument(
            "--create-demo-tenant",
            action="store_true",
            help="Also create a demo tenant for testing",
        )
        parser.add_argument(
            "--superuser-email",
            type=str,
            default="admin@telecrm.in",
            help="Super admin email (default: admin@telecrm.in)",
        )
        parser.add_argument(
            "--superuser-password",
            type=str,
            default=None,
            help="Super admin password (prompted if not provided)",
        )

    def handle(self, *args, **options):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("  TeleCRM Initial Data Setup")
        self.stdout.write("=" * 60 + "\n")

        self._setup_plans()
        self._setup_superuser(
            options["superuser_email"], options.get("superuser_password")
        )
        self._setup_global_settings()

        if options["create_demo_tenant"]:
            self._create_demo_tenant()

        self.stdout.write(
            self.style.SUCCESS(
                "\n✅ Initial setup complete!\n"
                f"   Admin panel: http://localhost:8000/superadmin/\n"
            )
        )

    def _setup_plans(self):
        """Create all subscription plans with features."""
        self.stdout.write("\n📦 Setting up plans...")

        from apps.core.constants import FeatureKey
        from apps.plans.models import Plan, PlanFeature

        plans_config = [
            {
                "name": "Starter",
                "slug": "starter",
                "description": "Perfect for small teams getting started with CRM.",
                "price_monthly": "999.00",
                "price_yearly": "9590.00",  # ~20% discount
                "max_agents": 5,
                "max_leads": 5000,
                "max_leads_per_day": 200,
                "max_whatsapp_bulk_per_day": 500,
                "max_email_bulk_per_day": 1000,
                "max_sms_per_day": 500,
                "storage_gb": 5,
                "custom_fields_limit": 10,
                "data_retention_days": 180,
                "is_public": True,
                "sort_order": 1,
                "features": [
                    FeatureKey.MANUAL_ENTRY if hasattr(FeatureKey, "MANUAL_ENTRY") else None,
                    FeatureKey.LEAD_IMPORT,
                    FeatureKey.BASIC_REPORTS,
                    FeatureKey.ONE_CLICK_WHATSAPP,
                    FeatureKey.ONE_CLICK_EMAIL,
                    FeatureKey.ONE_CLICK_SMS,
                    FeatureKey.FOLLOW_UP_AUTOMATION,
                    FeatureKey.CONTACT_HISTORY,
                    FeatureKey.LEAD_PIPELINE,
                    FeatureKey.WHATSAPP_SINGLE_PROVIDER,
                ],
            },
            {
                "name": "Growth",
                "slug": "growth",
                "description": "For growing teams that need integrations and bulk communication.",
                "price_monthly": "2499.00",
                "price_yearly": "23990.00",
                "max_agents": 20,
                "max_leads": 25000,
                "max_leads_per_day": 1000,
                "max_whatsapp_bulk_per_day": 5000,
                "max_email_bulk_per_day": 10000,
                "max_sms_per_day": 2000,
                "storage_gb": 25,
                "custom_fields_limit": 30,
                "data_retention_days": 365,
                "is_public": True,
                "sort_order": 2,
                "features": [
                    FeatureKey.LEAD_IMPORT,
                    FeatureKey.LEAD_EXPORT,
                    FeatureKey.BASIC_REPORTS,
                    FeatureKey.ADVANCED_REPORTS,
                    FeatureKey.ONE_CLICK_WHATSAPP,
                    FeatureKey.ONE_CLICK_EMAIL,
                    FeatureKey.ONE_CLICK_SMS,
                    FeatureKey.BULK_WHATSAPP,
                    FeatureKey.BULK_EMAIL,
                    FeatureKey.BULK_SMS,
                    FeatureKey.FOLLOW_UP_AUTOMATION,
                    FeatureKey.CONTACT_HISTORY,
                    FeatureKey.LEAD_PIPELINE,
                    FeatureKey.LEAD_SCORING,
                    FeatureKey.CUSTOM_FIELDS,
                    FeatureKey.WHATSAPP_SINGLE_PROVIDER,
                    FeatureKey.TEAM_MANAGEMENT,
                    FeatureKey.AGENT_PERFORMANCE_REPORTS,
                    FeatureKey.INDIAMART,
                    FeatureKey.META_LEAD_ADS,
                    FeatureKey.GOOGLE_ADS_LEADS,
                    FeatureKey.WEBSITE_WIDGET,
                    FeatureKey.GENERIC_WEBHOOK,
                    FeatureKey.CALL_RECORDING_ACCESS,
                ],
            },
            {
                "name": "Business",
                "slug": "business",
                "description": "Full-featured CRM for serious sales teams.",
                "price_monthly": "5999.00",
                "price_yearly": "57590.00",
                "max_agents": 100,
                "max_leads": 100000,
                "max_leads_per_day": 5000,
                "max_whatsapp_bulk_per_day": 20000,
                "max_email_bulk_per_day": 50000,
                "max_sms_per_day": 10000,
                "storage_gb": 100,
                "custom_fields_limit": 100,
                "data_retention_days": 730,  # 2 years
                "is_public": True,
                "sort_order": 3,
                "features": FeatureKey.ALL,  # All features enabled
            },
            {
                "name": "Enterprise",
                "slug": "enterprise",
                "description": "Custom solution for large enterprises with dedicated support.",
                "price_monthly": "0.00",  # Custom pricing
                "price_yearly": "0.00",
                "max_agents": 9999,
                "max_leads": 9999999,
                "max_leads_per_day": 99999,
                "max_whatsapp_bulk_per_day": 999999,
                "max_email_bulk_per_day": 999999,
                "max_sms_per_day": 999999,
                "storage_gb": 1000,
                "custom_fields_limit": 9999,
                "data_retention_days": 9999,
                "is_public": True,
                "sort_order": 4,
                "features": FeatureKey.ALL,
            },
        ]

        for plan_data in plans_config:
            features = plan_data.pop("features", [])
            features = [f for f in features if f]  # Remove None values

            plan, created = Plan.objects.update_or_create(
                slug=plan_data["slug"],
                defaults=plan_data,
            )

            action = "Created" if created else "Updated"
            self.stdout.write(f"  {action}: {plan.name} plan")

            # Create plan features
            for feature_key in features:
                PlanFeature.objects.update_or_create(
                    plan=plan,
                    feature_key=feature_key,
                    defaults={"is_enabled": True},
                )

            self.stdout.write(f"    → {len(features)} features configured")

        self.stdout.write(self.style.SUCCESS("  ✅ Plans configured"))

    def _setup_superuser(self, email: str, password: str | None = None):
        """Create Django superuser for the admin panel."""
        from django.contrib.auth import get_user_model

        User = get_user_model()

        self.stdout.write("\n👤 Setting up super admin user...")

        if User.objects.filter(email=email).exists():
            self.stdout.write(
                self.style.WARNING(f"  ⚠️  Super admin {email} already exists.")
            )
            return

        if not password:
            if sys.stdin.isatty():
                import getpass
                password = getpass.getpass(f"  Enter password for {email}: ")
                confirm = getpass.getpass("  Confirm password: ")
                if password != confirm:
                    self.stdout.write(self.style.ERROR("  ❌ Passwords do not match."))
                    return
            else:
                # In CI/CD or non-interactive — generate a random password
                import secrets
                password = secrets.token_urlsafe(20)
                self.stdout.write(
                    self.style.WARNING(
                        f"  ⚠️  Non-interactive mode. "
                        f"Generated password: {password}\n"
                        f"  CHANGE THIS IMMEDIATELY!"
                    )
                )

        User.objects.create_superuser(
            username=email,
            email=email,
            password=password,
        )

        self.stdout.write(
            self.style.SUCCESS(f"  ✅ Super admin created: {email}")
        )

    def _setup_global_settings(self):
        """Seed default GlobalSettings entries."""
        self.stdout.write("\n⚙️  Setting up global settings...")

        try:
            from apps.superadmin.models import GlobalSettings

            defaults = {
                "platform_name": "TeleCRM",
                "support_email": "support@telecrm.in",
                "default_trial_days": "14",
                "max_tenants": "1000",
                "maintenance_mode": "false",
                "allow_new_registrations": "true",
                "razorpay_mode": "test",  # Change to 'live' in production
            }

            for key, value in defaults.items():
                obj, created = GlobalSettings.objects.get_or_create(
                    key=key, defaults={"value": value}
                )
                if created:
                    self.stdout.write(f"  + {key}: {value}")

            self.stdout.write(self.style.SUCCESS("  ✅ Global settings ready"))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  ⚠️  Could not set global settings: {exc}"))

    def _create_demo_tenant(self):
        """Create a demo tenant for development/testing."""
        self.stdout.write("\n🏗️  Creating demo tenant...")

        from django.core.management import call_command

        try:
            call_command(
                "create_tenant",
                company="Demo Realty Pvt Ltd",
                email="demo@demorealty.com",
                phone="+919876543210",
                name="Demo Admin",
                plan="growth",
                schema="demo_realty",
                password="Demo@123456",
                no_email=True,
            )
        except Exception as exc:
            self.stdout.write(
                self.style.WARNING(f"  ⚠️  Demo tenant may already exist: {exc}")
            )
