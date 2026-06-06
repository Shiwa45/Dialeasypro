"""
TeleCRM Backend — apps/calls/management/commands/seed_dispositions.py

Seeds standard call dispositions for a tenant schema.
Called automatically during tenant creation (via post_schema_sync signal)
and can also be run manually.

Usage:
    # Seed dispositions for a specific tenant schema
    python manage.py seed_dispositions --schema=acme_realty

    # Seed for all tenants (runs in each tenant schema)
    python manage.py seed_dispositions --all
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


DEFAULT_DISPOSITIONS = [
    # Connected / positive
    {
        "name": "Connected – Interested",
        "slug": "connected_interested",
        "is_positive": True,
        "sort_order": 1,
        "auto_followup_hours": 24,
    },
    {
        "name": "Connected – Callback Requested",
        "slug": "connected_callback",
        "is_positive": True,
        "sort_order": 2,
        "auto_followup_hours": 4,
    },
    {
        "name": "Connected – Not Interested",
        "slug": "connected_not_interested",
        "is_positive": False,
        "sort_order": 3,
        "auto_followup_hours": None,
    },
    {
        "name": "Connected – Already Purchased",
        "slug": "connected_purchased",
        "is_positive": False,
        "sort_order": 4,
        "auto_followup_hours": None,
    },
    # Not connected
    {
        "name": "Not Reachable",
        "slug": "not_reachable",
        "is_positive": False,
        "sort_order": 5,
        "auto_followup_hours": 6,
    },
    {
        "name": "Busy",
        "slug": "busy",
        "is_positive": False,
        "sort_order": 6,
        "auto_followup_hours": 2,
    },
    {
        "name": "Switched Off",
        "slug": "switched_off",
        "is_positive": False,
        "sort_order": 7,
        "auto_followup_hours": 12,
    },
    {
        "name": "Wrong Number",
        "slug": "wrong_number",
        "is_positive": False,
        "sort_order": 8,
        "auto_followup_hours": None,
    },
    {
        "name": "Do Not Disturb",
        "slug": "dnd",
        "is_positive": False,
        "sort_order": 9,
        "auto_followup_hours": None,
    },
    {
        "name": "Voicemail Left",
        "slug": "voicemail",
        "is_positive": False,
        "sort_order": 10,
        "auto_followup_hours": 24,
    },
]


class Command(BaseCommand):
    help = "Seed default call dispositions for a tenant schema."

    def add_arguments(self, parser):
        parser.add_argument("--schema", type=str, default=None,
                            help="Tenant schema name (required unless --all is used)")
        parser.add_argument("--all", action="store_true",
                            help="Run for all active tenant schemas")
        parser.add_argument("--clear", action="store_true",
                            help="Remove existing dispositions before seeding")

    def handle(self, *args, **options):
        from apps.tenants.models import Tenant

        if options["all"]:
            schemas = list(
                Tenant.objects.exclude(schema_name="public")
                .filter(is_active=True)
                .values_list("schema_name", flat=True)
            )
            self.stdout.write(f"Seeding dispositions for {len(schemas)} tenants...")
            for schema in schemas:
                self._seed_for_schema(schema, options["clear"])
        else:
            schema = options.get("schema")
            if not schema:
                raise CommandError("Provide --schema=<name> or use --all")
            if not Tenant.objects.filter(schema_name=schema).exists():
                raise CommandError(f"Tenant schema '{schema}' not found")
            self._seed_for_schema(schema, options["clear"])

        self.stdout.write(self.style.SUCCESS("\n✅ Dispositions seeded successfully"))

    def _seed_for_schema(self, schema_name: str, clear: bool):
        previous = connection.schema_name
        try:
            connection.set_schema(schema_name)
            from apps.calls.models import CallDisposition

            if clear:
                CallDisposition.objects.all().delete()
                self.stdout.write(f"  [{schema_name}] Cleared existing dispositions")

            created_count = 0
            for d in DEFAULT_DISPOSITIONS:
                _, created = CallDisposition.objects.get_or_create(
                    slug=d["slug"],
                    defaults={
                        "name": d["name"],
                        "is_positive": d["is_positive"],
                        "sort_order": d["sort_order"],
                        "auto_followup_hours": d.get("auto_followup_hours"),
                        "is_active": True,
                    },
                )
                if created:
                    created_count += 1

            self.stdout.write(
                f"  [{schema_name}] {created_count} new / "
                f"{len(DEFAULT_DISPOSITIONS) - created_count} existing"
            )
        except Exception as exc:
            self.stdout.write(
                self.style.ERROR(f"  [{schema_name}] Error: {exc}")
            )
        finally:
            connection.set_schema(previous)
