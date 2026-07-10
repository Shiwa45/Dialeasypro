"""
TeleCRM Backend — apps/communications/models.py

Per-tenant communication models. All in TENANT schemas.

WhatsAppMessage   : Single WhatsApp message sent to or received from a lead.
WhatsAppTemplate  : Pre-approved message templates (required by Meta/providers).
BulkCampaign      : A bulk communication campaign (WhatsApp / Email / SMS).
CampaignRecipient : Per-recipient tracking row for a bulk campaign.
EmailLog          : Record of individual transactional/bulk emails.
SMSLog            : Record of individual SMS messages.

Indian context:
  WhatsApp providers: Interakt, AiSensy, Wati, Gupshup, 2Factor
  SMS providers: MSG91, TextLocal, Fast2SMS, Kaleyra
  TRAI DND rules enforced for SMS (WhatsApp exempt)
"""
import uuid
from django.db import models
from django.utils import timezone
from apps.core.crypto import EncryptedJSONField
from apps.core.models import TimeStampedModel, TimeStampedUUIDModel
from apps.core.constants import WhatsAppProvider


# ============================================================
# WhatsApp
# ============================================================
class WhatsAppConfig(TimeStampedModel):
    """
    A tenant's own WhatsApp Business connection.

    One row per tenant (singleton). Holds which provider they send through and
    that provider's credentials — encrypted at rest, so a database dump never
    exposes a tenant's API keys. Each provider needs a different bag of
    credentials; the shape is documented per-provider in providers/whatsapp.py.
    """

    # Enforced as a singleton in save(); a tenant sends through one provider.
    singleton = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)

    provider = models.CharField(
        max_length=30, choices=WhatsAppProvider.CHOICES, default=WhatsAppProvider.INTERAKT,
        help_text="Which WhatsApp Business API the tenant sends through.",
    )
    is_active = models.BooleanField(
        default=False, db_index=True,
        help_text="Off until credentials are verified. Sends fall back to a no-op while off.",
    )

    # Provider-specific secrets, e.g. Meta Cloud:
    #   {"access_token": "...", "phone_number_id": "...", "business_account_id": "..."}
    # Interakt / AiSensy: {"api_key": "..."}; WATI: {"access_token": "...", "api_endpoint": "..."};
    # Gupshup: {"api_key": "...", "app_name": "...", "source_number": "..."}
    credentials = EncryptedJSONField(default=dict, blank=True)

    # Default language code for template sends (Meta requires it per template).
    default_language = models.CharField(max_length=10, default="en")

    # Populated by the test-send / webhook so an admin can see it's working.
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        verbose_name = "WhatsApp Configuration"
        verbose_name_plural = "WhatsApp Configuration"

    def __str__(self):
        state = "active" if self.is_active else "inactive"
        return f"WhatsApp via {self.get_provider_display()} ({state})"

    def save(self, *args, **kwargs):
        self.singleton = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> "WhatsAppConfig":
        """The tenant's config row, created inactive on first access."""
        obj, _ = cls.objects.get_or_create(singleton=1)
        return obj

