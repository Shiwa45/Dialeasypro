"""
TeleCRM Backend — apps/integrations/meta_sync.py

On-demand pull of Meta Lead Ads leads, shared by:
  - the "Sync now" button in the tenant UI (MetaSyncLeadsView)
  - the backfill_meta_leads management command

The realtime webhook only delivers leads submitted *after* setup, and can
occasionally miss events. This lets a tenant admin pull the newest leads
manually. Meta returns leads newest-first, so we fetch a bounded number per
form and rely on phone-based dedup to skip ones already in the CRM.
"""
import logging

import requests
from django.utils import timezone

from apps.core.exceptions import PlanLimitExceededException
from apps.integrations.field_mapping import apply_field_mapping, flatten_meta_field_data

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v25.0"


def sync_meta_leads(config, max_per_form: int = 200) -> dict:
    """
    Fetch the newest leads from each ACTIVE Meta form on the configured Page
    and import any that aren't already in the CRM.

    Returns a dict of counts, or {"error": ...} on a credential/API failure.
    Reuses MetaLeadAdsWebhookView._create_or_update_lead so imported leads are
    identical to webhook-delivered ones (mapping, dedup, assignment, activity).
    """
    from apps.integrations.views import MetaLeadAdsWebhookView

    token = (config.credentials or {}).get("access_token", "")
    page_id = (config.credentials or {}).get("page_id") or (config.options or {}).get("page_id")
    if not token or not page_id:
        return {"error": "missing_credentials"}

    mapping = (config.options or {}).get("field_mapping", {})
    dup_action = (config.options or {}).get("duplicate_action", "skip")
    view = MetaLeadAdsWebhookView()

    # Which forms? Only ACTIVE ones (archived forms won't get new leads).
    fr = requests.get(
        f"{GRAPH}/{page_id}/leadgen_forms",
        params={"access_token": token, "fields": "id,status", "limit": 100},
        timeout=20,
    )
    if fr.status_code != 200:
        logger.warning(f"[MetaSync] forms fetch failed: {fr.text[:300]}")
        return {"error": "forms_fetch_failed", "detail": fr.text[:300]}
    form_ids = [f["id"] for f in fr.json().get("data", []) if f.get("status") == "ACTIVE"]

    created = skipped = failed = seen = 0
    quota_reached = False

    for form_id in form_ids:
        if quota_reached:
            break
        url = f"{GRAPH}/{form_id}/leads"
        params = {"access_token": token, "fields": "id,created_time,field_data", "limit": 100}
        fetched = 0
        while url and fetched < max_per_form and not quota_reached:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code != 200:
                logger.warning(f"[MetaSync] leads fetch {form_id}: {r.text[:200]}")
                break
            data = r.json()
            for lead in data.get("data", []):
                seen += 1
                fetched += 1
                raw = flatten_meta_field_data(lead.get("field_data", []))
                lead_data, custom = apply_field_mapping(raw, mapping)
                lead_data["source_lead_id"] = lead.get("id")
                lead_data["custom_values"] = custom
                if not lead_data.get("phone"):
                    failed += 1
                    continue
                try:
                    was_created, _ = view._create_or_update_lead(
                        lead_data, config, duplicate_action=dup_action
                    )
                    if was_created:
                        created += 1
                    else:
                        skipped += 1
                except PlanLimitExceededException as exc:
                    # Stop immediately: every remaining lead would fail the same
                    # way, and marking hundreds as "failed" is just noise.
                    logger.warning(f"[MetaSync] lead quota reached: {exc.detail}")
                    quota_reached = True
                    break
                except Exception as exc:
                    failed += 1
                    logger.warning(f"[MetaSync] create failed: {exc}")
            if quota_reached:
                break
            url = data.get("paging", {}).get("next")
            params = None  # paging.next already carries the cursor + token

    if created:
        config.total_leads_received = (config.total_leads_received or 0) + created
        config.last_received_at = timezone.now()
        config.error_message = ""
        config.save(update_fields=["total_leads_received", "last_received_at", "error_message"])

    return {
        "created": created,
        "skipped": skipped,
        "failed": failed,
        "seen": seen,
        "forms": len(form_ids),
        "quota_reached": quota_reached,
    }
