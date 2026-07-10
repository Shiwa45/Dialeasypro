"""
TeleCRM Backend — apps/communications/providers/whatsapp.py

WhatsApp provider implementations.

Every provider is constructed from a *tenant's* credentials (a dict off their
WhatsAppConfig), not from global settings — this is multi-tenant, so each
tenant sends through their own WhatsApp Business account. All implement the
same two-method interface:

  send_template(phone, template_id, variables) → provider_message_id
  send_text(phone, message)                    → provider_message_id

Credential shapes, by provider:
  meta_cloud : {"access_token", "phone_number_id"[, "business_account_id"]}
  interakt   : {"api_key"}
  aisensy    : {"api_key"}
  wati       : {"access_token", "api_endpoint"}   # api_endpoint e.g. https://live-server-12345.wati.io
  gupshup    : {"api_key", "app_name", "source_number"}

`build_provider(config)` picks the class from `config.provider` and hands it
`config.credentials`. A tenant with no active config (or one that raises on
missing credentials) gets the Mock provider, which logs and no-ops rather than
sending — so a half-configured tenant fails safe instead of silently blasting
a wrong number.
"""
import logging
import uuid

import requests

logger = logging.getLogger(__name__)

TIMEOUT = 15


class WhatsAppError(Exception):
    """A send failed. Carries the provider's own message where we could read it."""


class WhatsAppProviderBase:
    """Abstract base. Subclasses read what they need from `credentials`."""

    #: keys that must be present and non-empty in `credentials`
    required = ()

    def __init__(self, credentials: dict | None = None):
        self.credentials = credentials or {}
        missing = [k for k in self.required if not self.credentials.get(k)]
        if missing:
            raise WhatsAppError(
                f"{self.__class__.__name__} is missing credential(s): {', '.join(missing)}"
            )

    def send_template(self, phone: str, template_id: str, variables: list) -> str:
        raise NotImplementedError

    def send_text(self, phone: str, message: str) -> str:
        raise NotImplementedError

    # ---- phone helpers -------------------------------------
    @staticmethod
    def _digits(phone: str) -> str:
        """Bare digits, no +, no spaces (e.g. 919876543210)."""
        return "".join(ch for ch in phone if ch.isdigit())

    def _local(self, phone: str) -> str:
        """10-digit local number, country code stripped."""
        d = self._digits(phone)
        return d[-10:] if len(d) >= 10 else d

    def _e164_no_plus(self, phone: str) -> str:
        """Country-coded, no plus (91XXXXXXXXXX). Assumes India when bare."""
        d = self._digits(phone)
        if len(d) == 10:
            return f"91{d}"
        return d

    # ---- HTTP helper ---------------------------------------
    def _post(self, url: str, *, headers=None, json=None, data=None) -> dict:
        try:
            resp = requests.post(url, headers=headers, json=json, data=data, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise WhatsAppError(f"Network error talking to WhatsApp provider: {exc}") from exc
        if resp.status_code >= 400:
            raise WhatsAppError(
                f"{self.__class__.__name__} HTTP {resp.status_code}: {resp.text[:300]}"
            )
        try:
            return resp.json()
        except ValueError:
            return {}


# ============================================================
# Meta WhatsApp Cloud API (direct, no BSP)
# ============================================================
class MetaCloudProvider(WhatsAppProviderBase):
    """
    WhatsApp Cloud API straight from Meta — https://developers.facebook.com/docs/whatsapp/cloud-api

    Cheapest per-message and the most future-proof, since there's no reseller
    in the path. A free-form `send_text` only reaches users inside the 24-hour
    customer-service window; outside it, Meta rejects anything but a template —
    that rejection surfaces here as a WhatsAppError with Meta's own reason.
    """

    required = ("access_token", "phone_number_id")
    API_VERSION = "v21.0"

    def _url(self) -> str:
        pnid = self.credentials["phone_number_id"]
        return f"https://graph.facebook.com/{self.API_VERSION}/{pnid}/messages"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.credentials['access_token']}",
            "Content-Type": "application/json",
        }

    def send_template(self, phone: str, template_id: str, variables: list) -> str:
        components = []
        if variables:
            components = [{
                "type": "body",
                "parameters": [{"type": "text", "text": str(v)} for v in variables],
            }]
        payload = {
            "messaging_product": "whatsapp",
            "to": self._e164_no_plus(phone),
            "type": "template",
            "template": {
                "name": template_id,
                "language": {"code": self.credentials.get("language", "en")},
                "components": components,
            },
        }
        data = self._post(self._url(), headers=self._headers(), json=payload)
        return self._first_id(data)

    def send_text(self, phone: str, message: str) -> str:
        payload = {
            "messaging_product": "whatsapp",
            "to": self._e164_no_plus(phone),
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }
        data = self._post(self._url(), headers=self._headers(), json=payload)
        return self._first_id(data)

    @staticmethod
    def _first_id(data: dict) -> str:
        msgs = data.get("messages") or []
        return msgs[0].get("id", "") if msgs else ""


