"""
TeleCRM Backend — apps/authentication/permissions.py

Re-exports all permissions from core, plus auth-specific ones.
Import from here in authentication views.
"""
# Re-export everything from core permissions
from apps.core.permissions import (  # noqa: F401
    IsAuthenticatedAgent,
    IsActiveAgent,
    IsTenantAdmin,
    IsManagerOrAdmin,
    IsSeniorAgentOrAbove,
    IsNotReadOnly,
    HasFeatureAccess,
    feature_required,
    IsOwnResourceOrManagerAbove,
    IsSuperAdmin,
    tenant_admin_required,
    role_required,
    feature_access_required,
)

from rest_framework import permissions


class IsSelfOrManagerAbove(permissions.BasePermission):
    """
    Object-level: agent can only update their own profile.
    Managers and admins can update any agent.
    """
    message = "You can only update your own profile."

    def has_object_permission(self, request, view, obj):
        from apps.core.constants import AgentRole
        agent = request.user
        if agent.role in [AgentRole.ADMIN, AgentRole.MANAGER]:
            return True
        return obj.pk == agent.pk


class CanManageAgent(permissions.BasePermission):
    """
    Object-level: check if the acting agent can manage the target agent.
    Higher role level = can manage lower role level.
    """
    message = "You don't have permission to manage this agent."

    def has_object_permission(self, request, view, obj):
        return request.user.can_manage(obj)
