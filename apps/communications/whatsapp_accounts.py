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

Agents tied to numbers. An admin can give an agent one or more numbers
(WhatsAppConfig.agents). Such an agent sends only from those: steps 2-4 pick
among them, and a template none of them can send is refused. Two things are
deliberately outside that rule:

* Admins and managers, and agents with no number assigned, are unrestricted.
* A free-text reply (no template) goes out from the number the customer
  last wrote to. Meta only accepts free text inside the 24-hour window of the
  number the customer messaged; from any other number it fails, so the
  "assigned" number would be the wrong one exactly when the agent is
  answering a customer.
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


def allowed_account_ids(agent):
    """
    The numbers this agent may send from, as a list of ids — or None when the
    agent may use every number (admins, managers, and agents not tied to any
    number, which is how every tenant starts).
    """
    if agent is None or getattr(agent, "is_manager", False):
        return None
    ids = list(agent.whatsapp_numbers.order_by("pk").values_list("pk", flat=True))
    return ids or None


def preferred_account(agent):
    """
    The number pre-selected for this agent: among their numbers the company
    default if it is one of them, else the first by name. Unrestricted agents
    get the company default.
    """
    from apps.communications.models import WhatsAppConfig

    ids = allowed_account_ids(agent)
    if ids is None:
        return default_account()
    return (
        WhatsAppConfig.objects.filter(pk__in=ids)
        .order_by("-is_default", "-is_active", "label", "pk")
        .first()
    )


def _only_from(ids) -> str:
    from apps.communications.models import WhatsAppConfig

    labels = list(WhatsAppConfig.objects.filter(pk__in=ids).order_by("label").values_list("label", flat=True))
    return ", ".join(labels) or "your assigned numbers"


def resolve_sender(*, account_id=None, template=None, lead=None, agent=None) -> Sender:
    from apps.communications.models import WhatsAppConfig

    allowed = allowed_account_ids(agent)
    sticky = last_account_for_lead(lead)
    free_text = template is None

    if account_id not in (None, ""):
        account = WhatsAppConfig.objects.filter(pk=account_id).first()
        if account is None:
            return Sender(error="That WhatsApp number no longer exists.")
        # A free-text reply on the customer's own conversation is allowed
        # from that number even when it isn't one of the agent's.
        reply_on_their_number = free_text and sticky is not None and sticky.pk == account.pk
        if allowed is not None and account.pk not in allowed and not reply_on_their_number:
            return Sender(error=f"You can send only from: {_only_from(allowed)}.")
        if template is not None and not template.usable_from(account):
            return Sender(error=(
                f'Template "{template.name}" was approved for {template.account.label}\'s '
                f"WhatsApp Business Account, not {account.label}'s. "
                "Pick a number in that account or another template."
            ))
        return Sender(account=account)

    if allowed is None:
        # Unrestricted: the original order, unchanged.
        if template is not None and template.account_id:
            # The lead's number, if that number can send this template (same
            # WhatsApp Business Account); otherwise the template's own number.
            if sticky is not None and template.usable_from(sticky):
                return Sender(account=sticky)
            return Sender(account=template.account)
        if sticky is not None:
            return Sender(account=sticky)
        return Sender(account=default_account())

    # ---- An agent tied to numbers ----
    if free_text:
        # Replying: the number the customer wrote to (see the module note).
        if sticky is not None:
            return Sender(account=sticky)
        return Sender(account=preferred_account(agent))

    candidates = []
    if sticky is not None and sticky.pk in allowed:
        candidates.append(sticky)
    preferred = preferred_account(agent)
    if preferred is not None:
        candidates.append(preferred)
    candidates.extend(
        WhatsAppConfig.objects.filter(pk__in=allowed).order_by("-is_default", "-is_active", "label", "pk")
    )
    for account in candidates:
        if template.usable_from(account):
            return Sender(account=account)
    return Sender(error=(
        f'None of your WhatsApp numbers ({_only_from(allowed)}) can send template "{template.name}". '
        "Ask your admin, or pick another template."
    ))


def can_add_account(request) -> bool:
    """A second number needs the multi-account plan feature."""
    from apps.core.constants import FeatureKey

    if not all_accounts().exists():
        return True
    has = getattr(request, "has_feature", lambda k: False)
    return bool(has(FeatureKey.WHATSAPP_MULTI_PROVIDER))