class WhatsAppTemplate(TimeStampedModel):
    """
    Pre-approved WhatsApp message template.
    Must be approved by Meta before use in bulk messaging.
    """

    CATEGORY_CHOICES = [
        ("marketing", "Marketing"),
        ("utility", "Utility / Transactional"),
        ("authentication", "Authentication (OTP)"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending Approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("paused", "Paused by Meta"),
    ]

    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="marketing")
    language = models.CharField(max_length=10, default="en", help_text="e.g. en, hi, mr")

    # ---- Header (text OR media) ----
    HEADER_TYPE_CHOICES = [
        ("none", "No header"),
        ("text", "Text"),
        ("image", "Image"),
        ("video", "Video"),
        ("document", "Document"),
    ]
    header_type = models.CharField(
        max_length=12, choices=HEADER_TYPE_CHOICES, default="none",
        help_text="WhatsApp template header type. 'image' shows a banner image.",
    )
    header_text = models.CharField(max_length=60, blank=True, default="")
    header_media_url = models.URLField(
        max_length=600, blank=True, default="",
        help_text="Image/video/document URL for a media header (e.g. Cloudinary).",
    )

    # Template body with {{1}}, {{2}} variable placeholders
    body_text = models.TextField(help_text="Use {{1}}, {{2}} for variables.")
    footer_text = models.CharField(max_length=60, blank=True, default="")

    # Variable mapping: {"1": "name", "2": "phone"} → maps {{1}} to lead.name
    variable_mapping = models.JSONField(
        default=dict, blank=True,
        help_text='Map {{N}} to Lead fields. e.g. {"1": "name", "2": "city"}',
    )

    # Provider-specific template ID (after approval)
    provider = models.CharField(max_length=30, choices=WhatsAppProvider.CHOICES, default=WhatsAppProvider.INTERAKT)
    provider_template_id = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)

    is_active = models.BooleanField(default=True)
    usage_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "WhatsApp Template"
        verbose_name_plural = "WhatsApp Templates"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} [{self.get_status_display()}]"

    def render(self, lead) -> str:
        """Render template body substituting {{N}} with lead field values."""
        text = self.body_text
        for var_num, field_name in self.variable_mapping.items():
            value = getattr(lead, field_name, "") or ""
            text = text.replace(f"{{{{{var_num}}}}}", str(value))
        return text


class WhatsAppMessage(TimeStampedModel):
    """
    A single WhatsApp message sent to or received from a lead.
    Maintains conversation thread per lead.
    """

    DIRECTION_CHOICES = [("outbound", "Outbound"), ("inbound", "Inbound")]
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("read", "Read"),
        ("failed", "Failed"),
        ("received", "Received"),
    ]
    MESSAGE_TYPES = [
        ("text", "Text"),
        ("template", "Template"),
        ("image", "Image"),
        ("document", "Document"),
        ("audio", "Audio"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(
        "leads.Lead", on_delete=models.CASCADE, related_name="whatsapp_messages"
    )
    sent_by = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="whatsapp_sent",
        help_text="Null for inbound messages or bulk sends.",
    )

    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, default="outbound", db_index=True)
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default="text")
    content = models.TextField(blank=True, default="")
    template = models.ForeignKey(
        WhatsAppTemplate, on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Template used (for outbound template messages).",
    )

    # Provider tracking
    provider = models.CharField(max_length=30, choices=WhatsAppProvider.CHOICES, default=WhatsAppProvider.INTERAKT)
    provider_message_id = models.CharField(max_length=200, blank=True, default="", db_index=True)

    # Status & timing
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued", db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True, default="")

    # Media attachment
    media_url = models.URLField(blank=True, default="")

    # Campaign reference (for bulk messages)
    campaign = models.ForeignKey(
        "BulkCampaign", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="whatsapp_messages",
    )

    class Meta:
        verbose_name = "WhatsApp Message"
        verbose_name_plural = "WhatsApp Messages"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["lead", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return (
            f"[WA {self.direction}] {self.lead.name} — "
            f"{self.content[:50]} [{self.status}]"
        )


# ============================================================
# Bulk Campaigns
# ============================================================

class BulkCampaign(TimeStampedUUIDModel):
    """
    A bulk communication campaign targeting multiple leads.
    Supports WhatsApp, Email, and SMS channels.
    """

    CHANNEL_CHOICES = [
        ("whatsapp", "WhatsApp"),
        ("email", "Email"),
        ("sms", "SMS"),
    ]
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("scheduled", "Scheduled"),
        ("running", "Running"),
        ("paused", "Paused"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    name = models.CharField(max_length=200)
    channel = models.CharField(max_length=15, choices=CHANNEL_CHOICES, db_index=True)
    created_by = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True,
        related_name="created_campaigns",
    )

    # Targeting
    # Lead IDs are resolved at send time from filters stored here
    audience_filters = models.JSONField(
        default=dict,
        help_text='Filter criteria: {"status": "interested", "city": "Mumbai"}',
    )
    estimated_recipients = models.PositiveIntegerField(default=0)

    # WhatsApp
    template = models.ForeignKey(
        WhatsAppTemplate, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="campaigns",
    )

    # Email
    email_subject = models.CharField(max_length=200, blank=True, default="")
    email_body = models.TextField(blank=True, default="")

    # SMS
    sms_text = models.CharField(max_length=160, blank=True, default="",
                                help_text="Max 160 chars for single SMS.")
    sms_sender_id = models.CharField(max_length=11, blank=True, default="",
                                     help_text="TRAI-approved 6-char sender ID.")

    # Scheduling
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft", db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Results (updated in real-time during send)
    total_recipients = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    delivered_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    replied_count = models.PositiveIntegerField(default=0)

    # Celery task
    celery_task_id = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        verbose_name = "Bulk Campaign"
        verbose_name_plural = "Bulk Campaigns"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.channel.upper()}] {self.name} [{self.get_status_display()}]"

    @property
    def delivery_rate(self) -> float:
        if not self.sent_count:
            return 0.0
        return round(self.delivered_count / self.sent_count * 100, 1)

    @property
    def progress_percent(self) -> int:
        if not self.total_recipients:
            return 0
        return int((self.sent_count + self.failed_count) / self.total_recipients * 100)


