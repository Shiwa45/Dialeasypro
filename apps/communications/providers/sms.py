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

    # The JSON body below is MSG91's v2 sendsms shape. It was previously
    # POSTed to sendhttp.php — the LEGACY query-string endpoint, which ignores
    # a JSON body — so a send either failed or silently delivered nothing while
    # still returning 200 and a body we stored as a message id.
    BASE_URL = "https://api.msg91.com/api/v2/sendsms"

    def __init__(self):
        self.auth_key = getattr(settings, "MSG91_AUTH_KEY", "")
        self.default_sender = getattr(settings, "MSG91_SENDER_ID", "TELECRM")
        if not self.auth_key:
            raise ValueError("MSG91_AUTH_KEY is not configured")

    def send(self, phone: str, message: str, sender_id: str = "") -> str:
        payload = {
            "sender": sender_id or self.default_sender,
            "route": "4",  # Transactional route
            "country": "91",
            "sms": [{"message": message, "to": [self._clean_phone(phone)]}],
        }
        response = requests.post(
            self.BASE_URL,
            json=payload,
            headers={"authkey": self.auth_key, "Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()

        # MSG91 answers 200 with {"type": "error", "message": "..."} for things
        # like a bad sender id. Raising here is what stops a rejected message
        # being recorded as sent.
        try:
            data = response.json()
        except ValueError:
            return response.text.strip()

        if isinstance(data, dict):
            if data.get("type") == "error":
                raise RuntimeError(f"MSG91 rejected the message: {data.get('message')}")
            return str(data.get("message") or data.get("request_id") or "")
        return response.text.strip()


class MockSMSProvider(SMSProviderBase):
    """Development mock — logs instead of sending."""

    def send(self, phone: str, message: str, sender_id: str = "") -> str:
        logger.info(f"[Mock SMS] [{sender_id}] → {phone}: {message[:80]}")
        import uuid
        return f"mock_sms_{uuid.uuid4().hex[:8]}"
