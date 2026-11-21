"""
TeleCRM Backend — apps/communications/whatsapp_accounts.py

Which of the tenant's WhatsApp accounts a message goes out from.

A tenant can connect several WhatsApp numbers (WhatsAppConfig rows). Every
send answers "from which one?" the same way, in this order:

1. The number the user picked (one-click send, a campaign's sender).
2. The number this lead last wrote to — so a reply continues the
   conversation the customer started, instead of arriving from a stranger —
   as long as it can send the chosen template.
3. The template's own number. Meta approves a template for one WhatsApp
   Business Account (every number in it may send it); a number in another
   account is refused.
4. The default account.

A picked number that can't send the chosen template is an error, not a
silent switch: the user would see one sender and the customer another.
"""
from dataclasses import dataclass


@dataclass
class Sender:
    account: object = None   # WhatsAppConfig, or None when nothing is connected
    error: str = ""


def all_accounts():
    from apps.communications.models import WhatsAppConfig

    return WhatsAppConfig.objects.all()


def default_account():
    from apps.communications.models import WhatsAppConfig

    return WhatsAppConfig.get_default()


def last_account_for_lead(lead):
    """The active account this lead last wrote to, else last heard from us on."""
    from apps.communications.models import WhatsAppMessage

    if lead is None:
        return None
    base = WhatsAppMessage.objects.filter(
        lead=lead, account__isnull=False, account__is_active=True,
    ).select_related("account").order_by("-created_at")
    msg = base.filter(direction="inbound").first() or base.first()
    return msg.account if msg else None


def resolve_sender(*, account_id=None, template=None, lead=None) -> Sender:
    from apps.communications.models import WhatsAppConfig

    if account_id not in (None, ""):
        account = WhatsAppConfig.objects.filter(pk=account_id).first()
        if account is None:
            return Sender(error="That WhatsApp number no longer exists.")
        if template is not None and not template.usable_from(account):
            return Sender(error=(
                f'Template "{template.name}" was approved for {template.account.label}\'s '
                f"WhatsApp Business Account, not {account.label}'s. "
                "Pick a number in that account or another template."
            ))
        return Sender(account=account)
    sticky = last_account_for_lead(lead)
    if template is not None and template.account_id:
        # The lead's number, if that number can send this template (same
        # WhatsApp Business Account); otherwise the template's own number.
        if sticky is not None and template.usable_from(sticky):
            return Sender(account=sticky)
        return Sender(account=template.account)
    if sticky is not None:
        return Sender(account=sticky)
    return Sender(account=default_account())


def can_add_account(request) -> bool:
    """A second number needs the multi-account plan feature."""
    from apps.core.constants import FeatureKey

    if not all_accounts().exists():
        return True
    has = getattr(request, "has_feature", lambda k: False)
    return bool(has(FeatureKey.WHATSAPP_MULTI_PROVIDER))
