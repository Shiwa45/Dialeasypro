"""
TeleCRM Backend — apps/hrms/permissions.py

HRMS-specific object scoping. Employees see their own records; HR, managers and
admins see everyone's. Payroll is HR/admin only — a manager must never read a
colleague's salary.

Who counts as "sees everyone" is no longer a hardcoded role list here; it is
Cap.HRMS_VIEW_ALL in apps/core/capabilities.py, so adding a role to that table
is enough to widen visibility everywhere at once.
"""
from apps.core.capabilities import Cap, has_capability
from apps.hrms.models import Employee


def employee_for(agent) -> Employee | None:
    """The Employee row for an agent, or None when not enrolled in HRMS."""
    return Employee.objects.filter(agent=agent).select_related("agent").first()


def is_hr_manager(agent) -> bool:
    """
    True when this agent sees the whole org's HRMS rows.

    Kept under the original name because call sites across views.py read
    naturally with it, but the answer now comes from the capability table.
    """
    return has_capability(agent, Cap.HRMS_VIEW_ALL)


def can_approve(agent) -> bool:
    """True when this agent may approve/reject leave and expense claims."""
    return has_capability(agent, Cap.HRMS_APPROVE)


def can_manage(agent) -> bool:
    """True when this agent may edit employees and HRMS configuration."""
    return has_capability(agent, Cap.HRMS_MANAGE)


def scope_to_visible(qs, agent, field: str = "employee"):
    """
    Restrict a queryset of employee-owned rows to what `agent` may see.
    Org-wide viewers see all; everyone else only their own rows.
    """
    if is_hr_manager(agent):
        return qs
    employee = employee_for(agent)
    if employee is None:
        return qs.none()
    return qs.filter(**{field: employee})
