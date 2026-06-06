"""
TeleCRM Backend — apps/superadmin/middleware.py

Audit log middleware that captures significant HTTP actions automatically.
Logs all non-GET requests to the admin panel and tenant admin.
"""
import logging

from django.conf import settings

from apps.core.constants import AuditAction

logger = logging.getLogger(__name__)

# HTTP methods that modify data (we log these)
AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths that should never be audited (noise)
SKIP_PATHS = {
    "/health/",
    "/api/v1/health/",
    "/static/",
    "/media/",
    "/__debug__/",
    "/favicon.ico",
}


class AuditLogMiddleware:
    """
    Automatically logs all write operations to the AuditLog table.

    Captures:
    - Django admin actions (super admin panel)
    - Tenant admin write actions
    - All API POST/PUT/PATCH/DELETE requests

    Note: This is supplemented by explicit AuditLog.log() calls
    in views for more detailed change tracking.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only log write operations
        if request.method not in AUDIT_METHODS:
            return response

        # Skip noise paths
        for skip_path in SKIP_PATHS:
            if request.path.startswith(skip_path):
                return response

        # Only log if request resulted in success (2xx or 3xx)
        if response.status_code >= 400:
            return response

        try:
            self._log_action(request, response)
        except Exception as exc:
            # Never let audit logging break the response
            logger.error(f"[AuditLog Middleware] Error: {exc}")

        return response

    def _log_action(self, request, response):
        """Create an audit log entry for this request."""
        from apps.superadmin.models import AuditLog

        # Determine actor
        actor_type = "system"
        actor_id = ""
        actor_email = ""

        if request.path.startswith(f"/{settings.ADMIN_URL}"):
            # Super admin panel action
            actor_type = "super_admin"
            if request.user and request.user.is_authenticated:
                actor_id = str(request.user.pk)
                actor_email = request.user.email

        elif request.path.startswith("/crm/"):
            # Tenant admin action
            actor_type = "tenant_admin"
            agent_id = request.session.get("agent_id")
            if agent_id:
                actor_id = str(agent_id)

        elif request.path.startswith("/api/"):
            # API action
            actor_type = "api"
            if hasattr(request, "user") and hasattr(request.user, "email"):
                actor_id = str(getattr(request.user, "pk", ""))
                actor_email = getattr(request.user, "email", "")

        # Determine action from HTTP method
        method_to_action = {
            "POST": AuditAction.CREATE,
            "PUT": AuditAction.UPDATE,
            "PATCH": AuditAction.UPDATE,
            "DELETE": AuditAction.DELETE,
        }
        action = method_to_action.get(request.method, AuditAction.CREATE)

        # Get tenant schema
        tenant_schema = ""
        if hasattr(request, "tenant"):
            tenant_schema = request.tenant.schema_name

        AuditLog.objects.create(
            action=action,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_email=actor_email,
            actor_ip=AuditLog._get_client_ip(request),
            actor_user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
            tenant_schema=tenant_schema,
            entity_type="",
            entity_repr=request.path[:200],
            description=f"{request.method} {request.path} → {response.status_code}",
        )
