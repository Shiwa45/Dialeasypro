"""
TeleCRM Backend — apps/hrms/permissions.py

HRMS-specific object scoping. Employees see their own records; managers and
admins see everyone's. Payroll is admin-only — an agent must never read a
colleague's salary.
"""
from apps.core.constants import AgentRole
from apps.hrms.models import Employee


def employee_for(agent) -> Employee | None:
    """The Employee row for an agent, or None when not enrolled in HRMS."""
    return Employee.objects.filter(agent=agent).select_related("agent").first()


def is_hr_manager(agent) -> bool:
    return getattr(agent, "role", None) in (AgentRole.ADMIN, AgentRole.MANAGER)


def scope_to_visible(qs, agent, field: str = "employee"):
    """
    Restrict a queryset of employee-owned rows to what `agent` may see.
    Managers/admins see all; everyone else only their own rows.
    """
    if is_hr_manager(agent):
        return qs
    employee = employee_for(agent)
    if employee is None:
        return qs.none()
    return qs.filter(**{field: employee})