# ============================================================
# Interakt (BSP)
# ============================================================
class InteraktProvider(WhatsAppProviderBase):
    """Interakt — https://developers.interakt.ai/reference"""

    required = ("api_key",)
    BASE_URL = "https://api.interakt.ai/v1/public/message/"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Basic {self.credentials['api_key']}",
            "Content-Type": "application/json",
        }

    def send_template(self, phone: str, template_id: str, variables: list) -> str:
        payload = {
            "countryCode": "+91",
            "phoneNumber": self._local(phone),
            "callbackData": "telecrm",
            "type": "Template",
            "template": {
                "name": template_id,
                "languageCode": self.credentials.get("language", "en"),
                "bodyValues": [str(v) for v in variables],
            },
        }
        return self._post(self.BASE_URL, headers=self._headers(), json=payload).get("id", "")

    def send_text(self, phone: str, message: str) -> str:
        payload = {
            "countryCode": "+91",
            "phoneNumber": self._local(phone),
            "callbackData": "telecrm",
            "type": "Text",
            "data": {"message": message},
        }
        return self._post(self.BASE_URL, headers=self._headers(), json=payload).get("id", "")


# ============================================================
# AiSensy (BSP)
# ============================================================
class AiSensyProvider(WhatsAppProviderBase):
    """
    AiSensy — https://wiki.aisensy.com/

    AiSensy's public API is template-first (their "campaign" API). A free-form
    text send maps to a campaign named after the config's `text_campaign`, or
    "telecrm_text" by default; that campaign must exist in the tenant's AiSensy
    account, so `send_text` can fail if they haven't made it.
    """

    required = ("api_key",)
    BASE_URL = "https://backend.aisensy.com/campaign/t1/api/v2"

    def _payload(self, campaign: str, phone: str, params: list) -> dict:
        return {
            "apiKey": self.credentials["api_key"],
            "campaignName": campaign,
            "destination": self._e164_no_plus(phone),
            "userName": "TeleCRM",
            "templateParams": [str(p) for p in params],
        }

    def send_template(self, phone: str, template_id: str, variables: list) -> str:
        data = self._post(self.BASE_URL, json=self._payload(template_id, phone, variables))
        return data.get("messageId") or data.get("id", "")

    def send_text(self, phone: str, message: str) -> str:
        campaign = self.credentials.get("text_campaign", "telecrm_text")
        data = self._post(self.BASE_URL, json=self._payload(campaign, phone, [message]))
        return data.get("messageId") or data.get("id", "")


# ============================================================
# WATI (BSP)
# ============================================================
class WatiProvider(WhatsAppProviderBase):
    """
    WATI — https://docs.wati.io/

    The API endpoint is per-tenant (their live server host), so it's part of
    the credentials rather than a constant.
    """

    required = ("access_token", "api_endpoint")

    def _headers(self) -> dict:
        token = self.credentials["access_token"]
        if not token.lower().startswith("bearer "):
            token = f"Bearer {token}"
        return {"Authorization": token, "Content-Type": "application/json"}

    def _base(self) -> str:
        return self.credentials["api_endpoint"].rstrip("/")

    def send_template(self, phone: str, template_id: str, variables: list) -> str:
        # WATI keys template params by name; positional templates use 1..N.
        params = [{"name": str(i + 1), "value": str(v)} for i, v in enumerate(variables)]
        url = (
            f"{self._base()}/api/v1/sendTemplateMessage"
            f"?whatsappNumber={self._e164_no_plus(phone)}"
        )
        payload = {"template_name": template_id, "broadcast_name": "telecrm", "parameters": params}
        data = self._post(url, headers=self._headers(), json=payload)
        return self._wati_id(data)

    def send_text(self, phone: str, message: str) -> str:
        url = (
            f"{self._base()}/api/v1/sendSessionMessage/{self._e164_no_plus(phone)}"
            f"?messageText={requests.utils.quote(message)}"
        )
        data = self._post(url, headers=self._headers())
        return self._wati_id(data)

    @staticmethod
    def _wati_id(data: dict) -> str:
        if isinstance(data.get("message"), dict):
            return data["message"].get("id", "") or ""
        return data.get("id", "") or ""


