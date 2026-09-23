"""
TeleCRM Backend — apps/plans/api_views.py

What a tenant can see about their own subscription.

The CRM's Billing tab had nothing behind it: it told the customer to go to
`/superadmin/`, which is the platform operator's panel and not somewhere a
tenant can sign in, next to placeholder phone numbers. A paying customer
could not see which plan they were on, what it allows, how much of it they
have used, or when it renews.

Everything here is read-only and scoped to the tenant of the current schema.
Plans, subscriptions and invoices live in the public schema, so each query
names the tenant explicitly rather than relying on the search path.
"""
import logging

from django.conf import settings
from django.db import connection
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import IsTenantAdmin
from apps.core.constants import FeatureKey, SubscriptionStatus
from apps.core.quotas import active_agent_count, agent_limit
from apps.plans.models import Invoice, Subscription
from apps.plans.serializers import InvoiceSerializer

logger = logging.getLogger(__name__)

# Enough to cover a year of monthly billing without paginating a list nobody
# scrolls; older invoices are a support request, not a screen.
INVOICE_LIMIT = 24


class TenantBillingAPIView(APIView):
    """
    GET /api/v1/billing/

    The tenant's own plan, what it allows, how much of it is used, when it
    renews, and their invoices.

    Admin-only: invoice amounts and GST totals are the business's financial
    records, not something every agent on the floor needs.
    """

    permission_classes = [IsTenantAdmin]

    def get(self, request):
        from apps.tenants.models import Tenant

        tenant = Tenant.objects.filter(schema_name=connection.schema_name).select_related("plan").first()
        if tenant is None:
            return Response(
                {"error": "workspace_not_found", "message": "Workspace not found."},
                status=404,
            )

        subscription = (
            Subscription.objects.filter(tenant=tenant)
            .select_related("plan")
            .order_by("-created_at")
            .first()
        )
        # The subscription's plan is what billing actually runs on; the
        # tenant's own plan field is a convenience copy kept in step by the
        # admin. Prefer the former, fall back to the latter.
        plan = (subscription.plan if subscription else None) or tenant.plan

        return Response({
            "plan": self._plan(plan),
            "subscription": self._subscription(subscription, tenant),
            "usage": self._usage(plan),
            "features": self._features(plan),
            "invoices": InvoiceSerializer(
                Invoice.objects.filter(tenant=tenant).order_by("-invoice_date", "-created_at")[:INVOICE_LIMIT],
                many=True,
            ).data,
            "support": self._support(),
        })

    # ---- Pieces --------------------------------------------

    def _plan(self, plan):
        if plan is None:
            return None
        return {
            "name": plan.name,
            "slug": plan.slug,
            "description": plan.description,
            "price_monthly": str(plan.price_monthly),
            "price_yearly": str(plan.price_yearly),
        }

    def _subscription(self, subscription, tenant):
        """
        Where the tenant stands. Falls back to the tenant row when no
        Subscription exists — a trial created by the onboarding flow has its
        dates there, and showing nothing would read as "you have no account".
        """
        if subscription is None:
            return {
                "status": tenant.subscription_status,
                "billing_cycle": "",
                "current_period_start": None,
                "current_period_end": None,
                "trial_end": tenant.trial_ends_at,
                "days_until_renewal": None,
                "cancel_at_period_end": False,
                "is_active": tenant.subscription_status in SubscriptionStatus.ACTIVE_STATUSES,
            }

        return {
            "status": subscription.status,
            "billing_cycle": subscription.billing_cycle,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "trial_end": subscription.trial_end,
            "days_until_renewal": subscription.days_until_renewal,
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "is_active": subscription.status in SubscriptionStatus.ACTIVE_STATUSES,
        }

    def _usage(self, plan):
        """
        Used against allowed, for the things a tenant actually runs out of.

        `agents.limit` is the enforced cap, which is the tenant's own seat
        override when the platform has set one — not the plan's headline
        number, or the bar would sit at the wrong place for exactly the
        customers whose limit was changed by hand.
        """
        from apps.leads.models import CustomField

        limits = {
            "agents": agent_limit(),
            "leads": getattr(plan, "max_leads", None) or None,
            "leads_per_day": getattr(plan, "max_leads_per_day", None) or None,
            "custom_fields": getattr(plan, "custom_fields_limit", None) or None,
            "storage_gb": getattr(plan, "storage_gb", None) or None,
        }

        from apps.core.quotas import _lead_counts

        leads_total, leads_today = _lead_counts()
        used = {
            "agents": active_agent_count(),
            "leads": leads_total,
            "leads_per_day": leads_today,
            "custom_fields": CustomField.objects.filter(is_active=True).count(),
            "storage_gb": None,  # Not metered yet — reported as unknown, not as 0.
        }

        return {
            key: {"used": used.get(key), "limit": limits.get(key)}
            for key in limits
        }

    def _features(self, plan):
        """What the plan includes, labelled for a human."""
        if plan is None:
            return []
        return [
            {
                "key": f.feature_key,
                "label": FeatureKey.LABELS.get(f.feature_key, f.feature_key),
                "enabled": f.is_enabled,
            }
            for f in plan.features.all().order_by("feature_key")
        ]

    def _support(self):
        """
        Who to contact. Read from the platform's own settings rather than
        hardcoded in the client, which is how the tab came to show
        "+91-1800-XXX-XXXX" to real customers.
        """
        from apps.superadmin.models import GlobalSettings

        def setting(key, default=""):
            try:
                return GlobalSettings.get(key, default) or default
            except Exception:  # noqa: BLE001 — a missing table must not 500 billing
                return default

        return {
            "platform_name": setting("platform_name", "TeleCRM"),
            "email": setting("support_email", settings.SUPPORT_EMAIL),
            # Only what has actually been configured. A blank is rendered as
            # nothing; a placeholder is rendered as a number people dial.
            "phone": setting("support_phone", ""),
            "whatsapp": setting("support_whatsapp", ""),
        }
