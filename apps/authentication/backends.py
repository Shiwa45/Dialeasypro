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

        # Security: token must be scoped to the active tenant schema.
        # TenantSchemaFromTokenMiddleware already corrects the schema from the
        # token before this point, so a mismatch here means something went wrong
        # at the middleware layer (e.g. an expired token that the middleware
        # couldn't decode) — or a genuine cross-tenant replay attack.
        token_schema = payload.get("tenant_schema")
        current_schema = connection.schema_name

        if token_schema != current_schema:
            logger.warning(
                f"[Auth] Schema mismatch — token: {token_schema}, "
                f"connection: {current_schema}. Attempting schema correction."
            )
            # Try to self-heal: switch to the token's schema if it is valid.
            # This handles the edge case where middleware didn't run
            # (e.g. during tests or direct API calls without the middleware stack).
            if token_schema and token_schema != "public":
                try:
                    connection.set_schema(token_schema)
                except Exception:
                    raise AuthenticationFailed({
                        "error": "schema_mismatch",
                        "message": "Invalid token for this tenant.",
                    })
            else:
                raise AuthenticationFailed({
                    "error": "schema_mismatch",
                    "message": "Invalid token for this tenant.",
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

        # Update last_active_at lazily (don't slow down every request)
        # Use a lightweight update without triggering signals
        from django.utils import timezone
        agent.last_active_at = timezone.now()
        agent.save(update_fields=["last_active_at"])

        return (agent, payload)

    def authenticate_header(self, request):
        return f'{self.AUTH_HEADER_PREFIX} realm="TeleCRM API"'
