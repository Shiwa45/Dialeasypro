"""
TeleCRM Backend — apps/core/models.py

Abstract base models inherited by all TeleCRM models.
These are in the core app (SHARED_APPS) and have no migrations themselves —
they're abstract and their fields are included in the child models' migrations.
"""
import uuid

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """
    Abstract base class adding created_at and updated_at fields.
    All TeleCRM models inherit from this.
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # Ensure updated_at is always timezone-aware
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)


class UUIDModel(models.Model):
    """
    Abstract base class using UUID as primary key.
    Use for models where sequential IDs would expose business metrics.
    (E.g., lead count = ID of last lead)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedUUIDModel(UUIDModel, TimeStampedModel):
    """Combines UUID primary key + timestamps."""

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class SoftDeleteModel(models.Model):
    """
    Abstract base class for soft-delete functionality.
    Records are marked as deleted instead of physically removed.
    Provides is_deleted + deleted_at fields.

    Usage:
        MyModel.objects.active()     → non-deleted records
        MyModel.objects.all()        → includes deleted (use sparingly)
        instance.soft_delete()       → marks as deleted
        instance.restore()           → un-deletes
    """
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by_id = models.BigIntegerField(null=True, blank=True)  # Agent ID

    class Meta:
        abstract = True

    def soft_delete(self, deleted_by=None):
        """Soft-delete this record."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        if deleted_by:
            self.deleted_by_id = deleted_by.pk
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by_id"])

    def restore(self):
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by_id = None
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by_id"])


class ActiveManager(models.Manager):
    """Default manager that excludes soft-deleted records."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def active(self):
        return self.get_queryset()

    def deleted(self):
        return super().get_queryset().filter(is_deleted=True)


class SortableModel(models.Model):
    """
    Abstract base class for models that need manual ordering.
    Adds a sort_order field.
    """
    sort_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        abstract = True
        ordering = ["sort_order"]
