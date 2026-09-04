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
    """Keep the integrations screen honest about what last arrived."""
    if config is None:
        return
    from django.db.models import F

    type(config).objects.filter(pk=config.pk).update(
        last_webhook_at=timezone.now(),
        last_webhook_error=summary["last_error"][:500],
        total_inbound_messages=F("total_inbound_messages") + summary["messages"],
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
    from apps.integrations.meta_whatsapp import enrich_attribution, get_config

    conversation = WhatsAppConversation.objects.filter(pk=conversation_id).first()
    if conversation is None:
        return {"status": "missing"}

    enriched = enrich_attribution(conversation, get_config())
    return {"status": "enriched" if enriched else "unchanged"}
