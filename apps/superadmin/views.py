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

        now = timezone.now()
        context["stats"] = {
            "total_tenants": Tenant.objects.exclude(schema_name="public").count(),
            "active_tenants": Tenant.objects.filter(
                subscription_status__in=SubscriptionStatus.ACTIVE_STATUSES,
                is_active=True,
            ).exclude(schema_name="public").count(),
            "trial_tenants": Tenant.objects.filter(
                subscription_status=SubscriptionStatus.TRIAL
            ).count(),
            "suspended_tenants": Tenant.objects.filter(
                subscription_status=SubscriptionStatus.SUSPENDED
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
