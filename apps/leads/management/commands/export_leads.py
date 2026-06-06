"""
TeleCRM Backend — apps/leads/management/commands/export_leads.py

CLI command to export leads for a tenant schema to CSV.

Usage:
    python manage.py export_leads --schema=acme_realty
    python manage.py export_leads --schema=acme_realty --status=interested
    python manage.py export_leads --schema=acme_realty --output=/tmp/leads.csv
"""
import csv
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = "Export leads for a tenant to CSV."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True, type=str)
        parser.add_argument("--status", type=str, default="", help="Filter by status")
        parser.add_argument("--assigned-to", type=int, default=None)
        parser.add_argument(
            "--output", type=str, default=None,
            help="Output file path (default: leads_<schema>_<date>.csv)",
        )

    def handle(self, *args, **options):
        from apps.tenants.models import Tenant

        schema = options["schema"]
        if not Tenant.objects.filter(schema_name=schema).exists():
            raise CommandError(f"Schema '{schema}' not found")

        previous = connection.schema_name
        try:
            connection.set_schema(schema)
            self._export(schema, options)
        finally:
            connection.set_schema(previous)

    def _export(self, schema: str, options: dict):
        from apps.leads.models import Lead

        qs = Lead.objects.filter(is_deleted=False).select_related("assigned_to", "disposition")
        if options["status"]:
            qs = qs.filter(status=options["status"])
        if options["assigned_to"]:
            qs = qs.filter(assigned_to_id=options["assigned_to"])

        output_path = options["output"] or (
            f"leads_{schema}_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
        )

        fields = [
            "id", "name", "phone", "alternate_phone", "email",
            "city", "state", "pincode", "source", "status", "priority",
            "score", "budget", "requirement", "deal_value",
            "assigned_to__name", "next_followup_at", "last_contacted_at",
            "contact_count", "is_dnd", "created_at",
        ]

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            count = 0
            for lead in qs.values(*fields).iterator(chunk_size=500):
                writer.writerow(lead)
                count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Exported {count} leads → {os.path.abspath(output_path)}"
            )
        )
