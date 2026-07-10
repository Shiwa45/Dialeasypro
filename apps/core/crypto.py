"""
TeleCRM Backend — apps/core/crypto.py

Transparent at-rest encryption for sensitive model fields (WhatsApp API keys,
provider tokens). Values are encrypted going into the database and decrypted
coming out, so a database dump or read replica never exposes a tenant's
credentials in the clear.

Key resolution:
  FIELD_ENCRYPTION_KEY   a urlsafe-base64 Fernet key — set this in production
                         and rotate it deliberately.
  (fallback) SECRET_KEY  derived to a Fernet key so dev/staging work with no
                         extra config. Rotating SECRET_KEY then makes existing
                         ciphertext unreadable — set FIELD_ENCRYPTION_KEY to
                         decouple the two before you rely on this in anger.
"""
import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet() -> Fernet:
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    if key:
        return Fernet(key.encode() if isinstance(key, str) else key)
    # Derive a stable 32-byte key from SECRET_KEY for environments that haven't
    # set a dedicated one.
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(text: str) -> str:
    if not text:
        return ""
    return _fernet().encrypt(text.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        # Wrong/rotated key, or the column held plaintext from before this field
        # was encrypted. Returning "" is safer than raising in the send path —
        # the provider call fails cleanly and the admin re-enters the secret.
        return ""


class EncryptedJSONField(models.TextField):
    """
    A dict stored as an encrypted blob.

    Behaves like a JSONField to Python code (get/set a dict) but is opaque
    ciphertext in the database. Use for a bag of provider credentials —
    `{"api_key": "...", "token": "..."}` — so no individual secret is queryable
    or visible in a dump.
    """

    description = "Encrypted JSON blob"

    def get_prep_value(self, value):
        if value in (None, ""):
            return ""
        return encrypt(json.dumps(value, separators=(",", ":"), sort_keys=True))

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        if isinstance(value, dict):
            return value
        if value in (None, ""):
            return {}
        raw = decrypt(value)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {}
