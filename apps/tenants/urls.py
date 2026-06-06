"""
TeleCRM Backend — apps/tenants/urls.py

Public API URLs for tenant registration.
Mounted at: /api/v1/public/ (in config/urls_public.py)
"""
from django.urls import path

from apps.plans.views import PublicPlanListView
from apps.tenants.views import TenantCheckSubdomainAPIView, TenantRegistrationAPIView

app_name = "public_api"

urlpatterns = [
    # Tenant self-registration (signup form)
    path("register/", TenantRegistrationAPIView.as_view(), name="tenant_register"),

    # Subdomain availability check (AJAX, called while user types)
    path("check-subdomain/", TenantCheckSubdomainAPIView.as_view(), name="check_subdomain"),

    # Public plan listing (pricing page)
    path("plans/", PublicPlanListView.as_view(), name="plan_list"),
]
