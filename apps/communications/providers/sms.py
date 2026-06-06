"""
TeleCRM Backend — apps/communications/providers/sms.py

SMS provider implementations.
All must implement: send(phone, message, sender_id) → provider_message_id

Supported: MSG91, TextLocal, Fast2SMS, MockSMSProvider
"""
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SMSProviderBase:
    def send(self, phone: str, message: str, sender_id: str = "") -> str:
        raise NotImplementedError

    def _clean_phone(self, phone: str) -> str:
        return phone.replace("+91", "").replace(" ", "")


class MSG91Provider(SMSProviderBase):
    """
    MSG91 SMS API — popular enterprise SMS provider in India.
    Docs: https://docs.msg91.com/
    Configure: MSG91_AUTH_KEY, MSG91_SENDER_ID
    """

    BASE_URL = "https://api.msg91.com/api/v5/flow/"

    def __init__(self):
        self.auth_key = getattr(settings, "MSG91_AUTH_KEY", "")
        self.default_sender = getattr(settings, "MSG91_SENDER_ID", "TELECRM")

    def send(self, phone: str, message: str, sender_id: str = "") -> str:
        payload = {
            "sender": sender_id or self.default_sender,
            "route": "4",  # Transactional route
            "country": "91",
            "sms": [{"message": message, "to": [self._clean_phone(phone)]}],
        }
        response = requests.post(
            "https://api.msg91.com/api/sendhttp.php",
            json=payload,
            headers={"authkey": self.auth_key, "Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        return response.text.strip()


class MockSMSProvider(SMSProviderBase):
    """Development mock — logs instead of sending."""

    def send(self, phone: str, message: str, sender_id: str = "") -> str:
        logger.info(f"[Mock SMS] [{sender_id}] → {phone}: {message[:80]}")
        import uuid
        return f"mock_sms_{uuid.uuid4().hex[:8]}"
