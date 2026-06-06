"""
TeleCRM Backend — apps/tenants/management/commands/create_tenant.py

CLI command to manually create a tenant (useful for onboarding,
demos, and seeding test environments).

Usage:
    python manage.py create_tenant \\
        --company="Acme Realty Pvt Ltd" \\
        --email=admin@acmerealty.com \\
        --phone=9876543210 \\
        --name="Rahul Sharma" \\
        --plan=starter

    # With explicit schema name:
    python manage.py create_tenant \\
        --company="Acme Realty" \\
        --email=admin@acmerealty.com \\
        --schema=acme_realty
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a new tenant with an admin agent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--company", required=True, type=str, help="Company name"
        )
        parser.add_argument(
            "--email", required=True, type=str, help="Admin email address"
        )
        parser.add_argument(
            "--phone",
            required=True,
            type=str,
            help="Admin phone number (10-digit Indian mobile)",
        )
        parser.add_argument(
            "--name", required=True, type=str, help="Admin full name"
        )
        parser.add_argument(
            "--plan",
            type=str,
            default="starter",
            help="Plan slug: starter | growth | business | enterprise (default: starter)",
        )
        parser.add_argument(
            "--schema",
            type=str,
            default=None,
            help="Override schema name (auto-generated if not provided)",
        )
        parser.add_argument(
            "--password",
            type=str,
            default=None,
            help="Admin password (auto-generated if not provided)",
        )
        parser.add_argument(
            "--trial-days",
            type=int,
            default=settings.DEFAULT_TRIAL_DAYS,
            help=f"Trial period in days (default: {settings.DEFAULT_TRIAL_DAYS})",
        )
        parser.add_argument(
            "--no-email",
            action="store_true",
            help="Skip sending welcome email",
        )

    def handle(self, *args, **options):
        from apps.core.utils import make_unique_schema_name, normalize_indian_phone
        from apps.plans.models import Plan
        from apps.tenants.models import Domain, Tenant

        # ---- Validate inputs --------------------------------
        phone = normalize_indian_phone(options["phone"])
        if not phone:
            raise CommandError(
                f"Invalid phone number: {options['phone']}. "
                "Please provide a valid 10-digit Indian mobile number."
            )

        plan = Plan.objects.filter(slug=options["plan"], is_active=True).first()
        if not plan:
            available = ", ".join(Plan.objects.values_list("slug", flat=True))
            raise CommandError(
                f"Plan '{options['plan']}' not found. Available plans: {available}"
            )

        # Determine schema name
        schema_name = options.get("schema") or make_unique_schema_name(options["company"])

        if Tenant.objects.filter(schema_name=schema_name).exists():
            raise CommandError(
                f"Schema '{schema_name}' already exists. "
                "Use --schema to provide a different name."
            )

        # ---- Create tenant ----------------------------------
        self.stdout.write(f"\n🚀 Creating tenant: {options['company']}")
        self.stdout.write(f"   Schema: {schema_name}")
        self.stdout.write(f"   Plan:   {plan.name}")
        self.stdout.write(f"   Admin:  {options['email']}\n")

        try:
            tenant = Tenant(
                schema_name=schema_name,
                company_name=options["company"],
                primary_contact_name=options["name"],
                primary_contact_email=options["email"].lower(),
                primary_contact_phone=phone,
                plan=plan,
                is_active=True,
            )
            tenant.save()  # Triggers schema creation + post_schema_sync signal
            self.stdout.write(self.style.SUCCESS("  ✅ Tenant created"))

        except Exception as exc:
            raise CommandError(f"Failed to create tenant: {exc}")

        # ---- Create domain ----------------------------------
        domain_name = f"{schema_name}.{settings.BASE_DOMAIN}"
        Domain.objects.get_or_create(
            domain=domain_name,
            defaults={"tenant": tenant, "is_primary": True},
        )
        self.stdout.write(self.style.SUCCESS(f"  ✅ Domain: {domain_name}"))

        # ---- Development: also register {schema}.localhost --
        # Allows the frontend (running at localhost) to route to this tenant
        # without needing /etc/hosts entries or a real DNS subdomain.
        if settings.DEBUG:
            dev_domain = f"{schema_name}.localhost"
            Domain.objects.get_or_create(
                domain=dev_domain,
                defaults={"tenant": tenant, "is_primary": False},
            )
            self.stdout.write(self.style.SUCCESS(f"  ✅ Dev domain: {dev_domain}"))

        # ---- Set trial period --------------------------------
        tenant.set_trial(days=options["trial_days"])
        self.stdout.write(
            self.style.SUCCESS(
                f"  ✅ Trial: {options['trial_days']} days "
                f"(expires: {tenant.trial_ends_at.strftime('%Y-%m-%d')})"
            )
        )

        # ---- Get password (auto-generated in signal, or use provided) ---
        # The signal already created the admin agent with a temp password.
        # If --password is provided, update it.
        password_used = options.get("password")
        if password_used:
            from django.db import connection
            previous_schema = connection.schema_name
            try:
                connection.set_schema(schema_name)
                from apps.authentication.models import Agent
                admin = Agent.objects.filter(is_tenant_admin=True).first()
                if admin:
                    admin.set_password(password_used)
                    admin.must_change_password = False
                    admin.save(update_fields=["password", "must_change_password"])
            finally:
                connection.set_schema(previous_schema)

        # ---- Summary ----------------------------------------
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Tenant '{options['company']}' is ready!\n"
                f"\n   CRM URL:  https://{domain_name}/crm/\n"
                f"   Email:    {options['email']}\n"
                f"   Password: {password_used or '[Sent in welcome email / check signal logs]'}\n"
                f"   Trial:    {options['trial_days']} days\n"
            )
        )
