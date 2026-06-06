"""
TeleCRM Backend — apps/tenants/management/commands/create_public_tenant.py

Creates the "public" tenant required by django-tenants.
This MUST be run once before anything else works.

Usage:
    python manage.py create_public_tenant
    python manage.py create_public_tenant --domain=telecrm.in
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the public tenant (required by django-tenants). Run this once."

    def add_arguments(self, parser):
        parser.add_argument(
            "--domain",
            type=str,
            default=None,
            help=f"Primary domain for the public tenant (default: {settings.BASE_DOMAIN})",
        )

    def handle(self, *args, **options):
        from apps.tenants.models import Domain, Tenant

        domain_name = options.get("domain") or settings.BASE_DOMAIN

        if Tenant.objects.filter(schema_name="public").exists():
            self.stdout.write(
                self.style.WARNING("⚠️  Public tenant already exists. Skipping.")
            )
            # Ensure domain exists
            public_tenant = Tenant.objects.get(schema_name="public")
            if not Domain.objects.filter(tenant=public_tenant).exists():
                Domain.objects.create(
                    domain=domain_name,
                    tenant=public_tenant,
                    is_primary=True,
                )
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Created domain: {domain_name}")
                )
            return

        self.stdout.write("Creating public tenant...")

        # Create public tenant (does NOT create a new schema — public schema always exists)
        public_tenant = Tenant(
            schema_name="public",
            company_name="TeleCRM Platform",
            primary_contact_name="TeleCRM Admin",
            primary_contact_email="admin@telecrm.in",
            primary_contact_phone="+911234567890",
            is_active=True,
        )

        # Prevent auto_create_schema for public (schema already exists)
        public_tenant.auto_create_schema = False
        public_tenant.save(verbosity=0)

        # Create primary domain
        Domain.objects.create(
            domain=domain_name,
            tenant=public_tenant,
            is_primary=True,
        )

        # Also add admin subdomain if different
        admin_domain = settings.SUPER_ADMIN_DOMAIN
        if admin_domain and admin_domain != domain_name:
            Domain.objects.get_or_create(
                domain=admin_domain,
                defaults={"tenant": public_tenant, "is_primary": False},
            )
            self.stdout.write(f"  ✅ Admin domain: {admin_domain}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Public tenant created!\n"
                f"   Schema: public\n"
                f"   Domain: {domain_name}\n"
            )
        )
