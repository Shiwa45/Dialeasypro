"""
TeleCRM Backend — apps/authentication/urls.py

MVT URL patterns for the tenant admin web interface.
Namespace: tenant_admin
Mounted at: /crm/  (in config/urls.py)
"""
from django.urls import path

from apps.authentication.views import (
    AgentCreateView,
    AgentDeleteView,
    AgentListView,
    AgentUpdateView,
    ProfileView,
    TenantAdminDashboardView,
    TenantAdminLoginView,
    TenantAdminLogoutView,
)

app_name = "tenant_admin"

urlpatterns = [
    # Auth
    path("login/", TenantAdminLoginView.as_view(), name="login"),
    path("logout/", TenantAdminLogoutView.as_view(), name="logout"),

    # Dashboard (root)
    path("", TenantAdminDashboardView.as_view(), name="dashboard"),

    # Agent Management
    path("agents/", AgentListView.as_view(), name="agent_list"),
    path("agents/create/", AgentCreateView.as_view(), name="agent_create"),
    path("agents/<int:pk>/edit/", AgentUpdateView.as_view(), name="agent_update"),
    path("agents/<int:pk>/delete/", AgentDeleteView.as_view(), name="agent_delete"),

    # Profile
    path("profile/", ProfileView.as_view(), name="profile"),
]
