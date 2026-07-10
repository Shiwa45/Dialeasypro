"""
TeleCRM Backend — apps/core/permissions.py

Custom DRF permission classes for the TeleCRM platform.

Permission hierarchy (least → most access):
  IsAuthenticatedAgent      → Any authenticated agent
  IsActiveAgent             → Authenticated + account not suspended
  IsAgentWithRole           → Agent with specific role(s)
  IsTenantAdmin             → Admin role only
  IsManagerOrAdmin          → Manager or Admin role
  HasFeatureAccess          → Tenant plan has specific feature enabled
  IsSuperAdmin              → Django superuser (public schema only)
"""
import logging

from rest_framework import permissions

from apps.core.constants import AgentRole

logger = logging.getLogger(__name__)


class IsAuthenticatedAgent(permissions.BasePermission):
    """
    Allow access only to authenticated agents.
    Used as the default permission in DRF settings.
    """

    message = "Authentication required. Please log in."

    def has_permission(self, request, view):
        # request.user is an Agent instance set by AgentJWTAuthentication
        return bool(
            request.user
            and hasattr(request.user, "role")  # Is an Agent, not Django User
            and request.user.is_active
        )


class IsActiveAgent(IsAuthenticatedAgent):
    """
    Agent must be authenticated AND tenant account must be active.
    """

    message = "Your account is suspended. Please contact your administrator."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        # Check if tenant is suspended (set by TenantFeatureFlagMiddleware)
        return not getattr(request, "tenant_suspended", False)


class IsAgentWithRole(permissions.BasePermission):
    """
    Base class for role-based permissions.
    Subclass this and set `allowed_roles`.

    Example:
        class IsManagerOrAdmin(IsAgentWithRole):
            allowed_roles = [AgentRole.MANAGER, AgentRole.ADMIN]
    """

    allowed_roles = []
    message = "You don't have permission to perform this action."

    def has_permission(self, request, view):
        if not request.user or not hasattr(request.user, "role"):
            return False
        return request.user.role in self.allowed_roles


class IsTenantAdmin(IsAgentWithRole):
    """Only tenant admins (role=admin) can access."""
    allowed_roles = [AgentRole.ADMIN]
    message = "Only tenant administrators can perform this action."


class IsManagerOrAdmin(IsAgentWithRole):
    """Managers and Admins can access."""
    allowed_roles = [AgentRole.MANAGER, AgentRole.ADMIN]
    message = "Only managers or administrators can perform this action."


class IsSeniorAgentOrAbove(IsAgentWithRole):
    """Senior agents, managers, and admins can access."""
    allowed_roles = [AgentRole.SENIOR_AGENT, AgentRole.MANAGER, AgentRole.ADMIN]
    message = "This action requires senior agent access or above."


class IsNotReadOnly(IsAgentWithRole):
    """Any role except read-only can write."""
    message = "Your account has read-only access."

    def has_permission(self, request, view):
        if not request.user or not hasattr(request.user, "role"):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True  # Read-only can always read
        return request.user.role != AgentRole.READONLY


class HasFeatureAccess(permissions.BasePermission):
    """
    Check if the tenant's plan has a specific feature enabled.

    Usage in view:
        class MyView(APIView):
            permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
            required_feature = FeatureKey.BULK_WHATSAPP

    Or use the factory:
        permission_classes = [
            IsAuthenticatedAgent,
            feature_required(FeatureKey.BULK_WHATSAPP)
        ]
    """

    required_feature = None  # Override in view or use factory
    message = "Your current plan doesn't include this feature. Please upgrade."

    def has_permission(self, request, view):
        # Get required_feature from view class attribute
        feature_key = getattr(view, "required_feature", self.required_feature)

        if not feature_key:
            logger.warning(
                f"HasFeatureAccess used on {view.__class__.__name__} "
                f"without required_feature set — denying access"
            )
            return False

        # Use the has_feature helper injected by TenantFeatureFlagMiddleware
        if hasattr(request, "has_feature") and request.has_feature(feature_key):
            return True

        # Raise (rather than return False) so the client gets a 402 with the
        # structured upsell payload instead of an opaque 403.
        from apps.core.exceptions import FeatureNotEnabledException
        raise FeatureNotEnabledException(feature_key=feature_key)


def feature_required(feature_key):
    """
    Factory function to create a feature permission class.

    Usage:
        permission_classes = [
            IsAuthenticatedAgent,
            feature_required(FeatureKey.BULK_WHATSAPP)
        ]
    """
    return type(
        f"Requires_{feature_key}",
        (HasFeatureAccess,),
        {
            "required_feature": feature_key,
            "message": (
                f"Your current plan doesn't include access to this feature. "
                f"Please upgrade to unlock it."
            ),
        },
    )


