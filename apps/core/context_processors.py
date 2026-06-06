"""
TeleCRM Backend — apps/core/context_processors.py

Django template context processors.
These inject variables into every template context automatically.

Registered in settings.py TEMPLATES['OPTIONS']['context_processors'].
"""
import logging

logger = logging.getLogger(__name__)


def tenant_context(request):
    """
    Injects tenant information into every template.

    Available in templates:
      {{ current_tenant.company_name }}
      {{ current_tenant.schema_name }}
      {{ is_public_schema }}
      {{ current_agent.name }}  (if logged in via session)
      {{ current_agent.role }}
    """
    ctx = {
        "current_tenant": None,
        "is_public_schema": True,
        "current_agent": None,
    }

    # Get tenant from request (set by django-tenants middleware)
    if hasattr(request, "tenant"):
        ctx["current_tenant"] = request.tenant
        ctx["is_public_schema"] = request.tenant.schema_name == "public"

    # Get agent from session (MVT web views)
    agent_id = request.session.get("agent_id")
    if agent_id and not ctx["is_public_schema"]:
        try:
            from apps.authentication.models import Agent
            # Cache agent on request object to avoid multiple DB hits
            if not hasattr(request, "_cached_agent"):
                request._cached_agent = Agent.objects.filter(
                    pk=agent_id, is_active=True
                ).first()
            ctx["current_agent"] = request._cached_agent
        except Exception as exc:
            logger.debug(f"Could not load agent from session: {exc}")

    return ctx


def plan_features_context(request):
    """
    Injects tenant plan features into templates for conditional UI rendering.

    Available in templates:
      {% if features.bulk_whatsapp %}
          <a href="...">Bulk WhatsApp</a>
      {% endif %}

      {{ plan.name }}  ← current plan name
    """
    ctx = {
        "features": {},
        "plan": None,
        "subscription_status": None,
    }

    # Feature flags are injected by TenantFeatureFlagMiddleware
    if hasattr(request, "tenant_features"):
        ctx["features"] = request.tenant_features

    if hasattr(request, "tenant_plan") and request.tenant_plan:
        ctx["plan"] = request.tenant_plan

    # Get subscription status for billing UI
    if (
        hasattr(request, "tenant")
        and request.tenant
        and request.tenant.schema_name != "public"
    ):
        try:
            from apps.plans.models import Subscription
            sub = Subscription.objects.filter(
                tenant=request.tenant
            ).order_by("-created_at").first()
            if sub:
                ctx["subscription_status"] = sub.status
                ctx["subscription"] = sub
        except Exception:
            pass

    return ctx