# ============================================================
# Gupshup (BSP)
# ============================================================
class GupshupProvider(WhatsAppProviderBase):
    """
    Gupshup — https://docs.gupshup.io/

    Form-encoded, not JSON. `source_number` is the tenant's approved WhatsApp
    sender; `app_name` is their Gupshup app.
    """

    required = ("api_key", "app_name", "source_number")
    BASE_URL = "https://api.gupshup.io/wa/api/v1/msg"
    TEMPLATE_URL = "https://api.gupshup.io/wa/api/v1/template/msg"

    def _headers(self) -> dict:
        return {
            "apikey": self.credentials["api_key"],
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def send_text(self, phone: str, message: str) -> str:
        import json as _json

        data = {
            "channel": "whatsapp",
            "source": self.credentials["source_number"],
            "destination": self._e164_no_plus(phone),
            "src.name": self.credentials["app_name"],
            "message": _json.dumps({"type": "text", "text": message}),
        }
        return self._post(self.BASE_URL, headers=self._headers(), data=data).get("messageId", "")

    def send_template(self, phone: str, template_id: str, variables: list) -> str:
        import json as _json

        data = {
            "channel": "whatsapp",
            "source": self.credentials["source_number"],
            "destination": self._e164_no_plus(phone),
            "src.name": self.credentials["app_name"],
            "template": _json.dumps({"id": template_id, "params": [str(v) for v in variables]}),
        }
        return self._post(self.TEMPLATE_URL, headers=self._headers(), data=data).get("messageId", "")


# ============================================================
# Mock (dev + fail-safe fallback)
# ============================================================
class MockWhatsAppProvider(WhatsAppProviderBase):
    """Logs instead of sending. Used when a tenant has no active config."""

    def __init__(self, credentials: dict | None = None):
        # No required credentials — this must never raise.
        self.credentials = credentials or {}

    def send_template(self, phone: str, template_id: str, variables: list) -> str:
        logger.info("[Mock WA] template %s → %s | vars=%s", template_id, phone, variables)
        return f"mock_{uuid.uuid4().hex[:8]}"

    def send_text(self, phone: str, message: str) -> str:
        logger.info("[Mock WA] text → %s: %s", phone, message[:80])
        return f"mock_{uuid.uuid4().hex[:8]}"


# ============================================================
# Factory
# ============================================================
_PROVIDERS = {
    "meta_cloud": MetaCloudProvider,
    "interakt": InteraktProvider,
    "aisensy": AiSensyProvider,
    "wati": WatiProvider,
    "gupshup": GupshupProvider,
}


def provider_class(slug: str):
    return _PROVIDERS.get(slug, MockWhatsAppProvider)


def build_provider(config) -> WhatsAppProviderBase:
    """
    Build the provider for a tenant's WhatsAppConfig.

    Returns a Mock (which no-ops) when the config is missing, inactive, or its
    credentials are incomplete — a send should degrade to "not sent" rather
    than raise deep inside a bulk loop, and the config's `last_error` records
    why so an admin can fix it.
    """
    if config is None or not getattr(config, "is_active", False):
        return MockWhatsAppProvider()
    cls = provider_class(config.provider)
    creds = dict(config.credentials or {})
    creds.setdefault("language", getattr(config, "default_language", "en") or "en")
    try:
        return cls(creds)
    except WhatsAppError as exc:
        logger.warning("WhatsApp config invalid for provider %s: %s", config.provider, exc)
        try:
            type(config).objects.filter(pk=config.pk).update(
                last_error=str(exc)[:500], is_active=False
            )
        except Exception:  # noqa: BLE001 — never let bookkeeping mask the send path
            pass
        return MockWhatsAppProvider()


def verify_config(config) -> tuple[bool, str]:
    """
    Instantiate the provider to confirm the credentials are structurally
    complete. Does not send — a real send happens via the test-send endpoint.
    Returns (ok, message).
    """
    cls = provider_class(config.provider)
    if cls is MockWhatsAppProvider:
        return False, f"No implementation for provider '{config.provider}'."
    try:
        cls(dict(config.credentials or {}))
        return True, "Credentials look complete."
    except WhatsAppError as exc:
        return False, str(exc)
