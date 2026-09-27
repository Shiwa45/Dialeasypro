"""
TeleCRM Backend — apps/authentication/backends.py

Custom DRF authentication backend for Agent JWT tokens.
Replaces the default TokenAuthentication/JWTAuthentication which
expect Django auth.User — our Agent model is separate and per-tenant.
"""
import logging

from django.db import connection
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.authentication.tokens import verify_agent_token

logger = logging.getLogger(__name__)


class AgentJWTAuthentication(BaseAuthentication):
    """
    Custom DRF authentication that:
    1. Extracts Bearer token from Authorization header
    2. Verifies JWT signature and expiry
    3. Validates tenant_schema in token matches current request schema
    4. Fetches Agent from the current tenant's schema

    Returns (agent, token_payload) tuple on success.
    Returns None (unauthenticated, not an error) if no token present.
    Raises AuthenticationFailed if token is present but invalid.
    """

    AUTH_HEADER = "HTTP_AUTHORIZATION"
    AUTH_HEADER_PREFIX = "Bearer"

    def authenticate(self, request):
        auth_header = request.META.get(self.AUTH_HEADER, "")

        # ---- DIAGNOSTIC LOGGING (temporary) --------------------
        logger.warning(
            "[AuthDiag] path=%s host=%s schema=%s auth_prefix=%r "
            "x_tenant_schema=%r x_workspace_id=%r x_tenant_domain=%r ua=%r",
            request.path,
            request.META.get("HTTP_HOST", ""),
            connection.schema_name,
            auth_header[:20],
            request.META.get("HTTP_X_TENANT_SCHEMA", ""),
            request.META.get("HTTP_X_WORKSPACE_ID", ""),
            request.META.get("HTTP_X_TENANT_DOMAIN", ""),
            request.META.get("HTTP_USER_AGENT", "")[:60],
        )
        # --------------------------------------------------------

        if not auth_header.startswith(f"{self.AUTH_HEADER_PREFIX} "):
            return None  # No token — let other auth classes try (or deny)

        token_string = auth_header[len(self.AUTH_HEADER_PREFIX) + 1:].strip()
        if not token_string:
            return None

        # Verify token
        payload = verify_agent_token(token_string)
        if not payload:
            raise AuthenticationFailed({
                "error": "token_invalid",
                "message": "Invalid or expired token. Please log in again.",
            })

        token_schema = payload.get("tenant_schema")
        current_schema = connection.schema_name

        if token_schema != current_schema:
            logger.warning(
                f"[Auth] Schema mismatch — token: {token_schema!r}, "
                f"connection: {current_schema!r}. Attempting correction."
            )
            if token_schema and token_schema != "public":
                # Token has a valid tenant schema — trust it and switch.
                try:
                    connection.set_schema(token_schema)
                    from apps.core.middleware import TenantSchemaFromTokenMiddleware
                    TenantSchemaFromTokenMiddleware._ensure_tenant_urlconf(request)
                except Exception as exc:
                    logger.error(f"[Auth] Failed to switch to schema {token_schema!r}: {exc}")
                    raise AuthenticationFailed({
                        "error": "schema_mismatch",
                        "message": "Invalid token for this tenant.",
                    })
            else:
                # No tenant claim (or "public"). This used to be trusted and
                # resolved in whichever tenant the request was addressed to —
                # a token that says nothing about its tenant is not one we can
                # honour anywhere. Every token we issue carries the claim.
                raise AuthenticationFailed({
                    "error": "schema_mismatch",
                    "message": "Could not determine tenant. Please log in again.",
                })

        # Fetch agent from current tenant schema
        agent_id = payload.get("agent_id")
        try:
            from apps.authentication.models import Agent
            agent = Agent.objects.get(pk=agent_id, is_active=True)
        except Exception:
            raise AuthenticationFailed({
                "error": "agent_not_found",
                "message": "Agent not found or account deactivated.",
            })

        # last_active_at feeds is_online, a five-minute window, so it needs
        # minute precision at most. It used to be saved on EVERY request — an
        # extra write per API call. A queryset update skips signals too.
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()
        if agent.last_active_at is None or now - agent.last_active_at > timedelta(seconds=60):
            type(agent).objects.filter(pk=agent.pk).update(last_active_at=now)
            agent.last_active_at = now

        return (agent, payload)

    def authenticate_header(self, request):
        return f'{self.AUTH_HEADER_PREFIX} realm="TeleCRM API"'
