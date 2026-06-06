"""
TeleCRM Backend — apps/superadmin/models.py

Models for the super admin layer (public schema).

AuditLog      → Immutable record of all significant actions across the platform
GlobalSettings → Key-value store for platform-wide settings
SupportNote   → Internal notes on tenants (visible only to super admins)
"""
import uuid

from django.db import models
from django.utils import timezone

from apps.core.constants import AuditAction
from apps.core.models import TimeStampedModel


class AuditLog(models.Model):
    """
    Immutable audit trail for all significant platform actions.
    Never update or delete these records.

    Covers:
    - Super admin actions (tenant CRUD, plan changes)
    - Tenant admin actions (agent CRUD, settings changes)
    - System actions (trial expiry, subscription events)
    - Security events (login, failed login, password reset)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ---- Who did it ----------------------------------------
    actor_type = models.CharField(
        max_length=20,
        choices=[
            ("super_admin", "Super Admin"),
            ("tenant_admin", "Tenant Admin"),
            ("agent", "Agent"),
            ("system", "System (Celery)"),
            ("api", "API"),
        ],
        default="system",
    )
    actor_id = models.CharField(
        max_length=100, blank=True, default="",
        help_text="PK of the actor (user ID, agent ID, etc.)",
    )
    actor_email = models.EmailField(blank=True, default="")
    actor_ip = models.GenericIPAddressField(null=True, blank=True)
    actor_user_agent = models.CharField(max_length=500, blank=True, default="")

    # ---- Where it happened ---------------------------------
    tenant_schema = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Schema name if action was in a tenant context. Empty for public.",
    )

    # ---- What happened -------------------------------------
    action = models.CharField(
        max_length=50, choices=AuditAction.CHOICES, db_index=True
    )
    entity_type = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Model name: 'Tenant', 'Agent', 'Lead', etc.",
    )
    entity_id = models.CharField(max_length=100, blank=True, default="")
    entity_repr = models.CharField(
        max_length=300, blank=True, default="",
        help_text="Human-readable description of the affected entity.",
    )
    changes = models.JSONField(
        default=dict, blank=True,
        help_text="Dict with 'before' and 'after' states for update actions.",
    )
    description = models.TextField(
        blank=True, default="",
        help_text="Free-text description of what happened.",
    )

    # ---- Metadata -----------------------------------------
    is_sensitive = models.BooleanField(
        default=False,
        help_text="If True, this log entry involves sensitive data (e.g., passwords).",
    )
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["tenant_schema", "timestamp"]),
            models.Index(fields=["actor_email", "timestamp"]),
            models.Index(fields=["action", "timestamp"]),
        ]

    def __str__(self):
        return (
            f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] "
            f"{self.actor_email or 'system'} — {self.action} — {self.entity_repr}"
        )

    @classmethod
    def log(
        cls,
        action: str,
        actor_type: str = "system",
        actor_id: str = "",
        actor_email: str = "",
        tenant_schema: str = "",
        entity_type: str = "",
        entity_id: str = "",
        entity_repr: str = "",
        changes: dict = None,
        description: str = "",
        request=None,
        is_sensitive: bool = False,
    ):
        """
        Convenience class method to create audit log entries.

        Usage:
            AuditLog.log(
                action=AuditAction.LOGIN,
                actor_type="agent",
                actor_email="agent@acme.com",
                tenant_schema="acme_realty",
                entity_type="Agent",
                entity_repr="Riya Singh",
            )
        """
        ip = None
        user_agent = ""

        if request:
            ip = cls._get_client_ip(request)
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
            if not actor_email and hasattr(request, "user") and request.user:
                actor_email = getattr(request.user, "email", "")
            if not tenant_schema and hasattr(request, "tenant"):
                tenant_schema = getattr(request.tenant, "schema_name", "")

        cls.objects.create(
            action=action,
            actor_type=actor_type,
            actor_id=str(actor_id),
            actor_email=actor_email,
            actor_ip=ip,
            actor_user_agent=user_agent,
            tenant_schema=tenant_schema,
            entity_type=entity_type,
            entity_id=str(entity_id),
            entity_repr=entity_repr,
            changes=changes or {},
            description=description,
            is_sensitive=is_sensitive,
        )

    @staticmethod
    def _get_client_ip(request) -> str:
        """Extract real client IP from request headers."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")


class GlobalSettings(TimeStampedModel):
    """
    Platform-wide key-value settings managed by super admins.
    Cached in Redis for fast access.

    Examples:
        key="maintenance_mode",     value="false"
        key="default_trial_days",   value="14"
        key="platform_name",        value="TeleCRM"
    """

    key = models.CharField(max_length=100, unique=True, db_index=True)
    value = models.TextField()
    description = models.CharField(max_length=500, blank=True, default="")
    updated_by = models.EmailField(blank=True, default="")

    class Meta:
        verbose_name = "Global Setting"
        verbose_name_plural = "Global Settings"
        ordering = ["key"]

    def __str__(self):
        return f"{self.key}: {self.value[:50]}"

    @classmethod
    def get(cls, key: str, default=None):
        """Get a setting value by key."""
        from django.core.cache import cache

        cache_key = f"global_setting:{key}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            obj = cls.objects.get(key=key)
            cache.set(cache_key, obj.value, timeout=300)
            return obj.value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set(cls, key: str, value: str, updated_by: str = ""):
        """Set a setting value."""
        from django.core.cache import cache

        obj, _ = cls.objects.update_or_create(
            key=key,
            defaults={"value": str(value), "updated_by": updated_by},
        )
        cache.delete(f"global_setting:{key}")
        return obj


class SupportNote(TimeStampedModel):
    """
    Internal notes that super admins write about a tenant.
    Visible only in the super admin panel — NOT to the tenant.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="support_notes",
    )
    note = models.TextField()
    created_by = models.EmailField(help_text="Super admin who wrote this note.")
    is_pinned = models.BooleanField(
        default=False, help_text="Pin important notes to the top."
    )

    class Meta:
        verbose_name = "Support Note"
        verbose_name_plural = "Support Notes"
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return f"Note on {self.tenant.company_name} by {self.created_by}"
