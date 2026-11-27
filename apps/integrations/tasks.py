"""
TeleCRM Backend — apps/integrations/tasks.py

Async processing for inbound integration webhooks.

Meta gives a webhook about 20 seconds and retries anything slower, so the HTTP
handler only validates, logs the raw payload and returns 200 — the CRM work
(contact, conversation, message, lead, ad attribution) happens here, on the
`integrations` queue.

Retries are safe: every event claims a unique dedupe key inside the same
transaction that writes the CRM rows (see meta_whatsapp.process_message), so a
retried task re-does nothing it already did.
"""
import logging

from celery import shared_task
from django.utils import timezone

from apps.core.tasks import TenantAwareTask

logger = logging.getLogger(__name__)


@shared_task(
    base=TenantAwareTask,
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="integrations",
)
def process_meta_whatsapp_webhook(self, schema_name: str, webhook_log_id: str):
    """
    Turn one logged Meta WhatsApp delivery into CRM records.

    Takes the WebhookLog id rather than the payload itself: the payload is
    already durably stored, the broker message stays small, and a delivery can
    be replayed by hand from the log row if processing ever needs re-running.
    """
    from apps.integrations.meta_whatsapp import get_config, process_payload
    from apps.integrations.models import WebhookLog

    try:
        log = WebhookLog.objects.get(pk=webhook_log_id)
    except WebhookLog.DoesNotExist:
        logger.error(
            "[Meta CTWA] WebhookLog %s missing in schema %s — nothing to process",
            webhook_log_id, schema_name,
        )
        return {"status": "missing_log"}

    config = get_config()

    try:
        summary = process_payload(log.payload, config, webhook_log=log)
    except Exception as exc:  # noqa: BLE001 — retry the whole delivery
        log.error = str(exc)[:500]
        log.save(update_fields=["error"])
        logger.error(
            "[Meta CTWA] Delivery %s failed in %s: %s",
            webhook_log_id, schema_name, exc, exc_info=True,
        )
        raise self.retry(exc=exc)

    log.processed = True
    log.leads_created = summary["leads_created"]
    log.leads_updated = summary["leads_updated"]
    log.error = summary["last_error"]
    log.save(update_fields=["processed", "leads_created", "leads_updated", "error"])

    _record_health(config, summary)

    logger.info(
        "[Meta CTWA] Delivery %s done | messages=%s statuses=%s created=%s "
        "updated=%s duplicates=%s errors=%s",
        webhook_log_id, summary["messages"], summary["statuses"],
        summary["leads_created"], summary["leads_updated"],
        summary["duplicates"], summary["errors"],
    )
    return summary


def _record_health(config, summary: dict):
    """
    Keep the integrations screen honest about what last arrived — on each
    account a message was filed under, or the default one for a delivery
    that carried only receipts.
    """
    from django.db.models import F

    from apps.communications.models import WhatsAppConfig

    by_account = summary.get("by_account") or {}
    if not by_account and config is not None:
        by_account = {config.pk: 0}
    for pk, count in by_account.items():
        WhatsAppConfig.objects.filter(pk=pk).update(
            last_webhook_at=timezone.now(),
            last_webhook_error=summary["last_error"][:500],
            total_inbound_messages=F("total_inbound_messages") + count,
            updated_at=timezone.now(),
        )


@shared_task(
    base=TenantAwareTask,
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    queue="integrations",
)
def enrich_ctwa_attribution(self, schema_name: str, conversation_id: str):
    """
    Retry the campaign/ad-set/ad name lookup for one conversation.

    Split out so a Marketing API outage, or an `ads_read` permission granted
    only after the lead arrived, can be recovered without replaying webhooks.
    """
    from apps.communications.models import WhatsAppConversation
    from apps.integrations.meta_whatsapp import config_for_number, enrich_attribution, get_config

    conversation = WhatsAppConversation.objects.filter(pk=conversation_id).first()
    if conversation is None:
        return {"status": "missing"}

    config = config_for_number(conversation.business_phone_number_id, fallback=get_config())
    enriched = enrich_attribution(conversation, config)
    return {"status": "enriched" if enriched else "unchanged"}


# ============================================================
# Meta Lead Ads via "Continue with Facebook"
# ============================================================

@shared_task(
    base=TenantAwareTask,
    bind=True,
    max_retries=4,
    default_retry_delay=60,
    queue="integrations",
)
def process_meta_leadgen(self, schema_name: str, page_id: str, form_id: str, leadgen_id: str):
    """
    One lead from the platform webhook, in its tenant's schema.

    A Graph failure is retried (Meta sometimes needs a moment before a new
    lead is readable); the 5-minute poll is the backstop if every retry fails.
    """
    from apps.integrations.meta_connect import MetaError, handle_leadgen

    try:
        return handle_leadgen(page_id, form_id, leadgen_id, via="webhook")
    except MetaError as exc:
        logger.warning("[MetaConnect] lead %s in %s: %s", leadgen_id, schema_name, exc.message)
        raise self.retry(exc=exc)


@shared_task(bind=True, queue="integrations")
def poll_meta_leads(self, schema_name: str = None):
    """
    Beat, every 5 minutes: fetch recent Meta leads for every tenant.

    The webhook delivers most leads in seconds; this catches what it misses
    (a delivery Meta gave up on, a Page whose webhook was never verified, the
    older manual token set-up that only a button used to pull). Leads already
    in the CRM are skipped, so overlap with the webhook is harmless.
    """
    if not schema_name:
        from apps.core.utils import get_all_tenant_schemas

        for schema in get_all_tenant_schemas():
            poll_meta_leads.apply_async(args=[schema], queue="integrations")
        return None

    from django_tenants.utils import schema_context

    with schema_context(schema_name):
        from apps.core.constants import LeadSource
        from apps.integrations.meta_connect import poll_tenant
        from apps.integrations.models import LeadSourceConfig, MetaLeadPage

        has_pages = MetaLeadPage.objects.filter(connected=True).exists()
        legacy = LeadSourceConfig.objects.filter(
            source=LeadSource.META_FACEBOOK, is_active=True,
        ).exclude(credentials={}).first()
        if not has_pages and not (legacy and (legacy.credentials or {}).get("access_token")):
            return None
        try:
            totals = poll_tenant()
        except Exception as exc:  # noqa: BLE001 — one tenant must not stop the rest
            logger.warning("[MetaConnect] poll failed in %s: %s", schema_name, exc, exc_info=True)
            return None
        if totals.get("created"):
            logger.info("[MetaConnect] poll %s imported %s lead(s)", schema_name, totals["created"])
        return totals
