"""
TeleCRM Backend — apps/plans/api_urls.py
Mounted at: /api/v1/billing/
"""
from django.urls import path

from apps.plans.api_views import TenantBillingAPIView

urlpatterns = [
    path("", TenantBillingAPIView.as_view(), name="api_tenant_billing"),
]
