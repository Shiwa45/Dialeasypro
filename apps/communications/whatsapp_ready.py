"""
TeleCRM Backend — apps/communications/whatsapp_ready.py

Two questions every WhatsApp send has to answer before it goes out:

1. Is WhatsApp actually connected?
   With no active WhatsAppConfig the provider factory hands back the Mock
   provider, which logs and returns a fake id. Bulk campaigns used to treat
   that as success — a whole audience marked "sent", Delivered 0, and not one
   message on a phone. Sends now refuse up front, and the send tasks mark
   recipients FAILED rather than SENT if they ever reach the mock.

2. What goes in {{1}}, {{2}}…?
   Templates carry a `variable_mapping` ({"1": "name", "2": "city"}), but no
   screen ever set it, so every message went out with the literal "{{1}}".
   The mapping is now edited in the web app, validated here, and a template
   whose placeholders aren't all mapped cannot be used for a campaign.
"""
import re

from django.conf import settings

PLACEHOLDER_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")

NOT_CONNECTED = {
    "error": "whatsapp_not_connected",
    "message": (
        "WhatsApp isn't connected. Connect it in Settings → WhatsApp and send "
        "a test message, then try again."
    ),
}
NOT_CONNECTED_REASON = "WhatsApp is not connected — nothing was sent."

# Lead fields a template variable can be filled from. "custom:<key>" is also
# accepted for any custom field.
LEAD_VARIABLE_FIELDS = {
    "name": "Lead name",
    "first_name": "First name",
    "phone": "Phone",
    "email": "Email",
    "city": "City",
    "state": "State",
    "requirement": "Requirement",
    "budget": "Budget",
    "deal_value": "Deal value",
    "campaign_name": "Campaign name",
    "agent_name": "Assigned agent's name",
    "agent_phone": "Assigned agent's phone",
}


def whatsapp_connected() -> bool:
    from apps.communications.models import WhatsAppConfig

    config = WhatsAppConfig.objects.filter(singleton=1).first()
    return bool(config and config.is_active)


def mock_allowed() -> bool:
    """Only tests and local development may 'send' through the mock."""
    return bool(getattr(settings, "WHATSAPP_ALLOW_MOCK", False))


def placeholder_numbers(text: str) -> list[int]:
    return sorted({int(n) for n in PLACEHOLDER_RE.findall(text or "")})


def is_valid_field(field: str) -> bool:
    if field in LEAD_VARIABLE_FIELDS:
        return True
    return field.startswith("custom:") and len(field) > len("custom:")


def unmapped_placeholders(template) -> list[int]:
    mapping = template.variable_mapping or {}
    return [
        n for n in placeholder_numbers(template.body_text)
        if not is_valid_field(str(mapping.get(str(n), "") or ""))
    ]


def lead_value(lead, field: str) -> str:
    """The text a variable mapped to `field` becomes for this lead."""
    if not field:
        return ""
    if field == "first_name":
        return (lead.name or "").strip().split(" ")[0] if lead.name else ""
    if field in ("agent_name", "agent_phone"):
        agent = getattr(lead, "assigned_to", None)
        if agent is None:
            return ""
        return (agent.name if field == "agent_name" else agent.phone) or ""
    if field.startswith("custom:"):
        key = field.split(":", 1)[1]
        value = (
            lead.custom_field_values.filter(field__field_key=key)
            .values_list("value", flat=True).first()
        )
        return value or ""
    value = getattr(lead, field, "")
    if value is None:
        return ""
    # 150000.00 → 150000, 1500.50 stays.
    if hasattr(value, "quantize"):
        value = value.normalize() if value == value.to_integral() else value
        return f"{value:f}"
    return str(value)


def template_values(template, lead) -> list[str]:
    """Ordered values for {{1}}..{{N}} — N is the highest placeholder used."""
    numbers = placeholder_numbers(template.body_text)
    if not numbers:
        return []
    mapping = template.variable_mapping or {}
    return [lead_value(lead, str(mapping.get(str(i), "") or "")) for i in range(1, max(numbers) + 1)]