class CampaignRecipient(models.Model):
    """Per-lead row in a bulk campaign — tracks individual delivery status."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("failed", "Failed"),
        ("skipped", "Skipped (DND/Invalid)"),
    ]

    campaign = models.ForeignKey(BulkCampaign, on_delete=models.CASCADE, related_name="recipients")
    lead = models.ForeignKey("leads.Lead", on_delete=models.CASCADE, related_name="campaign_recipients")
    phone = models.CharField(max_length=15)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    error_message = models.CharField(max_length=500, blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        unique_together = ("campaign", "lead")
        verbose_name = "Campaign Recipient"
        indexes = [models.Index(fields=["campaign", "status"])]


# ============================================================
# Email & SMS Logs
# ============================================================

class EmailLog(TimeStampedModel):
    """Record of a single email sent from the CRM."""

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("opened", "Opened"),
        ("clicked", "Clicked"),
        ("bounced", "Bounced"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(
        "leads.Lead", on_delete=models.CASCADE, related_name="emails", null=True, blank=True
    )
    sent_by = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True
    )
    campaign = models.ForeignKey(
        BulkCampaign, on_delete=models.SET_NULL, null=True, blank=True, related_name="emails"
    )

    to_email = models.EmailField()
    subject = models.CharField(max_length=300)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued", db_index=True)
    provider = models.CharField(max_length=30, blank=True, default="",
                                 help_text="e.g. mailgun, sendgrid, ses")
    provider_message_id = models.CharField(max_length=200, blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        verbose_name = "Email Log"
        verbose_name_plural = "Email Logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Email to {self.to_email}: {self.subject[:50]} [{self.status}]"


class SMSLog(TimeStampedModel):
    """Record of a single SMS sent from the CRM."""

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("failed", "Failed"),
        ("dnd_blocked", "Blocked (DND)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(
        "leads.Lead", on_delete=models.CASCADE, related_name="sms_messages", null=True, blank=True
    )
    sent_by = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True
    )
    campaign = models.ForeignKey(
        BulkCampaign, on_delete=models.SET_NULL, null=True, blank=True, related_name="sms_messages"
    )

    phone_number = models.CharField(max_length=15)
    message = models.CharField(max_length=1600)   # 10x concatenated SMS
    sender_id = models.CharField(max_length=11, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued", db_index=True)
    provider = models.CharField(max_length=30, blank=True, default="",
                                 help_text="e.g. msg91, textlocal, fast2sms")
    provider_message_id = models.CharField(max_length=200, blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True, default="")
    cost_paise = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "SMS Log"
        verbose_name_plural = "SMS Logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"SMS to {self.phone_number}: {self.message[:40]} [{self.status}]"
