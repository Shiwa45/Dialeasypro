"""
TeleCRM Backend — apps/authentication/tokens.py

JWT token generation and management for Agent authentication.
Uses djangorestframework-simplejwt token infrastructure,
but authenticates Agent model (NOT Django auth.User).
"""
import logging
import uuid

from django.db import connection
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

logger = logging.getLogger(__name__)


def generate_tokens_for_agent(agent) -> dict:
    """
    Generate JWT access + refresh token pair for an Agent.

    JWT Payload includes:
      agent_id      : Agent's DB primary key (int)
      email         : Agent's email
      role          : Agent's role string
      tenant_schema : Current PostgreSQL schema name
      is_admin      : Whether agent is tenant admin
      token_type    : 'refresh'
      jti           : Unique token ID (for blacklisting)

    Returns:
      {
        'access': '<access_token_string>',
        'refresh': '<refresh_token_string>',
        'access_expires_in': <seconds>,
      }
    """
    refresh = RefreshToken()

    # Inject agent-specific claims
    refresh["agent_id"] = agent.pk
    refresh["email"] = agent.email
    refresh["role"] = agent.role
    refresh["tenant_schema"] = connection.schema_name
    refresh["is_admin"] = agent.is_tenant_admin
    refresh["name"] = agent.name

    access = refresh.access_token

    return {
        "access": str(access),
        "refresh": str(refresh),
        "access_expires_in": int(
            access.lifetime.total_seconds()
        ),
        "token_type": "Bearer",
    }


def verify_agent_token(token_string: str) -> dict | None:
    """
    Verify an access token and return its payload.

    Returns the token payload dict if valid, None if invalid/expired.
    """
    try:
        token = AccessToken(token_string)
        return {
            "agent_id": token.get("agent_id"),
            "email": token.get("email"),
            "role": token.get("role"),
            "tenant_schema": token.get("tenant_schema"),
            "is_admin": token.get("is_admin", False),
            "jti": token.get("jti"),
        }
    except Exception as exc:
        logger.debug(f"Token verification failed: {exc}")
        return None


def blacklist_refresh_token(refresh_token_string: str) -> bool:
    """
    Add a refresh token to the JWT blacklist (logout).
    Requires rest_framework_simplejwt.token_blacklist in INSTALLED_APPS.
    """
    try:
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )
        token = RefreshToken(refresh_token_string)
        jti = token.get("jti")

        outstanding, _ = OutstandingToken.objects.get_or_create(
            jti=jti,
            defaults={
                "token": refresh_token_string,
                "expires_at": token.current_time + token.lifetime,
            },
        )
        BlacklistedToken.objects.get_or_create(token=outstanding)
        return True
    except Exception as exc:
        logger.warning(f"Failed to blacklist token: {exc}")
        return False
