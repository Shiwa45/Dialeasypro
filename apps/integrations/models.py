"""
TeleCRM Backend — apps/integrations/models.py

Per-tenant integration configuration and webhook routing.

LeadSourceConfig  : Stores API keys and settings for each lead source integration.
WebhookLog        : Logs every inbound webhook payload for debugging.
IntegrationEvent  : Processed integration events (lead created from IndiaMART, etc.)

MetaWhatsAppEvent : Idempotency ledger for Meta WhatsApp webhook deliveries.

Indian lead sources:
  - IndiaMART         → /api/v1/integrations/indiamart/
  - Meta Lead Ads     → /api/v1/integrations/meta/
  - Meta Click-to-WA  → /api/v1/integrations/meta/whatsapp/
  - Google Ads        → /api/v1/integrations/google/
  - 99acres, Housing  → /api/v1/integrations/portal/{slug}/
  - Generic Webhook   → /api/v1/integrations/webhook/{token}/
"""
import uuid
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel, TimeStampedUUIDModel
from apps.core.constants import LeadSource
from apps.core.crypto import EncryptedJSONField


class LeadSourceConfig(TimeStampedModel):
    """
    Per-tenant configuration for a lead source integration.
    Stores provider-specific credentials and options.
    """

    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("error", "Error — check credentials"),
    ]

    source = models.CharField(
        max_length=50,
        choices=LeadSource.CHOICES,
        unique=True,   # One config per source per tenant schema
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    # Encrypted credentials (store encrypted in production via django-environ / KMS)
    # Stored as JSON: {"api_key": "...", "account_id": "...", etc.}
    credentials = models.JSONField(default=dict, blank=True)

    # Per-source options
    options = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Source-specific options: auto_assign_to agent_id, "
            "default_priority, duplicate_action, etc."
        ),
    )

    # Webhook token (for generic webhook and portal integrations)
    webhook_token = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        help_text="Auto-generated token for the inbound webhook URL.",
    )

    # Stats
    total_leads_received = models.PositiveIntegerField(default=0)
    last_received_at = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        verbose_name = "Lead Source Config"
        verbose_name_plural = "Lead Source Configs"
        ordering = ["source"]

    def __str__(self):
        return f"{self.get_source_display()} — {'Active' if self.is_active else 'Inactive'}"

    def save(self, *args, **kwargs):
        if not self.webhook_token:
            import secrets
            self.webhook_token = secrets.token_urlsafe(32)

        # Keep `status` in step with the switch. It is what the UI and the API
        # read, and it used to sit at "active" on an integration that had been
        # switched off — the one thing an admin checks to confirm the change
        # took. "error" is left alone: a broken integration that is also off
        # should still say what is broken about it.
        if not self.is_active and self.status == "active":
            self.status = "inactive"
        elif self.is_active and self.status == "inactive":
            self.status = "active"
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"status"}

        super().save(*args, **kwargs)

    @property
    def webhook_url(self) -> str:
        from django.conf import settings
        source_slug = self.source.replace("_", "-")
        return f"https://{{tenant}}.{settings.BASE_DOMAIN}/api/v1/integrations/webhook/{self.webhook_token}/"


