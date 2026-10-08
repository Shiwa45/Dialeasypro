"""
Rules for changing a lead's status by hand (quick-status buttons, the edit
form, the app).

Anyone could set any stage with no reason, so a lead could be "Converted" or
"Lost" with no call and nothing to say why, and reports counted it.

* Lost and Invalid need a reason.
* Converted needs a reason unless a manager or admin sets it.

The reason is written to the lead's activity feed with the change.
"""
from rest_framework.exceptions import ValidationError

from apps.core.constants import AgentRole, LeadStatus


def _is_manager(agent) -> bool:
    return bool(
        getattr(agent, "is_tenant_admin", False)
        or getattr(agent, "role", None) in (AgentRole.ADMIN, AgentRole.MANAGER)
    )


def check_manual_status_change(agent, old_status: str, new_status: str, reason: str) -> str:
    """Return the cleaned reason, or raise a 400 saying what is missing."""
    reason = (reason or "").strip()
    if new_status == old_status:
        return reason
    label = dict(LeadStatus.CHOICES).get(new_status, new_status)
    if new_status in LeadStatus.REASON_REQUIRED and not reason:
        raise ValidationError({"reason": f'Say why this lead is "{label}".'})
    if new_status == LeadStatus.CONVERTED and not reason and not _is_manager(agent):
        raise ValidationError({"reason": "Add a note on the sale (what was sold, invoice or order number)."})
    return reason
