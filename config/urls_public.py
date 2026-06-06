"""
TeleCRM Backend — config/urls_public.py

URL configuration for the PUBLIC schema.
Served on: telecrm.in / admin.telecrm.in

Routes:
  /superadmin/        → Django Admin (Unfold theme) — super admin panel
  /api/v1/public/     → Public API (registration, plan listing, subdomain check)
  /health/            → Health check endpoint
  /webhooks/razorpay/ → Razorpay payment webhooks
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.core.views import HealthCheckView
from apps.plans.webhooks import RazorpayWebhookView
from apps.superadmin.views import SuperAdminDashboardView

admin.site.site_header = "TeleCRM Super Admin"
admin.site.site_title = "TeleCRM"
admin.site.index_title = "Platform Management"

urlpatterns = [
    # ---- Root → redirect to admin -------------------------
    path("", RedirectView.as_view(url=f"/{settings.ADMIN_URL}", permanent=False)),

    # ---- Django Admin (Super Admin Panel with Unfold) ------
    path(settings.ADMIN_URL, admin.site.urls),

    # ---- Super Admin Custom Views --------------------------
    path("superadmin-dashboard/", SuperAdminDashboardView.as_view(), name="superadmin_dashboard"),

    # ---- Public API (no auth required) ---------------------
    # Includes: /register/, /check-subdomain/, /plans/
    path("api/v1/public/", include("apps.tenants.urls", namespace="public_api")),

    # ---- Razorpay Webhook ----------------------------------
    path("webhooks/razorpay/", RazorpayWebhookView.as_view(), name="razorpay_webhook"),

    # ---- Health Check --------------------------------------
    path("health/", HealthCheckView.as_view(), name="health_check"),
]

# ---- Development: Serve static/media files -----------------
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    try:
        import debug_toolbar
        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass
