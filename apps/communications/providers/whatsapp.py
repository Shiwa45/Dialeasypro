"""
TeleCRM Backend — apps/communications/providers/whatsapp.py

WhatsApp provider implementations.
Each provider class implements the same interface:
  send_template(phone, template_id, variables) → provider_message_id
  send_text(phone, message) → provider_message_id

Supported providers:
  Interakt   — Most popular in India; BSP partner
  AiSensy    — Budget-friendly Indian BSP
  Wati       — Popular with SMBs
  Gupshup    — Enterprise-grade
  MockWhatsAppProvider — For development/testing
"""
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class WhatsAppProviderBase:
    """Abstract base for WhatsApp provider implementations."""

    def send_template(self, phone: str, template_id: str, variables: list) -> str:
        raise NotImplementedError

    def send_text(self, phone: str, message: str) -> str:
        raise NotImplementedError

    def _strip_country_code(self, phone: str) -> str:
        """Remove +91 for providers that expect 10-digit numbers."""
        return phone.replace("+91", "").replace(" ", "")

    def _with_country_code(self, phone: str) -> str:
        """Ensure +91 prefix."""
        phone = phone.replace("+91", "").replace(" ", "")
        return f"91{phone}"   # Some APIs want 91XXXXXXXXXX


class InteraktProvider(WhatsAppProviderBase):
    """
    Interakt WhatsApp API.
    Docs: https://developers.interakt.ai/reference
    Configure in settings: INTERAKT_API_KEY
    """

    BASE_URL = "https://api.interakt.ai/v1/public/message/"

    def __init__(self):
        self.api_key = getattr(settings, "INTERAKT_API_KEY", "")
        if not self.api_key:
            raise ValueError("INTERAKT_API_KEY not configured in settings")

    def send_template(self, phone: str, template_id: str, variables: list) -> str:
        payload = {
            "countryCode": "+91",
            "phoneNumber": self._strip_country_code(phone),
            "callbackData": "telecrm",
            "type": "Template",
            "template": {
                "name": template_id,
                "languageCode": "en",
                "bodyValues": variables,
            },
        }
        response = requests.post(
            self.BASE_URL,
            json=payload,
            headers={"Authorization": f"Basic {self.api_key}", "Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("id", "")

    def send_text(self, phone: str, message: str) -> str:
        payload = {
            "countryCode": "+91",
            "phoneNumber": self._strip_country_code(phone),
            "callbackData": "telecrm",
            "type": "Text",
            "data": {"message": message},
        }
        response = requests.post(
            self.BASE_URL,
            json=payload,
            headers={"Authorization": f"Basic {self.api_key}", "Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("id", "")


class MockWhatsAppProvider(WhatsAppProviderBase):
    """Mock provider for development and testing. Logs instead of sending."""

    def send_template(self, phone: str, template_id: str, variables: list) -> str:
        logger.info(f"[Mock WA] Template {template_id} → {phone} | vars={variables}")
        import uuid
        return f"mock_{uuid.uuid4().hex[:8]}"

    def send_text(self, phone: str, message: str) -> str:
        logger.info(f"[Mock WA] Text → {phone}: {message[:80]}")
        import uuid
        return f"mock_{uuid.uuid4().hex[:8]}"
