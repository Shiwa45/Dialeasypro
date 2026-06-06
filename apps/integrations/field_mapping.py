"""
TeleCRM Backend — apps/integrations/field_mapping.py

Maps arbitrary inbound lead-source field names (Meta/Google/IndiaMART/webhook)
onto CRM fields, per tenant. Each tenant's products and form questions differ,
so the mapping is configured per integration and stored in
`LeadSourceConfig.options['field_mapping']` as:

    { "<incoming_field_name>": "<crm_target>" }

CRM targets:
  - a STANDARD lead field name  → "phone", "name", "email", "city", ...
  - a custom field              → "custom:<field_key>"
  - "ignore"                    → drop the value (still kept in source_meta)

Anything not mapped falls back to AUTO_MAP (common names), and whatever is still
unmapped is preserved verbatim in the lead's source_meta so no data is ever lost.
"""

# CRM standard lead fields that can be mapped to directly.
STANDARD_TARGETS = {
    "name", "phone", "alternate_phone", "email", "city", "state",
    "pincode", "requirement", "budget", "priority",
    "campaign_name", "ad_name",
}

# Best-effort defaults for common Meta/Google/IndiaMART field names, so the
# integration captures useful data even before a tenant configures a mapping.
# Keys are normalised (lowercased, spaces→underscores) before lookup.
AUTO_MAP = {
    # ---- Name ----
    "full_name": "name",
    "name": "name",
    "first_name": "name",          # combined with last_name in apply_field_mapping
    "sender_name": "name",         # IndiaMART
    "contact_person": "name",      # IndiaMART
    "customer_name": "name",
    "contact_name": "name",
    # ---- Phone ----
    "phone_number": "phone",
    "phone": "phone",
    "mobile": "phone",
    "mobile_number": "phone",
    "contact": "phone",
    "mob": "phone",
    "sender_mobile": "phone",      # IndiaMART
    "whatsapp_number": "alternate_phone",
    "sender_mobile_alt": "alternate_phone",
    # ---- Email ----
    "email": "email",
    "email_address": "email",
    "email_id": "email",
    "sender_email": "email",       # IndiaMART
    # ---- Location ----
    "city": "city",
    "town_city": "city",
    "location": "city",
    "sender_city": "city",         # IndiaMART
    "state": "state",
    "sender_state": "state",
    "pincode": "pincode",
    "pin_code": "pincode",
    "sender_pincode": "pincode",
    "zip": "pincode",
    # ---- Requirement / message ----
    "message": "requirement",
    "your_message": "requirement",
    "requirement": "requirement",
    "subject": "requirement",      # IndiaMART
    "query": "requirement",
    "query_message": "requirement",
    "budget": "budget",
    # ---- Campaign attribution ----
    "campaign_name": "campaign_name",
    "campaign": "campaign_name",
    "ad_name": "ad_name",
    "adset_name": "ad_name",
    "ad_set_name": "ad_name",
}


def _to_value(v):
    """Meta field values arrive as single-item lists; normalise to a string."""
    if isinstance(v, (list, tuple)):
        return str(v[0]) if v else ""
    return "" if v is None else str(v)


def flatten_meta_field_data(field_data: list) -> dict:
    """Convert Meta's [{name, values:[...]}] form data into a flat {name: value} dict."""
    out = {}
    for item in field_data or []:
        name = item.get("name")
        if name:
            out[name] = _to_value(item.get("values"))
    return out


def apply_field_mapping(raw_fields: dict, mapping: dict | None) -> tuple[dict, dict]:
    """
    Apply the tenant's field mapping to a flat dict of incoming fields.

    Returns (lead_data, custom_values):
      lead_data     — {crm_standard_field: value}  (+ always includes "meta": raw_fields)
      custom_values — {custom_field_key: value}
    """
    mapping = mapping or {}
    lead_data: dict = {}
    custom_values: dict = {}

    # Track name parts so we can assemble a full name if only first/last given.
    first_name = ""
    last_name = ""

    for field_name, value in raw_fields.items():
        value = _to_value(value)
        if not value:
            continue

        # Explicit tenant mapping wins; otherwise fall back to auto defaults.
        target = mapping.get(field_name)
        if target is None:
            target = AUTO_MAP.get(field_name.strip().lower().replace(" ", "_"))

        if target in (None, "", "ignore"):
            continue  # unmapped — preserved in meta below

        # Capture name parts specially for first/last assembly.
        low = field_name.strip().lower().replace(" ", "_")
        if target == "name" and low in ("first_name", "firstname"):
            first_name = value
            continue
        if target == "name" and low in ("last_name", "lastname"):
            last_name = value
            continue

        if target.startswith("custom:"):
            custom_values[target.split(":", 1)[1]] = value
        elif target in STANDARD_TARGETS:
            # First non-empty value wins for a given target.
            lead_data.setdefault(target, value)

    # Assemble full name from parts if no explicit full name was mapped.
    if "name" not in lead_data:
        full = f"{first_name} {last_name}".strip()
        if full:
            lead_data["name"] = full

    # Always preserve the complete raw payload.
    lead_data["meta"] = raw_fields
    return lead_data, custom_values
