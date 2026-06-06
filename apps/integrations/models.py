"""
TeleCRM Backend — apps/integrations/models.py

Per-tenant integration configuration and webhook routing.

LeadSourceConfig  : Stores API keys and settings for each lead source integration.
WebhookLog        : Logs every inbound webhook payload for debugging.
IntegrationEvent  : Processed integration events (lead created from IndiaMART, etc.)

Indian lead sources:
  - IndiaMART         → /api/v1/integrations/indiamart/
  - Meta Lead Ads     → /api/v1/integrations/meta/
  - Google Ads        → /api/v1/integrations/google/
  - 99acres, Housing  → /api/v1/integrations/portal/{slug}/
  - Generic Webhook   → /api/v1/integrations/webhook/{token}/
"""
import uuid
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel, TimeStampedUUIDModel
from apps.core.constants import LeadSource


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
