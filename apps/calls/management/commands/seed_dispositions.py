"""
TeleCRM Backend — apps/calls/management/commands/seed_dispositions.py

Seeds (and upgrades) the default call outcomes for tenant schemas. Runs on
tenant creation (tenants/signals.py) and from the calls 0007 migration for
every existing tenant; this command is for running it again by hand.

It used get_or_create, so an existing tenant never received a change to the
defaults. It now upserts — see apps/calls/disposition_defaults.py.

Usage:
    python manage.py seed_dispositions --schema=acme_realty
    python manage.py seed_dispositions --all
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.calls.disposition_defaults import DEFAULTS, upgrade_dispositions

# Kept for anything that imported the old name.
DEFAULT_DISPOSITIONS = [
    {"slug": r[0], "name": r[1], "category": r[2], "lead_status": r[3],
     "auto_followup_hours": r[4], "is_positive": r[5], "sets_dnd": r[6], "sort_order": r[7]}
    for r in DEFAULTS
]


class Command(BaseCommand):
    help = "Seed or upgrade the default call outcomes for tenant schemas."

    def add_arguments(self, parser):
        parser.add_argument("--schema", type=str, default=None,
                            help="Tenant schema name (required unless --all is used)")
        parser.add_argument("--all", action="store_true",
                            help="Run for all active tenant schemas")

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
                self._seed_for_schema(schema)
        else:
            schema = options.get("schema")
            if not schema:
                raise CommandError("Provide --schema=<name> or use --all")
            if not Tenant.objects.filter(schema_name=schema).exists():
                raise CommandError(f"Tenant schema '{schema}' not found")
            self._seed_for_schema(schema)

        self.stdout.write(self.style.SUCCESS("\n✅ Dispositions seeded successfully"))

    def _seed_for_schema(self, schema_name: str):
        previous = connection.schema_name
        try:
            connection.set_schema(schema_name)
            from apps.calls.models import CallDisposition

            result = upgrade_dispositions(CallDisposition)
            self.stdout.write(
                f"  [{schema_name}] {result['created']} created, {result['renamed']} renamed"
            )
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  [{schema_name}] Error: {exc}"))
        finally:
            connection.set_schema(previous)
