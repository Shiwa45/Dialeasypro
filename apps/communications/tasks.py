"""
TeleCRM Backend — apps/communications/tasks.py

Celery tasks for bulk and single-message communication.

send_bulk_whatsapp_campaign  : Fan out WhatsApp messages for a campaign
send_bulk_email_campaign     : Fan out emails for a campaign
send_bulk_sms_campaign       : Fan out SMS for a campaign
send_single_whatsapp         : Send one WhatsApp message
send_single_sms              : Send one SMS
update_whatsapp_delivery     : Process provider delivery webhook
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.core.tasks import TenantAwareTask

logger = logging.getLogger(__name__)

# ---- Daily per-channel rate limits (enforced per tenant by plan) ----
CHUNK_SIZE = 50          # messages per Celery sub-task
INTER_CHUNK_DELAY = 2    # seconds between chunks (avoid provider throttle)


# ============================================================
# WhatsApp Campaigns
# ============================================================

@shared_task(base=TenantAwareTask, bind=True, time_limit=7200)
def send_bulk_whatsapp_campaign(self, schema_name: str, campaign_id: str):
    """
    Main coordinator for a WhatsApp bulk campaign.
    Resolves audience → chunks leads → spawns send_whatsapp_chunk sub-tasks.
    """
    from apps.communications.models import BulkCampaign, CampaignRecipient
    from apps.leads.models import Lead

    try:
        campaign = BulkCampaign.objects.get(pk=campaign_id)
    except BulkCampaign.DoesNotExist:
        logger.error(f"[WA Campaign] {campaign_id} not found in {schema_name}")
        return

    # Mark as running
    campaign.status = "running"
    campaign.started_at = timezone.now()
    campaign.failure_reason = ""  # a relaunch must not show the last failure
    campaign.save(update_fields=["status", "started_at", "failure_reason"])

    try:
        # Resolve audience
        leads = _resolve_campaign_audience(campaign)

        # Check plan limit
        _check_daily_whatsapp_limit(schema_name, len(leads))

        # Create recipient rows (bulk)
        recipients = [
            CampaignRecipient(
                campaign=campaign,
                lead=lead,
                phone=lead.phone,
                status="pending",
            )
            for lead in leads
            if not lead.is_dnd  # Skip DND numbers
        ]
        CampaignRecipient.objects.bulk_create(recipients, ignore_conflicts=True)

        # Count the rows that exist, not the list we tried to insert:
        # ignore_conflicts silently drops duplicates (unique campaign+lead), so
        # len(recipients) over-reports on a relaunch and the progress bar never
        # reaches 100%.
        campaign.total_recipients = CampaignRecipient.objects.filter(
            campaign=campaign
        ).count()
        campaign.save(update_fields=["total_recipients"])

        # Dispatch chunks
        recipient_ids = list(
            CampaignRecipient.objects.filter(
                campaign=campaign, status="pending"
            ).values_list("id", flat=True)
        )

        for i, chunk_start in enumerate(range(0, len(recipient_ids), CHUNK_SIZE)):
            chunk = recipient_ids[chunk_start:chunk_start + CHUNK_SIZE]
            send_whatsapp_chunk.apply_async(
                args=[schema_name, campaign_id, chunk],
                countdown=i * INTER_CHUNK_DELAY,
                queue="bulk_ops",
            )

        logger.info(
            f"[WA Campaign] {campaign.name} dispatched "
            f"{len(recipient_ids)} messages in {len(recipient_ids)//CHUNK_SIZE + 1} chunks"
        )

    except Exception as exc:
        logger.error(f"[WA Campaign] Failed: {exc}", exc_info=True)
        _fail_campaign(campaign, exc)
        raise


@shared_task(base=TenantAwareTask, bind=True, max_retries=2)
def send_whatsapp_chunk(self, schema_name: str, campaign_id: str, recipient_ids: list):
    """
    Send WhatsApp messages to a chunk of recipients.
    Updates CampaignRecipient rows with delivery status.
    """
    from apps.communications.models import BulkCampaign, CampaignRecipient, WhatsAppMessage
    from apps.leads.models import LeadActivity

    try:
        campaign = BulkCampaign.objects.select_related("template").get(pk=campaign_id)
    except Exception as exc:
        logger.error(f"[WA Chunk] Setup failed: {exc}")
        return

    if _campaign_halted(campaign, "WA Chunk"):
        return

    # status="pending" is load-bearing, not a tidy-up. Without it a chunk that
    # is retried or redelivered re-sends to recipients already marked sent —
    # a real message to a real customer, twice.
    recipients = CampaignRecipient.objects.filter(
        id__in=recipient_ids, status="pending"
    ).select_related("lead")

    provider_service, provider_slug = _get_whatsapp_provider()

    sent, failed = 0, 0
    for recipient in recipients:
        # Re-checked inside the loop: a chunk of 50 takes a while, and an
        # admin hitting Pause expects it to stop now, not after this chunk.
        if _campaign_halted(campaign_id, "WA Chunk"):
            break
        try:
            # Render template with lead variables
            rendered_body = (
                campaign.template.render(recipient.lead)
                if campaign.template else ""
            )

            # Call provider API
            message_id = provider_service.send_template(
                phone=recipient.phone,
                template_id=campaign.template.provider_template_id if campaign.template else "",
                variables=_extract_variables(campaign.template, recipient.lead),
            )

            # Save WhatsApp message record
            msg = WhatsAppMessage.objects.create(
                lead=recipient.lead,
                direction="outbound",
                message_type="template",
                content=rendered_body,
                template=campaign.template,
                provider=provider_slug,
                provider_message_id=message_id,
                status="sent",
                sent_at=timezone.now(),
                campaign=campaign,
            )

            recipient.status = "sent"
            recipient.provider_message_id = message_id
            recipient.sent_at = timezone.now()
            recipient.save(update_fields=["status", "provider_message_id", "sent_at"])

            # Activity log on lead
            LeadActivity.objects.create(
                lead=recipient.lead,
                activity_type="whatsapp",
                description=f"WhatsApp sent via campaign: {campaign.name}",
                meta={"campaign_id": str(campaign_id), "message_id": str(msg.id)},
            )
            sent += 1

        except Exception as exc:
            logger.warning(f"[WA Chunk] Failed for {recipient.phone}: {exc}")
            recipient.status = "failed"
            recipient.error_message = str(exc)[:500]
            recipient.save(update_fields=["status", "error_message"])
            failed += 1

    # Update campaign counters atomically
    from django.db.models import F
    BulkCampaign.objects.filter(pk=campaign_id).update(
        sent_count=F("sent_count") + sent,
        failed_count=F("failed_count") + failed,
    )

    # Check if campaign is complete
    _check_campaign_completion(campaign_id)


# ============================================================
# Email Campaigns
# ============================================================

@shared_task(base=TenantAwareTask, bind=True, time_limit=7200)
def send_bulk_email_campaign(self, schema_name: str, campaign_id: str):
    """Coordinator for bulk email campaign."""
    from apps.communications.models import BulkCampaign, CampaignRecipient

    try:
        campaign = BulkCampaign.objects.get(pk=campaign_id)
    except BulkCampaign.DoesNotExist:
        return

    campaign.status = "running"
    campaign.started_at = timezone.now()
    campaign.failure_reason = ""  # a relaunch must not show the last failure
    campaign.save(update_fields=["status", "started_at", "failure_reason"])

    try:
        leads = _resolve_campaign_audience(campaign)
        eligible = [lead for lead in leads if lead.email]
        # Email had no cap check at all, so Plan.max_email_bulk_per_day was
        # decorative.
        _enforce_daily_limit("email", len(eligible))
        recipients = [
            CampaignRecipient(campaign=campaign, lead=lead, phone=lead.phone, status="pending")
            for lead in eligible
        ]
        CampaignRecipient.objects.bulk_create(recipients, ignore_conflicts=True)
        campaign.total_recipients = CampaignRecipient.objects.filter(
            campaign=campaign
        ).count()
        campaign.save(update_fields=["total_recipients"])

        recipient_ids = list(
            CampaignRecipient.objects.filter(campaign=campaign, status="pending")
            .values_list("id", flat=True)
        )
        for i, chunk_start in enumerate(range(0, len(recipient_ids), CHUNK_SIZE)):
            chunk = recipient_ids[chunk_start:chunk_start + CHUNK_SIZE]
            send_email_chunk.apply_async(
                args=[schema_name, campaign_id, chunk],
                countdown=i * INTER_CHUNK_DELAY,
                queue="bulk_ops",
            )
    except Exception as exc:
        logger.error(f"[Email Campaign] Failed: {exc}", exc_info=True)
        _fail_campaign(campaign, exc)
        raise


@shared_task(base=TenantAwareTask, bind=True, max_retries=2)
def send_email_chunk(self, schema_name: str, campaign_id: str, recipient_ids: list):
    """Send emails to a chunk of recipients."""
    from apps.communications.models import BulkCampaign, CampaignRecipient, EmailLog
    from django.core.mail import send_mail
    from django.db.models import F

    try:
        campaign = BulkCampaign.objects.get(pk=campaign_id)
    except Exception as exc:
        logger.error(f"[Email Chunk] Setup failed: {exc}")
        return

    if _campaign_halted(campaign, "Email Chunk"):
        return

    recipients = CampaignRecipient.objects.filter(
        id__in=recipient_ids, status="pending"
    ).select_related("lead")

    # One SMTP connection for the whole chunk. send_mail() opens and tears down
    # a connection per message, which is both slow and a good way to trip an
    # SMTP provider's connection-rate limit halfway through a campaign.
    from django.core.mail import get_connection
    mail_connection = get_connection(fail_silently=False)
    try:
        mail_connection.open()
    except Exception as exc:
        # The mail server being down is not 50 individual failures to
        # diagnose; mark the chunk and let the reason show once per recipient.
        logger.error(f"[Email Chunk] Could not open SMTP connection: {exc}")
        marked = CampaignRecipient.objects.filter(
            id__in=recipient_ids, status="pending"
        ).update(status="failed", error_message=f"Mail server unreachable: {exc}"[:500])
        if marked:
            BulkCampaign.objects.filter(pk=campaign_id).update(
                failed_count=F("failed_count") + marked
            )
        _check_campaign_completion(campaign_id)
        return

    sent, failed = 0, 0
    for recipient in recipients:
        if _campaign_halted(campaign_id, "Email Chunk"):
            break
        lead = recipient.lead
        if not lead.email:
            recipient.status = "skipped"
            recipient.error_message = "No email address"
            recipient.save(update_fields=["status", "error_message"])
            continue
        try:
            from apps.core.utils import render_template_with_variables
            subject = render_template_with_variables(
                campaign.email_subject, {"name": lead.name, "city": lead.city}
            )
            body = render_template_with_variables(
                campaign.email_body, {"name": lead.name, "city": lead.city, "phone": lead.phone}
            )
            send_mail(
                subject=subject,
                message=body,
                from_email=None,  # Uses DEFAULT_FROM_EMAIL
                recipient_list=[lead.email],
                fail_silently=False,
                connection=mail_connection,
            )
            EmailLog.objects.create(
                lead=lead, campaign=campaign, to_email=lead.email,
                subject=subject, body=body, status="sent", sent_at=timezone.now(),
            )
            recipient.status = "sent"
            recipient.sent_at = timezone.now()
            recipient.save(update_fields=["status", "sent_at"])
            sent += 1
        except Exception as exc:
            logger.warning(f"[Email Chunk] Failed for {lead.email}: {exc}")
            recipient.status = "failed"
            recipient.error_message = str(exc)[:500]
            recipient.save(update_fields=["status", "error_message"])
            failed += 1

    try:
        mail_connection.close()
    except Exception:  # noqa: BLE001 — closing must not fail a sent chunk
        pass

    BulkCampaign.objects.filter(pk=campaign_id).update(
        sent_count=F("sent_count") + sent,
        failed_count=F("failed_count") + failed,
    )
    _check_campaign_completion(campaign_id)


# ============================================================
# SMS Campaigns
# ============================================================

@shared_task(base=TenantAwareTask, bind=True, time_limit=7200)
def send_bulk_sms_campaign(self, schema_name: str, campaign_id: str):
    """Coordinator for bulk SMS campaign. Enforces TRAI DND."""
    from apps.communications.models import BulkCampaign, CampaignRecipient

    try:
        campaign = BulkCampaign.objects.get(pk=campaign_id)
    except BulkCampaign.DoesNotExist:
        return

    campaign.status = "running"
    campaign.started_at = timezone.now()
    campaign.failure_reason = ""  # a relaunch must not show the last failure
    campaign.save(update_fields=["status", "started_at", "failure_reason"])

    try:
        leads = _resolve_campaign_audience(campaign)
        # Filter: skip DND-registered numbers for SMS (TRAI regulation)
        eligible = [l for l in leads if not l.is_dnd]
        skipped_dnd = len(leads) - len(eligible)
        if skipped_dnd:
            logger.info(f"[SMS Campaign] Skipped {skipped_dnd} DND-registered leads")

        # Same omission as email: Plan.max_sms_per_day was never consulted.
        _enforce_daily_limit("sms", len(eligible))

        recipients = [
            CampaignRecipient(campaign=campaign, lead=lead, phone=lead.phone, status="pending")
            for lead in eligible
        ]
        CampaignRecipient.objects.bulk_create(recipients, ignore_conflicts=True)
        campaign.total_recipients = CampaignRecipient.objects.filter(
            campaign=campaign
        ).count()
        campaign.save(update_fields=["total_recipients"])

        recipient_ids = list(
            CampaignRecipient.objects.filter(campaign=campaign, status="pending")
            .values_list("id", flat=True)
        )
        for i, chunk_start in enumerate(range(0, len(recipient_ids), CHUNK_SIZE)):
            chunk = recipient_ids[chunk_start:chunk_start + CHUNK_SIZE]
            send_sms_chunk.apply_async(
                args=[schema_name, campaign_id, chunk],
                countdown=i * INTER_CHUNK_DELAY,
                queue="bulk_ops",
            )
    except Exception as exc:
        logger.error(f"[SMS Campaign] Failed: {exc}", exc_info=True)
        _fail_campaign(campaign, exc)
        raise


@shared_task(base=TenantAwareTask, bind=True, max_retries=2)
def send_sms_chunk(self, schema_name: str, campaign_id: str, recipient_ids: list):
    """Send SMS to a chunk of recipients via configured provider."""
    from apps.communications.models import BulkCampaign, CampaignRecipient, SMSLog
    from django.db.models import F

    try:
        campaign = BulkCampaign.objects.get(pk=campaign_id)
    except Exception as exc:
        logger.error(f"[SMS Chunk] Setup failed: {exc}")
        return

    if _campaign_halted(campaign, "SMS Chunk"):
        return

    recipients = CampaignRecipient.objects.filter(
        id__in=recipient_ids, status="pending"
    ).select_related("lead")

    sms_service = _get_sms_provider()
    sent, failed = 0, 0

    for recipient in recipients:
        if _campaign_halted(campaign_id, "SMS Chunk"):
            break
        lead = recipient.lead
        try:
            from apps.core.utils import render_template_with_variables
            message = render_template_with_variables(
                campaign.sms_text, {"name": lead.name, "city": lead.city}
            )
            msg_id = sms_service.send(
                phone=recipient.phone,
                message=message,
                sender_id=campaign.sms_sender_id,
            )
            SMSLog.objects.create(
                lead=lead, campaign=campaign,
                phone_number=recipient.phone, message=message,
                sender_id=campaign.sms_sender_id,
                status="sent", sent_at=timezone.now(),
                provider_message_id=msg_id,
            )
            recipient.status = "sent"
            recipient.sent_at = timezone.now()
            recipient.provider_message_id = msg_id
            recipient.save(update_fields=["status", "sent_at", "provider_message_id"])
            sent += 1
        except Exception as exc:
            logger.warning(f"[SMS Chunk] Failed for {recipient.phone}: {exc}")
            recipient.status = "failed"
            recipient.error_message = str(exc)[:500]
            recipient.save(update_fields=["status", "error_message"])
            failed += 1

    BulkCampaign.objects.filter(pk=campaign_id).update(
        sent_count=F("sent_count") + sent,
        failed_count=F("failed_count") + failed,
    )
    _check_campaign_completion(campaign_id)


# ============================================================
# Single message tasks
# ============================================================

@shared_task(base=TenantAwareTask, bind=True, max_retries=3)
def send_single_whatsapp(self, schema_name: str, lead_id: int, message: str,
                          template_id: int = None, sent_by_id: int = None):
    """Send a single WhatsApp message to one lead (click-to-send from lead detail)."""
    from apps.communications.models import WhatsAppMessage, WhatsAppTemplate
    from apps.leads.models import Lead, LeadActivity

    try:
        lead = Lead.objects.get(pk=lead_id, is_deleted=False)
        template = WhatsAppTemplate.objects.get(pk=template_id) if template_id else None
        sent_by = None
        if sent_by_id:
            from apps.authentication.models import Agent
            sent_by = Agent.objects.filter(pk=sent_by_id).first()

        provider_service, provider_slug = _get_whatsapp_provider()

        if template:
            msg_id = provider_service.send_template(
                phone=lead.phone,
                template_id=template.provider_template_id,
                variables=_extract_variables(template, lead),
            )
        else:
            msg_id = provider_service.send_text(phone=lead.phone, message=message)

        WhatsAppMessage.objects.create(
            lead=lead, sent_by=sent_by, direction="outbound",
            message_type="template" if template else "text",
            content=message, template=template,
            provider=provider_slug,
            provider_message_id=msg_id, status="sent", sent_at=timezone.now(),
        )
        LeadActivity.objects.create(
            lead=lead, activity_type="whatsapp",
            description=f"WhatsApp sent: {message[:80]}",
            performed_by=sent_by,
        )
        lead.log_contact(contact_type="whatsapp")
        logger.info(f"[WA] Sent to {lead.phone} ({schema_name})")

    except Exception as exc:
        logger.error(f"[WA Single] Failed: {exc}")
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


@shared_task(base=TenantAwareTask, bind=True, max_retries=3)
def send_single_sms(self, schema_name: str, lead_id: int, message: str,
                    sender_id: str = "", sent_by_id: int = None):
    """Send a single SMS to one lead."""
    from apps.communications.models import SMSLog
    from apps.leads.models import Lead, LeadActivity

    try:
        lead = Lead.objects.get(pk=lead_id, is_deleted=False)
        if lead.is_dnd:
            logger.warning(f"[SMS] Skipped DND lead {lead_id}")
            return

        sms_service = _get_sms_provider()
        msg_id = sms_service.send(phone=lead.phone, message=message, sender_id=sender_id)

        sent_by = None
        if sent_by_id:
            from apps.authentication.models import Agent
            sent_by = Agent.objects.filter(pk=sent_by_id).first()

        SMSLog.objects.create(
            lead=lead, phone_number=lead.phone, message=message,
            sender_id=sender_id, status="sent", sent_at=timezone.now(),
            provider_message_id=msg_id,
        )
        LeadActivity.objects.create(
            lead=lead, activity_type="sms",
            description=f"SMS sent: {message[:80]}",
            performed_by=sent_by,
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


# ============================================================
# Helpers
# ============================================================

def _resolve_campaign_audience(campaign):
    """Resolve campaign audience_filters to a queryset of leads."""
    from apps.leads.models import Lead
    from django.db.models import Q

    qs = Lead.objects.filter(is_deleted=False)
    filters = campaign.audience_filters or {}

    if status := filters.get("status"):
        qs = qs.filter(status=status)
    if city := filters.get("city"):
        qs = qs.filter(city__icontains=city)
    if source := filters.get("source"):
        qs = qs.filter(source=source)
    if assigned_to := filters.get("assigned_to"):
        qs = qs.filter(assigned_to_id=assigned_to)
    if tags := filters.get("tags"):
        for tag in tags:
            qs = qs.filter(tags__contains=tag)

    return list(qs)


# Campaign states in which a chunk must stop sending. "paused" and
# "cancelled" are the point of the Pause button; "failed" and "completed"
# mean something already finished this campaign.
HALTED_STATUSES = {"paused", "cancelled", "failed", "completed"}


def _fail_campaign(campaign, exc: Exception):
    """
    Mark a campaign failed with a reason an admin can act on.

    PlanLimitExceededException carries a sentence written for a person
    ("Daily SMS limit reached: 4000/4000"); anything else falls back to the
    exception text, which is at least a starting point. Never let this bury
    the original error — the caller re-raises.
    """
    from apps.core.exceptions import PlanLimitExceededException

    if isinstance(exc, PlanLimitExceededException):
        reason = str(getattr(exc, "detail", exc))
    else:
        reason = f"{exc.__class__.__name__}: {exc}"

    type(campaign).objects.filter(pk=campaign.pk).update(
        status="failed", failure_reason=reason[:500],
    )


def _campaign_halted(campaign_or_id, tag: str) -> bool:
    """
    Whether this campaign should stop sending right now.

    Pausing a campaign revokes the coordinator task, but by then the
    coordinator has usually finished and the per-chunk tasks are already
    queued with their countdowns — revoking it stops nothing. The chunks have
    to check for themselves, which is why this is consulted before a chunk
    starts AND between recipients: a 50-message chunk takes long enough that
    "stops after this chunk" is not what an admin pressing Pause means.

    Always re-read from the database; the campaign object a chunk loaded at
    start-up cannot know about a pause that happened since.
    """
    from apps.communications.models import BulkCampaign

    campaign_id = getattr(campaign_or_id, "pk", campaign_or_id)
    status = (
        BulkCampaign.objects.filter(pk=campaign_id)
        .values_list("status", flat=True)
        .first()
    )
    if status in HALTED_STATUSES:
        logger.info(f"[{tag}] Campaign {campaign_id} is {status} — stopping.")
        return True
    return False


def _current_plan():
    from apps.core.constants import SubscriptionStatus
    from apps.plans.models import Subscription

    return (
        Subscription.objects.filter(status__in=SubscriptionStatus.ACTIVE_STATUSES)
        .select_related("plan")
        .first()
    )


def _enforce_daily_limit(channel: str, count: int):
    """
    Refuse a campaign that would breach the plan's daily cap for its channel.

    Counts what has actually been sent today rather than assuming zero — the
    previous version compared `0 + count`, so a tenant could run twenty
    campaigns of just under the cap and never trip it. Only bulk sends are
    counted, matching what the plan field is named after.

    A missing subscription or an unreadable counter is not a reason to block a
    send, so both fall through permissively; the cap is a billing guardrail,
    not a security control.
    """
    from apps.communications.models import EmailLog, SMSLog, WhatsAppMessage
    from apps.core.exceptions import PlanLimitExceededException

    sub = _current_plan()
    if not sub:
        return

    today = timezone.localdate()
    plan = sub.plan

    if channel == "whatsapp":
        limit = plan.max_whatsapp_bulk_per_day
        used = WhatsAppMessage.objects.filter(
            direction="outbound", campaign__isnull=False, created_at__date=today,
        ).count()
    elif channel == "email":
        limit = plan.max_email_bulk_per_day
        used = EmailLog.objects.filter(
            campaign__isnull=False, created_at__date=today,
        ).count()
    elif channel == "sms":
        limit = plan.max_sms_per_day
        used = SMSLog.objects.filter(
            campaign__isnull=False, created_at__date=today,
        ).count()
    else:
        return

    if not limit:
        return  # 0/None on the plan means unlimited

    if used + count > limit:
        raise PlanLimitExceededException(
            limit_type=f"{channel}_per_day",
            current=used,
            max_allowed=limit,
        )


def _check_daily_whatsapp_limit(schema_name: str, count: int):
    """Back-compat shim for the WhatsApp coordinator."""
    _enforce_daily_limit("whatsapp", count)


def _check_campaign_completion(campaign_id: str):
    """
    Mark the campaign complete once every recipient has been processed.

    Scoped to status="running": the previous version updated unconditionally,
    so the last chunk of a campaign an admin had just PAUSED would flip it to
    "completed" — the pause silently undone, and the remaining recipients
    stranded as pending under a campaign that claims it finished.
    """
    from apps.communications.models import BulkCampaign, CampaignRecipient

    pending = CampaignRecipient.objects.filter(
        campaign_id=campaign_id, status="pending"
    ).count()
    if pending:
        return
    BulkCampaign.objects.filter(pk=campaign_id, status="running").update(
        status="completed", completed_at=timezone.now()
    )


def _get_whatsapp_provider():
    """
    Build the WhatsApp provider from the *tenant's* saved config.

    The provider and its credentials come from the tenant's WhatsAppConfig
    singleton, not from a template or global settings — every tenant sends
    through their own WhatsApp Business account. Returns (provider, slug) so
    callers can record which provider actually sent the message; slug is
    "mock" when the tenant hasn't configured (or activated) one.
    """
    from apps.communications.models import WhatsAppConfig
    from apps.communications.providers.whatsapp import build_provider

    config = WhatsAppConfig.objects.filter(singleton=1).first()
    provider = build_provider(config)
    slug = config.provider if (config and config.is_active) else "mock"
    return provider, slug


def _get_sms_provider():
    """
    The tenant's SMS provider, or the mock when none is configured.

    This used to return MockSMSProvider() unconditionally — so every bulk SMS
    campaign logged a fake message id, marked every recipient "sent", and
    delivered nothing. The campaign reported 100% success and no SMS existed.

    Credentials are platform-level (settings) because there is no per-tenant
    SMS config model yet, unlike WhatsApp. Add one before selling SMS to
    tenants who need their own sender ID and billing.
    """
    from django.conf import settings

    from apps.communications.providers.sms import MockSMSProvider, MSG91Provider

    if getattr(settings, "MSG91_AUTH_KEY", ""):
        return MSG91Provider()

    logger.warning(
        "[SMS] No provider configured (MSG91_AUTH_KEY unset) — messages are "
        "logged, not sent."
    )
    return MockSMSProvider()


def _extract_variables(template, lead) -> list:
    """Extract ordered variable values from a lead based on template mapping."""
    if not template or not template.variable_mapping:
        return []
    result = []
    for i in range(1, len(template.variable_mapping) + 1):
        field = template.variable_mapping.get(str(i), "")
        result.append(str(getattr(lead, field, "") or ""))
    return result


@shared_task(base=TenantAwareTask, bind=True)
def launch_scheduled_campaigns(self, schema_name: str = None):
    """
    Beat-scheduled task: check for campaigns scheduled to start now.
    Runs every 5 minutes. Dispatches per-tenant if schema_name given,
    otherwise dispatches across all tenants.
    """
    from apps.communications.models import BulkCampaign
    from django.db import connection

    if not schema_name:
        from apps.core.utils import get_all_tenant_schemas
        for schema in get_all_tenant_schemas():
            launch_scheduled_campaigns.apply_async(
                args=[schema], queue="bulk_ops"
            )
        return

    now = timezone.now()
    due_campaigns = BulkCampaign.objects.filter(
        status="scheduled",
        scheduled_at__lte=now,
    )

    TASK_MAP = {
        "whatsapp": send_bulk_whatsapp_campaign,
        "email": send_bulk_email_campaign,
        "sms": send_bulk_sms_campaign,
    }

    for campaign in due_campaigns:
        task_fn = TASK_MAP.get(campaign.channel)
        if not task_fn:
            logger.warning(
                f"[Task] Scheduled campaign {campaign.name} has unknown channel "
                f"'{campaign.channel}' — skipping."
            )
            continue

        # Claim it first, conditionally. Beat ticks every few minutes and the
        # coordinator only marks the campaign "running" once it actually
        # starts — so a backed-up queue let the next tick dispatch the same
        # campaign again, sending the whole audience twice. Whoever wins this
        # UPDATE owns the launch.
        claimed = BulkCampaign.objects.filter(
            pk=campaign.pk, status="scheduled"
        ).update(status="running", started_at=timezone.now())
        if not claimed:
            continue

        task_fn.apply_async(
            args=[schema_name, str(campaign.id)],
            queue="bulk_ops",
        )
        logger.info(f"[Task] Launched scheduled campaign: {campaign.name}")
