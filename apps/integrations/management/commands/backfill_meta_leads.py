"""
TeleCRM Backend — apps/integrations/management/commands/backfill_meta_leads.py

Import EXISTING Meta Lead Ads leads into the CRM.

The realtime webhook only delivers leads submitted *after* the integration is
configured. Leads collected before that (or while the webhook wasn't wired up)
stay in Meta and never reach the CRM. This command pulls them via the Graph API
and creates them using the same field-mapping + dedup logic as the live webhook.

Usage:
    # Backfill all forms for the 'demo' tenant
    python manage.py backfill_meta_leads --schema=demo

    # Only leads created on/after a date
    python manage.py backfill_meta_leads --schema=demo --since=2026-05-01

    # A single form
    python manage.py backfill_meta_leads --schema=demo --form=840957365235806

    # See what would happen without writing anything
    python manage.py backfill_meta_leads --schema=demo --dry-run
"""
from datetime import datetime, timezone as dt_timezone

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.core.exceptions import PlanLimitExceededException

GRAPH = "https://graph.facebook.com/v18.0"


class Command(BaseCommand):
    help = "Backfill existing Meta Lead Ads leads into the CRM for a tenant."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True, help="Tenant schema name (e.g. demo)")
        parser.add_argument("--form", default=None, help="Limit to a single Meta form ID")
        parser.add_argument("--since", default=None, help="Only leads created on/after YYYY-MM-DD")
        parser.add_argument("--dry-run", action="store_true", help="Don't write, just report")

    def handle(self, *args, **opts):
        from apps.core.constants import LeadSource
        from apps.integrations.models import LeadSourceConfig
        from apps.integrations.field_mapping import (
            flatten_meta_field_data, apply_field_mapping,
        )
        from apps.integrations.views import MetaLeadAdsWebhookView

        schema = opts["schema"]
        dry_run = opts["dry_run"]

        since = None
        if opts["since"]:
            try:
                since = datetime.strptime(opts["since"], "%Y-%m-%d").replace(tzinfo=dt_timezone.utc)
            except ValueError:
                raise CommandError("--since must be YYYY-MM-DD")

        connection.set_schema(schema)

        config = LeadSourceConfig.objects.filter(
            source__in=[LeadSource.META_FACEBOOK, LeadSource.META_INSTAGRAM]
        ).first()
        if not config:
            raise CommandError(f"No Meta integration config in schema '{schema}'.")

        token = (config.credentials or {}).get("access_token", "")
        page_id = (config.credentials or {}).get("page_id") or (config.options or {}).get("page_id")
        if not token or not page_id:
            raise CommandError("Meta config is missing access_token or page_id.")

        mapping = (config.options or {}).get("field_mapping", {})
        dup_action = (config.options or {}).get("duplicate_action", "skip")
        view = MetaLeadAdsWebhookView()  # reuse its _create_or_update_lead

        # Resolve which forms to process.
        if opts["form"]:
            form_ids = [opts["form"]]
        else:
            form_ids = self._list_form_ids(page_id, token)
        self.stdout.write(f"Processing {len(form_ids)} form(s) in schema '{schema}'.")

        total_created = total_skipped = total_failed = total_seen = 0
        quota_reached = False

        for form_id in form_ids:
            self.stdout.write(f"\n→ Form {form_id}")
            for lead in self._iter_form_leads(form_id, token):
                total_seen += 1

                # Optional date filter (Meta returns created_time like 2026-05-16T...).
                if since:
                    ct = lead.get("created_time", "")
                    try:
                        created = datetime.fromisoformat(ct.replace("Z", "+00:00"))
                        if created < since:
                            continue
                    except Exception:
                        pass

                raw_fields = flatten_meta_field_data(lead.get("field_data", []))
                lead_data, custom_values = apply_field_mapping(raw_fields, mapping)
                lead_data["source_lead_id"] = lead.get("id")
                lead_data["custom_values"] = custom_values

                if not lead_data.get("phone"):
                    total_failed += 1
                    self.stderr.write(f"   ! skip (no phone): {raw_fields}")
                    continue

                if dry_run:
                    total_created += 1
                    self.stdout.write(f"   [dry-run] would import: {lead_data.get('name','?')} / {lead_data.get('phone')}")
                    continue

                try:
                    created, _ = view._create_or_update_lead(lead_data, config, duplicate_action=dup_action)
                    if created:
                        total_created += 1
                    else:
                        total_skipped += 1
                except PlanLimitExceededException as exc:
                    # Every remaining lead would hit the same cap — stop here.
                    self.stderr.write(self.style.WARNING(
                        f"\n   ! Plan lead limit reached: {exc.detail}\n"
                        f"   ! Stopping. Upgrade the plan (or raise max_leads) and re-run."
                    ))
                    quota_reached = True
                    break
                except Exception as exc:
                    total_failed += 1
                    self.stderr.write(f"   ! failed: {exc}")

            if quota_reached:
                break

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. seen={total_seen} created={total_created} "
            f"skipped_existing={total_skipped} failed={total_failed}"
            + (" (dry-run, nothing written)" if dry_run else "")
        ))

    def _list_form_ids(self, page_id, token):
        resp = requests.get(
            f"{GRAPH}/{page_id}/leadgen_forms",
            params={"access_token": token, "fields": "id,name,status", "limit": 100},
            timeout=20,
        )
        resp.raise_for_status()
        return [f["id"] for f in resp.json().get("data", [])]

    def _iter_form_leads(self, form_id, token):
        """Yield each lead dict from a form, following pagination."""
        url = f"{GRAPH}/{form_id}/leads"
        params = {"access_token": token, "fields": "id,created_time,field_data", "limit": 100}
        while url:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code != 200:
                self.stderr.write(f"   ! Graph error {resp.status_code}: {resp.text[:300]}")
                return
            data = resp.json()
            for lead in data.get("data", []):
                yield lead
            # Follow paging.next (already a full URL with cursor); drop params after first page.
            url = data.get("paging", {}).get("next")
            params = None
