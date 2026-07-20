"""
Management command: fix_called_leads

Retroactively finds all leads with status="new" that have at least one
CallLog record, and updates them to status="attempted" + has_been_worked=True.

Usage:
    python manage.py fix_called_leads           # dry-run (default)
    python manage.py fix_called_leads --apply   # actually apply the fix

This is safe to run multiple times — it only touches leads that are still
in status="new" and have at least one call.
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = (
        "Fix leads that have been called but still show status='new'. "
        "Updates them to 'attempted' and marks has_been_worked=True."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Actually apply the fix. Without this flag, only a dry-run report is shown.",
        )
        parser.add_argument(
            "--schema",
            type=str,
            default="",
            help="Tenant schema to operate on. Leave empty for the current schema.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        schema = options.get("schema", "").strip()

        from django.db import connection
        from apps.tenants.models import Tenant

        if schema:
            tenants = Tenant.objects.filter(schema_name=schema)
            if not tenants.exists():
                self.stdout.write(self.style.ERROR(f"Schema '{schema}' not found."))
                return
        else:
            # By default, run on all tenants except public
            tenants = Tenant.objects.exclude(schema_name="public")

        for tenant in tenants:
            self.stdout.write(self.style.NOTICE(f"\n--- Processing Tenant: {tenant.schema_name} ---"))
            connection.set_schema(tenant.schema_name)
            self._process_tenant(apply)

    def _process_tenant(self, apply):
        from apps.leads.models import Lead
        from apps.calls.models import CallLog

        # Find all leads that are still "new" but have at least one call
        lead_ids_with_calls = (
            CallLog.objects.filter(lead__isnull=False)
            .values_list("lead_id", flat=True)
            .distinct()
        )

        stale_leads = Lead.objects.filter(
            pk__in=lead_ids_with_calls,
            status="new",
            is_deleted=False,
        )

        count = stale_leads.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS(
                "✓ No leads to fix — all called leads already have a non-'new' status."
            ))
            return

        self.stdout.write(
            f"Found {count} lead(s) with status='new' that have been called."
        )

        if not apply:
            self.stdout.write(self.style.WARNING(
                "DRY RUN — no changes made. Re-run with --apply to fix them."
            ))
            # Show a sample
            for lead in stale_leads[:10]:
                call_count = CallLog.objects.filter(lead=lead).count()
                self.stdout.write(
                    f"  • Lead #{lead.pk} '{lead.name}' ({lead.phone}) — "
                    f"{call_count} call(s), has_been_worked={lead.has_been_worked}"
                )
            if count > 10:
                self.stdout.write(f"  ... and {count - 10} more")
            return

        # Apply the fix
        updated = stale_leads.update(status="attempted", has_been_worked=True)

        self.stdout.write(self.style.SUCCESS(
            f"✓ Fixed {updated} lead(s): status → 'attempted', has_been_worked → True"
        ))
