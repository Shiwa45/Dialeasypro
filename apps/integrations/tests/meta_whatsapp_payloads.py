"""
TeleCRM Backend — apps/integrations/tests/meta_whatsapp_payloads.py

Sample Meta WhatsApp webhook payloads.

These mirror the shape the WhatsApp Business Platform actually delivers, so
they double as the fixtures a developer can POST at a local server with curl
(see META_WHATSAPP_SETUP.md) instead of waiting on a real ad click.

The referral block is the Click-to-WhatsApp part: Meta sends it on the FIRST
message of an ad-referred conversation and not on the ones after it, and it
carries the ad id as `source_id` — never a campaign or ad name.
"""

WABA_ID = "102290129340398"
PHONE_NUMBER_ID = "106540352242922"
DISPLAY_PHONE_NUMBER = "15550001111"
CUSTOMER_WA_ID = "919876543210"
AD_ID = "23847239847239847"


def text_message(
    *,
    message_id: str = "wamid.HBgMOTE5ODc2NTQzMjEwFQIAEhgUM0E0QkNE",
    text: str = "Hi, I want more information.",
    wa_id: str = CUSTOMER_WA_ID,
    profile_name: str = "Rahul Sharma",
    referral: dict | None = None,
    phone_number_id: str = PHONE_NUMBER_ID,
    timestamp: str = "1717430400",
) -> dict:
    """One inbound text message, optionally carrying ad attribution."""
    message = {
        "from": wa_id,
        "id": message_id,
        "timestamp": timestamp,
        "type": "text",
        "text": {"body": text},
    }
    if referral is not None:
        message["referral"] = referral

    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": WABA_ID,
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": DISPLAY_PHONE_NUMBER,
                        "phone_number_id": phone_number_id,
                    },
                    "contacts": [{
                        "profile": {"name": profile_name},
                        "wa_id": wa_id,
                    }],
                    "messages": [message],
                },
            }],
        }],
    }


def ctwa_referral(ad_id: str = AD_ID, headline: str = "Diwali Offer") -> dict:
    """A Click-to-WhatsApp referral exactly as Meta nests it on the message."""
    return {
        "source_url": f"https://fb.me/{ad_id}",
        "source_id": ad_id,
        "source_type": "ad",
        "headline": headline,
        "body": "Flat 20% off on all 3BHK bookings this festive season.",
        "media_type": "image",
        "image_url": "https://scontent.example/ad-image.jpg",
        "ctwa_clid": "ARAaBbCcDdEeFfGg1234567890",
    }


def ctwa_message(**kwargs) -> dict:
    """An ad-referred first message — the flow this integration exists for."""
    referral = kwargs.pop("referral", None) or ctwa_referral()
    return text_message(referral=referral, **kwargs)


def image_message(
    *,
    message_id: str = "wamid.HBgMOTE5ODc2NTQzMjEwFQIAEhgUSU1BR0U",
    caption: str = "Is this layout still available?",
) -> dict:
    """A media message — stored with its media id, never its bytes."""
    payload = text_message(message_id=message_id)
    payload["entry"][0]["changes"][0]["value"]["messages"] = [{
        "from": CUSTOMER_WA_ID,
        "id": message_id,
        "timestamp": "1717430500",
        "type": "image",
        "image": {
            "id": "1479537139276761",
            "mime_type": "image/jpeg",
            "sha256": "a1b2c3",
            "caption": caption,
        },
    }]
    return payload


def status_update(
    *,
    message_id: str = "wamid.OUTBOUND123",
    status: str = "delivered",
    timestamp: str = "1717430600",
) -> dict:
    """A delivery receipt for a message the CRM sent."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": WABA_ID,
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": DISPLAY_PHONE_NUMBER,
                        "phone_number_id": PHONE_NUMBER_ID,
                    },
                    "statuses": [{
                        "id": message_id,
                        "status": status,
                        "timestamp": timestamp,
                        "recipient_id": CUSTOMER_WA_ID,
                        "conversation": {"id": "CONV123"},
                    }],
                },
            }],
        }],
    }


def unsupported_event() -> dict:
    """
    A delivery for a field this integration does not handle.

    Meta sends these to any app subscribed to more than `messages`; they must
    be ignored without erroring, or the endpoint gets disabled for flapping.
    """
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": WABA_ID,
            "changes": [{
                "field": "message_template_status_update",
                "value": {
                    "event": "APPROVED",
                    "message_template_id": 1234,
                    "message_template_name": "order_update",
                },
            }],
        }],
    }


def malformed_payload() -> dict:
    """Structurally valid JSON that is nonsense for this endpoint."""
    return {"object": "whatsapp_business_account", "entry": "not-a-list"}


def message_without_id() -> dict:
    """A message with no wamid — unusable, because there is no idempotency key."""
    payload = text_message()
    del payload["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
    return payload
