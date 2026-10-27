"""TeleCRM Backend — apps/superadmin/views.py"""
import logging
from django.utils import timezone
from django.views.generic import TemplateView
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator

logger = logging.getLogger(__name__)


def superadmin_dashboard_callback(request, context):
    """
    Callback for Unfold admin dashboard widgets.
    Registered in settings.py: UNFOLD['DASHBOARD_CALLBACK']
    Injects stats into the admin index page context.
    """
    try:
        from apps.tenants.models import Tenant
        from apps.plans.models import Subscription
        from apps.core.constants import SubscriptionStatus
        from django.db.models import Q

        now = timezone.now()
        context["stats"] = {
            "total_tenants": Tenant.objects.exclude(schema_name="public").count(),
            "active_tenants": Tenant.objects.filter(
                subscription_status__in=SubscriptionStatus.ACTIVE_STATUSES,
                is_active=True,
            ).exclude(schema_name="public").count(),
            # Only trials still running: a suspended or switched-off
            # tenant used to count as both "trial" and nothing else.
            "trial_tenants": Tenant.objects.filter(
                subscription_status=SubscriptionStatus.TRIAL, is_active=True,
            ).exclude(schema_name="public").count(),
            # Everyone who can't use the platform: switched off, or in any
            # status that isn't usable (suspended, cancelled, past due...).
            "suspended_tenants": Tenant.objects.exclude(schema_name="public").filter(
                Q(is_active=False) | ~Q(subscription_status__in=SubscriptionStatus.ACTIVE_STATUSES)
            ).count(),
            "new_this_month": Tenant.objects.filter(
                created_at__year=now.year,
                created_at__month=now.month,
            ).exclude(schema_name="public").count(),
        }
    except Exception as exc:
        logger.warning(f"[SuperAdmin Dashboard] Stats error: {exc}")
        context["stats"] = {}

    return context


@method_decorator(staff_member_required, name="dispatch")
class SuperAdminDashboardView(TemplateView):
    """Custom super admin dashboard view (beyond Django admin)."""
    template_name = "super_admin/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Context populated by superadmin_dashboard_callback
        return ctx
