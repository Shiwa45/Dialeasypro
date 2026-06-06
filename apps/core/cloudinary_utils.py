"""
TeleCRM Backend — apps/core/cloudinary_utils.py

Thin wrapper around the Cloudinary SDK for uploading call-recording audio.

Audio files are uploaded as Cloudinary "video" resource_type (Cloudinary stores
and serves audio under the video pipeline). Uploads are scoped per-tenant via a
folder prefix so recordings never collide across tenants.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _configure():
    """Configure the Cloudinary SDK from settings. Returns the module or None."""
    if not getattr(settings, "CLOUDINARY_CONFIGURED", False):
        return None
    try:
        import cloudinary
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )
        return cloudinary
    except Exception as exc:  # pragma: no cover - misconfiguration guard
        logger.error(f"[Cloudinary] Configuration failed: {exc}")
        return None


def upload_call_recording(file_obj, *, tenant_schema: str, public_id: str) -> dict | None:
    """
    Upload an audio file to Cloudinary and return its metadata.

    Args:
        file_obj:       A Django UploadedFile / file-like object.
        tenant_schema:  Current tenant schema name (used as the folder prefix
                        for isolation).
        public_id:      Deterministic id for the recording (e.g. "call_<uuid>"),
                        so re-uploading the same call overwrites rather than
                        duplicates.

    Returns:
        dict with keys: url, public_id, bytes, duration, format
        or None if Cloudinary is not configured / the upload failed.
    """
    cloudinary = _configure()
    if cloudinary is None:
        logger.warning("[Cloudinary] Not configured — skipping upload.")
        return None

    folder = f"{settings.CLOUDINARY_RECORDINGS_FOLDER}/{tenant_schema}"
    try:
        import cloudinary.uploader

        result = cloudinary.uploader.upload(
            file_obj,
            resource_type="video",  # audio is handled by the video pipeline
            folder=folder,
            public_id=public_id,
            overwrite=True,
            unique_filename=False,
            use_filename=False,
        )
        return {
            "url": result.get("secure_url"),
            "public_id": result.get("public_id"),
            "bytes": result.get("bytes", 0),
            "duration": int(result.get("duration") or 0),
            "format": result.get("format", ""),
        }
    except Exception as exc:
        logger.error(f"[Cloudinary] Upload failed for {public_id}: {exc}")
        return None


def upload_image(file_obj, *, tenant_schema: str, folder: str = "template_media") -> dict | None:
    """
    Upload an image (e.g. a WhatsApp template header banner) to Cloudinary.
    Returns {url, public_id, bytes, format} or None if not configured/failed.
    """
    cloudinary = _configure()
    if cloudinary is None:
        logger.warning("[Cloudinary] Not configured — skipping image upload.")
        return None
    try:
        import cloudinary.uploader
        result = cloudinary.uploader.upload(
            file_obj,
            resource_type="image",
            folder=f"{folder}/{tenant_schema}",
        )
        return {
            "url": result.get("secure_url"),
            "public_id": result.get("public_id"),
            "bytes": result.get("bytes", 0),
            "format": result.get("format", ""),
        }
    except Exception as exc:
        logger.error(f"[Cloudinary] Image upload failed: {exc}")
        return None


def delete_call_recording(public_id: str) -> bool:
    """Delete a recording from Cloudinary (used when a call/recording is purged)."""
    cloudinary = _configure()
    if cloudinary is None:
        return False
    try:
        import cloudinary.uploader
        cloudinary.uploader.destroy(public_id, resource_type="video")
        return True
    except Exception as exc:
        logger.warning(f"[Cloudinary] Delete failed for {public_id}: {exc}")
        return False