def require_feature(request, feature_key):
    """
    Imperative gate for cases where the required feature depends on the request
    body (e.g. a bulk campaign's channel, or an integration's lead source), so
    it can't be expressed as a static `required_feature` on the view.

    Raises FeatureNotEnabledException (402 + upsell payload) when not entitled.
    """
    from apps.core.exceptions import FeatureNotEnabledException

    if not getattr(request, "has_feature", lambda k: False)(feature_key):
        raise FeatureNotEnabledException(feature_key=feature_key)


# Bulk-messaging channel → the plan feature that unlocks it.
BULK_CHANNEL_FEATURES = {
    "whatsapp": FeatureKey.BULK_WHATSAPP,
    "email": FeatureKey.BULK_EMAIL,
    "sms": FeatureKey.BULK_SMS,
}

# Single-message channel → the plan feature that unlocks it.
ONE_CLICK_CHANNEL_FEATURES = {
    "whatsapp": FeatureKey.ONE_CLICK_WHATSAPP,
    "email": FeatureKey.ONE_CLICK_EMAIL,
    "sms": FeatureKey.ONE_CLICK_SMS,
}


def require_channel_feature(request, channel: str, *, bulk: bool):
    """Gate a messaging action on the feature for its channel."""
    mapping = BULK_CHANNEL_FEATURES if bulk else ONE_CLICK_CHANNEL_FEATURES
    feature_key = mapping.get(channel)
    if feature_key:
        require_feature(request, feature_key)


class IsOwnResourceOrManagerAbove(permissions.BasePermission):
    """
    Object-level permission: agents can only access their own resources,
    managers and admins can access all.

    The view must implement get_agent_id() or the object must have agent_id field.
    """

    message = "You can only access your own resources."

    def has_object_permission(self, request, view, obj):
        agent = request.user

        # Admins and managers can access all
        if agent.role in [AgentRole.ADMIN, AgentRole.MANAGER]:
            return True

        # Check object ownership
        if hasattr(obj, "agent_id"):
            return obj.agent_id == agent.pk
        if hasattr(obj, "agent"):
            return obj.agent_id == agent.pk
        if hasattr(obj, "assigned_agent_id"):
            return obj.assigned_agent_id == agent.pk

        return False


class IsSuperAdmin(permissions.BasePermission):
    """
    Allow access only to Django superusers.
    Used for platform-level API endpoints (public schema).
    """

    message = "Super admin access required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


# ============================================================
# MVT View Decorators (for Django template views)
# ============================================================

from functools import wraps

from django.http import HttpResponseForbidden
from django.shortcuts import redirect


def tenant_admin_required(view_func):
    """
    Decorator for MVT views requiring tenant admin login.
    Checks session-based authentication for web views.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        agent_id = request.session.get("agent_id")
        if not agent_id:
            return redirect(f"/crm/login/?next={request.path}")

        # Attach agent to request if not already done
        if not hasattr(request, "agent"):
            try:
                from apps.authentication.models import Agent

                request.agent = Agent.objects.get(pk=agent_id, is_active=True)
            except Exception:
                request.session.flush()
                return redirect("/crm/login/")

        return view_func(request, *args, **kwargs)

    return wrapper


def role_required(*roles):
    """
    Decorator for MVT views requiring specific agent roles.
    Must be used after @tenant_admin_required.

    Usage:
        @tenant_admin_required
        @role_required(AgentRole.ADMIN, AgentRole.MANAGER)
        def my_view(request):
            ...
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            agent = getattr(request, "agent", None)
            if not agent:
                return redirect("/crm/login/")

            if agent.role not in roles:
                return HttpResponseForbidden(
                    "You don't have permission to access this page."
                )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def feature_access_required(feature_key):
    """
    Decorator for MVT views requiring a specific plan feature.

    Usage:
        @tenant_admin_required
        @feature_access_required(FeatureKey.BULK_WHATSAPP)
        def bulk_whatsapp_view(request):
            ...
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not getattr(request, "has_feature", lambda k: False)(feature_key):
                # Render an "upgrade required" page
                from django.shortcuts import render

                return render(
                    request,
                    "tenant_admin/errors/upgrade_required.html",
                    {
                        "feature_key": feature_key,
                        "upgrade_url": "/crm/billing/",
                    },
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
