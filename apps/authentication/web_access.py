"""
TeleCRM Backend — apps/authentication/web_access.py

Whether agent-workspace users (agent, read-only) may use the WEB app.

Where this line is drawn, and why
---------------------------------
The web app and the mobile app share one API. An agent reaches exactly the
same data through either — their own leads and calls, scoped by
leads_visible_to / calls_visible_to — so this switch is not a security
boundary and is not dressed up as one. It is a policy control: some companies
want the floor on the dialer app only, and an admin should be able to say so.

So it governs the WEB CLIENT: the React app identifies itself with an
`X-Client: web` header, login refuses an agent from that client when the
tenant has switched web access off, and /auth/features/ reports the setting so
a session that was already open signs itself out on its next boot. The mobile
app sends no such header and is never affected.
"""
from django.db import connection

from apps.core.constants import AgentRole

WEB_CLIENT_HEADER = "HTTP_X_CLIENT"
WEB_CLIENT_VALUE = "web"

REFUSAL = {
    "error": "web_access_disabled",
    "message": (
        "Your company has turned off web sign-in for agents. "
        "Please use the DialSathi mobile app."
    ),
}


def is_web_client(request) -> bool:
    return (request.META.get(WEB_CLIENT_HEADER, "") or "").strip().lower() == WEB_CLIENT_VALUE


def current_tenant():
    """
    The tenant for the active schema.

    Read from the database rather than `request.tenant` because login and the
    features endpoint must give the same answer whether or not the tenant
    middleware ran — and a FakeTenant (what connection.set_schema leaves
    behind) carries none of the model's fields.
    """
    from apps.tenants.models import Tenant

    return Tenant.objects.filter(schema_name=connection.schema_name).first()


def agent_web_access_enabled(tenant=None) -> bool:
    tenant = tenant if tenant is not None else current_tenant()
    # No tenant row (public schema, tests without one) → the permissive
    # default, which is also the model default.
    return bool(getattr(tenant, "agent_web_access", True))


def web_access_allowed(agent, tenant=None) -> bool:
    """
    May this person use the web app at all?

    Only agent-workspace roles are ever refused. An admin who switches the
    setting off must never be able to lock THEMSELVES out of the screen that
    switches it back on.
    """
    if getattr(agent, "role", None) not in AgentRole.AGENT_WORKSPACE_ROLES:
        return True
    return agent_web_access_enabled(tenant)
