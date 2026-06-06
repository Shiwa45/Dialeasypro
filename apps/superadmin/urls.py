"""TeleCRM Backend — apps/superadmin/urls.py"""
from django.urls import path
from apps.superadmin.views import SuperAdminDashboardView

app_name = "superadmin"

urlpatterns = [
    path("dashboard/", SuperAdminDashboardView.as_view(), name="dashboard"),
]
