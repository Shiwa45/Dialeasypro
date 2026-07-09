"""
TeleCRM Backend — config/urls.py

URL configuration for TENANT schemas (served on tenant subdomains).
E.g.: acmerealty.telecrm.in → this URL conf

Routes:
  /crm/          → Tenant Admin MVT views (Django templates + HTMX)
  /api/v1/       → DRF REST API (for Flutter mobile app)
  /health/       → Health check endpoint
  /ws/           → WebSocket connections (Django Channels)
"""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django.views.static import serve as media_serve

from apps.core.views import HealthCheckView

urlpatterns = [
    # ---- Root redirect to tenant admin login ---------------
    path("", RedirectView.as_view(url="/crm/", permanent=False), name="root"),

    # ---- Tenant Admin (Django MVT) -------------------------
    # All CRM web UI lives here
    path("crm/", include("apps.authentication.urls", namespace="tenant_admin")),
    path("crm/leads/", include("apps.leads.urls")),
    path("crm/calls/", include("apps.calls.urls")),

    # ---- REST API (for Flutter mobile app) -----------------
    path("api/v1/auth/", include(("apps.authentication.api_urls", "authentication"), namespace="api_auth")),
    path("api/v1/leads/", include(("apps.leads.api_urls", "leads"), namespace="api_leads")),
    path("api/v1/calls/", include(("apps.calls.api_urls", "calls"), namespace="api_calls")),
    path("api/v1/comms/", include(("apps.communications.api_urls", "communications"), namespace="api_comms")),
    path("api/v1/integrations/", include(("apps.integrations.api_urls", "integrations"), namespace="api_integrations")),
    path("api/v1/reports/", include(("apps.reports.api_urls", "reports"), namespace="api_reports")),

    # ---- Health Check (used by load balancer) --------------
    path("health/", HealthCheckView.as_view(), name="health_check"),
    path("api/v1/health/", HealthCheckView.as_view(), name="api_health_check"),
]

# ---- Media files ---------------------------------------------
# Served by Django in production too: the reverse proxy forwards ALL paths
# here, and locally-stored call recordings (Cloudinary fallback) live under
# MEDIA_ROOT. Static files are handled by WhiteNoise.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            media_serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]

    # DRF Browsable API in debug mode
    urlpatterns += [
        path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
    ]

    # Django Debug Toolbar
    try:
        import debug_toolbar
        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass

# ============================================================
# WebSocket URL routing is handled in config/asgi.py
# WS routes: /ws/agent-monitor/, /ws/notifications/
# ============================================================