class WebhookLog(TimeStampedModel):
    """
    Log of every inbound webhook payload for debugging and replay.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=50, choices=LeadSource.CHOICES, db_index=True)
    config = models.ForeignKey(
        LeadSourceConfig, on_delete=models.SET_NULL, null=True, related_name="webhook_logs"
    )
    method = models.CharField(max_length=10, default="POST")
    headers = models.JSONField(default=dict, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    # Processing result
    processed = models.BooleanField(default=False, db_index=True)
    leads_created = models.PositiveSmallIntegerField(default=0)
    leads_updated = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        verbose_name = "Webhook Log"
        verbose_name_plural = "Webhook Logs"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["source", "processed", "created_at"])]

    def __str__(self):
        status = "✅" if self.processed else "⏳" if not self.error else "❌"
        return f"{status} {self.get_source_display()} webhook at {self.created_at:%d %b %H:%M}"


class MetaWhatsAppEvent(TimeStampedModel):
    """
    One row per Meta WhatsApp webhook event we have already acted on.

    Meta retries a delivery until it gets a 200, and will happily re-send an
    event it already delivered — so "the same message must never create a
    second lead" has to be guaranteed by the database, not by hoping the
    handler runs once. `dedupe_key` is that guarantee: processing claims the
    key inside the transaction that does the CRM work, so a concurrent retry
    either loses the insert race or sees a claimed key, and in both cases does
    nothing.

    The key is scoped per event, not per message: a message id and each of its
    subsequent delivery statuses (sent/delivered/read) are distinct events on
    the same wamid, so the key carries the event kind too.
    """

    STATUS_PENDING = "pending"
    STATUS_PROCESSED = "processed"
    STATUS_IGNORED = "ignored"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSED, "Processed"),
        (STATUS_IGNORED, "Ignored (unsupported event)"),
        (STATUS_FAILED, "Failed"),
    ]

    KIND_MESSAGE = "message"
    KIND_STATUS = "status"
    KIND_CHOICES = [(KIND_MESSAGE, "Inbound message"), (KIND_STATUS, "Delivery status")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dedupe_key = models.CharField(
        max_length=255, unique=True,
        help_text="Stable per-event key, e.g. 'msg:wamid.ABC' or 'status:wamid.ABC:read'.",
    )
    message_id = models.CharField(
        max_length=200, db_index=True, blank=True, default="",
        help_text="Meta's wamid for the message this event concerns.",
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_MESSAGE)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True,
    )

    # What the event produced, for support ("where did this lead come from?").
    lead = models.ForeignKey(
        "leads.Lead", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="meta_whatsapp_events",
    )
    conversation_id = models.UUIDField(null=True, blank=True)
    created_lead = models.BooleanField(default=False)
    webhook_log = models.ForeignKey(
        WebhookLog, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="whatsapp_events",
    )
    error = models.CharField(max_length=500, blank=True, default="")
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Meta WhatsApp Event"
        verbose_name_plural = "Meta WhatsApp Events"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return f"{self.kind}:{self.message_id} [{self.status}]"

    def mark(self, status: str, *, error: str = ""):
        self.status = status
        self.error = error[:500]
        self.processed_at = timezone.now()
        self.save(update_fields=["status", "error", "processed_at", "updated_at"])


# ============================================================
# Meta Lead Ads — "Continue with Facebook"
# ============================================================
# The tenant signs in with Facebook once, picks Pages and forms, and leads
# arrive on the platform's one Meta app webhook (routed here by Page id; see
# tenants.MetaPageRoute). Nobody creates a Meta app or copies a token.
#
# The older manual set-up (a Page token typed into LeadSourceConfig) keeps
# working alongside; both feed the same lead-creation code.

class MetaConnection(TimeStampedModel):
    """
    The Facebook sign-in that granted access, newest wins.

    Kept for the long-lived user token, which lists the person's Pages when
    they come back to connect another one. The Page tokens derived from it
    live on MetaLeadPage and do not expire.
    """

    fb_user_id = models.CharField(max_length=40, blank=True, default="")
    fb_user_name = models.CharField(max_length=200, blank=True, default="")
    secrets = EncryptedJSONField(default=dict, blank=True)  # {"user_token": "..."}
    token_expires_at = models.DateTimeField(null=True, blank=True)
    granted_scopes = models.JSONField(default=list, blank=True)
    connected_by = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def latest(cls):
        return cls.objects.order_by("-created_at", "-id").first()


class MetaLeadPage(TimeStampedModel):
    """A Facebook Page the tenant can receive Lead Ads from."""

    page_id = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=200, blank=True, default="")
    picture_url = models.URLField(max_length=1000, blank=True, default="")
    secrets = EncryptedJSONField(default=dict, blank=True)  # {"page_token": "..."}

    # Listed (the person can manage it) vs connected (subscribed, leads flow).
    connected = models.BooleanField(default=False, db_index=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    connected_by = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    auto_add_new_forms = models.BooleanField(
        default=True,
        help_text="A form created later on this Page starts receiving leads without a visit here.",
    )

    leads_received = models.PositiveIntegerField(default=0)
    last_lead_at = models.DateTimeField(null=True, blank=True)
    last_polled_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name or self.page_id} ({'connected' if self.connected else 'available'})"

    @property
    def token(self) -> str:
        return (self.secrets or {}).get("page_token", "")


class MetaLeadForm(TimeStampedModel):
    """One Lead Ads form on a connected Page, and where its leads go."""

    ASSIGN_DEFAULT = "default"
    ASSIGN_AGENT = "agent"
    ASSIGN_TEAM = "team"
    ASSIGN_CHOICES = [
        (ASSIGN_DEFAULT, "Your usual rules"),
        (ASSIGN_AGENT, "One agent"),
        (ASSIGN_TEAM, "A team, in turn"),
    ]

    page = models.ForeignKey(MetaLeadPage, on_delete=models.CASCADE, related_name="forms")
    form_id = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=300, blank=True, default="")
    status = models.CharField(max_length=20, blank=True, default="")  # ACTIVE / ARCHIVED / ...
    enabled = models.BooleanField(default=True, help_text="Take leads from this form.")

    assign_mode = models.CharField(max_length=10, choices=ASSIGN_CHOICES, default=ASSIGN_DEFAULT)
    assign_agent = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    assign_team = models.ForeignKey(
        "authentication.Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    # Round robin position within the team (index of the last agent given one).
    rr_cursor = models.IntegerField(default=-1)

    leads_received = models.PositiveIntegerField(default=0)
    last_lead_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["page__name", "name"]

    def __str__(self):
        return self.name or self.form_id
