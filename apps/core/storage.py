"""
TeleCRM Backend — apps/core/storage.py

Custom Django storage backends for AWS S3.

Three storage classes:
  StaticStorage     → Public static files (CSS, JS, images) — public read
  MediaStorage      → General media files (profile photos) — public read
  PrivateMediaStorage → Call recordings, sensitive files — private, presigned URLs

Usage in models:
  call_recording = models.FileField(storage=PrivateMediaStorage(), ...)
  profile_photo = models.ImageField(storage=MediaStorage(), ...)
"""
import logging
import mimetypes
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage

logger = logging.getLogger(__name__)


def _is_s3_configured() -> bool:
    """Check if S3 is configured and enabled."""
    return getattr(settings, "USE_S3", False)


if _is_s3_configured():
    from storages.backends.s3boto3 import S3Boto3Storage

    class StaticStorage(S3Boto3Storage):
        """
        Storage for static files (CSS, JS, admin assets).
        Files are public and heavily cached via CloudFront.
        """

        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        location = "static"
        default_acl = "public-read"
        file_overwrite = True
        querystring_auth = False
        custom_domain = getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None)
        object_parameters = {
            "CacheControl": "max-age=86400, public",  # 24-hour CDN cache
        }

    class MediaStorage(S3Boto3Storage):
        """
        Storage for general media files (profile photos, logos).
        Files are public-read; URL returned directly.
        """

        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        location = "media"
        default_acl = "public-read"
        file_overwrite = False
        querystring_auth = False
        custom_domain = getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None)
        object_parameters = {
            "CacheControl": "max-age=3600",  # 1-hour CDN cache
        }

        def get_available_name(self, name, max_length=None):
            """
            Add tenant schema prefix to prevent filename collisions
            between tenants.
            """
            try:
                from django.db import connection
                schema = connection.schema_name
                if schema != "public":
                    # Inject tenant schema into path
                    dirname, filename = os.path.split(name)
                    name = os.path.join(dirname, schema, filename)
            except Exception:
                pass
            return super().get_available_name(name, max_length)

    class PrivateMediaStorage(S3Boto3Storage):
        """
        Storage for PRIVATE files:
        - Call recordings
        - Document attachments (sensitive)
        - CSV imports/exports

        Files are private; access requires pre-signed URLs with expiry.
        URLs are generated on-demand in views with short expiry.
        """

        bucket_name = getattr(
            settings, "AWS_PRIVATE_BUCKET_NAME", settings.AWS_STORAGE_BUCKET_NAME
        )
        location = "private"
        default_acl = "private"
        file_overwrite = False
        querystring_auth = True  # MUST be True for private files
        signature_version = "s3v4"
        custom_domain = None  # Don't use CDN for private files

        def url(self, name, parameters=None, expire=None, http_method=None):
            """Generate presigned URL with configurable expiry."""
            if expire is None:
                expire = getattr(settings, "AWS_QUERYSTRING_EXPIRE", 3600)
            return super().url(name, parameters=parameters, expire=expire)

        def get_tenant_path(self, name: str) -> str:
            """
            Prefix file path with tenant schema name for isolation.
            E.g., recordings/2024/01/call.mp3 → tenant_acme/recordings/2024/01/call.mp3
            """
            try:
                from django.db import connection
                schema = connection.schema_name
                if schema != "public":
                    return f"tenant_{schema}/{name}"
            except Exception:
                pass
            return name

        def _save(self, name, content):
            name = self.get_tenant_path(name)
            return super()._save(name, content)

    def generate_presigned_url(file_field, expiry_seconds: int = 3600) -> str:
        """
        Generate a pre-signed S3 URL for a private file.

        Usage:
            url = generate_presigned_url(call.recording_file, expiry_seconds=3600)
        """
        if not file_field or not file_field.name:
            return ""

        try:
            storage = file_field.storage
            return storage.url(file_field.name, expire=expiry_seconds)
        except Exception as exc:
            logger.error(f"Failed to generate presigned URL: {exc}")
            return ""

else:
    # ---- Non-S3 fallback (local file system) ----------------
    # Used in development and testing

    class StaticStorage(FileSystemStorage):
        """Local static file storage for development."""
        pass

    class MediaStorage(FileSystemStorage):
        """Local media storage for development."""
        pass

    class PrivateMediaStorage(FileSystemStorage):
        """Local storage for private files in development."""

        def url(self, name):
            """In development, serve private files via Django (not presigned)."""
            return super().url(name)

    def generate_presigned_url(file_field, expiry_seconds: int = 3600) -> str:
        """In development, return the regular file URL."""
        if not file_field or not file_field.name:
            return ""
        try:
            return file_field.url
        except Exception:
            return ""


# ============================================================
# File Upload Utilities
# ============================================================

def get_call_recording_upload_path(instance, filename: str) -> str:
    """
    Upload path for call recordings.
    Structure: recordings/{year}/{month}/{agent_id}/{filename}
    """
    from django.utils import timezone
    now = timezone.now()
    agent_id = getattr(instance, "agent_id", "unknown")
    _, ext = os.path.splitext(filename)
    return f"recordings/{now.year}/{now.month:02d}/{agent_id}/{now.strftime('%Y%m%d_%H%M%S')}{ext}"


def get_profile_photo_upload_path(instance, filename: str) -> str:
    """Upload path for agent profile photos."""
    _, ext = os.path.splitext(filename)
    agent_id = getattr(instance, "pk", "new")
    return f"profiles/{agent_id}/photo{ext}"


def get_import_file_upload_path(instance, filename: str) -> str:
    """Upload path for CSV/Excel import files."""
    from django.utils import timezone
    now = timezone.now()
    return f"imports/{now.year}/{now.month:02d}/{filename}"



def get_presigned_url(key: str, expiry_seconds: int = 3600) -> str:
    """
    Generate a time-limited presigned URL for an S3 object.
    Falls back to returning the key unchanged in local dev.

    Args:
        key: S3 object key or local file path
        expiry_seconds: URL validity window (default 1 hour)

    Returns:
        Presigned URL string
    """
    if not _is_s3_configured():
        # Local dev — return path as-is (served by Django dev server)
        from django.conf import settings
        return f"{settings.MEDIA_URL}{key}"

    try:
        import boto3
        from django.conf import settings
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, "AWS_S3_REGION_NAME", "ap-south-1"),
        )
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": key},
            ExpiresIn=expiry_seconds,
        )
        return url
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f"[S3] Presigned URL failed for {key}: {exc}")
        return ""

def validate_file_size(file, max_size_bytes: int):
    """
    Validate file size against a maximum.
    Raises ValueError if file is too large.
    """
    if file.size > max_size_bytes:
        max_mb = max_size_bytes / (1024 * 1024)
        actual_mb = file.size / (1024 * 1024)
        raise ValueError(
            f"File size {actual_mb:.1f}MB exceeds maximum allowed {max_mb:.0f}MB."
        )


def validate_file_type(file, allowed_types: list):
    """
    Validate file MIME type.
    allowed_types: list of MIME types e.g. ['audio/mp4', 'audio/mpeg']
    """
    mime_type, _ = mimetypes.guess_type(file.name)
    if mime_type not in allowed_types:
        raise ValueError(
            f"File type '{mime_type}' is not allowed. "
            f"Allowed types: {', '.join(allowed_types)}"
        )
