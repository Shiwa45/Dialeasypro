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

Plan gating
-----------
Two of these rules are sold, not just configured:

* Agent web sign-in is a plan feature (FeatureKey.AGENT_WEB_ACCESS). Without
  it, agents and read-only users are refused on the web whatever the tenant
  setting says; with it, the tenant setting decides.
* The Recruiter role exists only for tenants with the Recruitment module.
  A recruiter on a tenant without it has nothing to do anywhere, so they are
  refused on EVERY client, and the role cannot be handed out.
"""
from django.db import connection

from apps.core.constants import AgentRole, FeatureKey, ModuleKey

WEB_CLIENT_HEADER = "HTTP_X_CLIENT"
WEB_CLIENT_VALUE = "web"

REFUSAL = {
    "error": "web_access_disabled",
    "reason": "setting",
    "message": (
        "Your company has turned off web sign-in for agents. "
        "Please use the DialSathi mobile app."
    ),
}

REFUSAL_NOT_IN_PLAN = {
    "error": "web_access_disabled",
    "reason": "plan",
    "message": (
        "Web sign-in for agents isn't included in your company's plan. "
        "Please use the DialSathi mobile app."
    ),
}

REFUSAL_NO_RECRUITMENT = {
    "error": "recruitment_not_in_plan",
    "reason": "plan",
    "message": (
        "Recruitment isn't included in your company's plan, so recruiter "
        "accounts can't sign in. Please ask your admin."
    ),
}

RECRUITMENT_FEATURES = tuple(ModuleKey.FEATURES[ModuleKey.RECRUITMENT])


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


def feature_checker(request=None):
    """
    `has_feature(key) -> bool` for the current tenant.

    Uses the one the feature-flag middleware put on the request (cached,
    plan + add-ons), and resolves the same effective map itself when there is
    no such request — a call from a shell, a task, or a test.
    """
    has_feature = getattr(request, "has_feature", None) if request is not None else None
    if callable(has_feature):
        return has_feature

    from apps.core.middleware import TenantFeatureFlagMiddleware

    tenant = current_tenant()
    if tenant is None:
        return lambda key: False
    features = TenantFeatureFlagMiddleware(lambda r: None)._get_tenant_features(tenant)
    return lambda key: bool(features.get(key, False))


def agent_web_in_plan(has_feature) -> bool:
    return bool(has_feature(FeatureKey.AGENT_WEB_ACCESS))


def recruitment_in_plan(has_feature) -> bool:
    """The Recruitment module counts only when ALL its features are on — the
    same rule /auth/features/ uses for `modules`, so the web app and the API
    always agree on whether a tenant 'has recruitment'."""
    return all(has_feature(key) for key in RECRUITMENT_FEATURES)


def refusal_for(agent, has_feature, *, web: bool, tenant=None):
    """
    Why this person may not use this client, as the error payload — or None.

    Only agent-workspace roles and recruiters are ever refused. An admin who
    switches the setting off must never be able to lock THEMSELVES out of the
    screen that switches it back on.
    """
    role = getattr(agent, "role", None)

    if role == AgentRole.RECRUITER and not recruitment_in_plan(has_feature):
        return REFUSAL_NO_RECRUITMENT

    if web and role in AgentRole.AGENT_WORKSPACE_ROLES:
        if not agent_web_in_plan(has_feature):
            return REFUSAL_NOT_IN_PLAN
        if not agent_web_access_enabled(tenant):
            return REFUSAL

    return None


def web_access_allowed(agent, has_feature=None, tenant=None) -> bool:
    """May this person use the web app at all?"""
    if has_feature is None:
        has_feature = feature_checker()
    return refusal_for(agent, has_feature, web=True, tenant=tenant) is None
