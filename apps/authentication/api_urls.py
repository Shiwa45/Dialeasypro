"""
TeleCRM Backend — apps/authentication/api_urls.py

DRF API URL patterns for Flutter mobile app.
Mounted at: /api/v1/auth/  (in config/urls.py)
"""
from django.urls import path

from apps.authentication.views import (
    AgentDetailAPIView,
    AgentListAPIView,
    AgentLoginAPIView,
    AgentLogoutAPIView,
    AgentPasswordChangeAPIView,
    AgentProfileAPIView,
    AgentRefreshTokenAPIView,
    AgentSetPasswordAPIView,
    TeamListAPIView,
    TenantInfoAPIView,
)

urlpatterns = [
    # Workspace probe — used by Flutter app to verify workspace name
    path("tenant-info/", TenantInfoAPIView.as_view(), name="api_tenant_info"),

    # Auth lifecycle
    path("login/", AgentLoginAPIView.as_view(), name="api_agent_login"),
    path("refresh/", AgentRefreshTokenAPIView.as_view(), name="api_agent_refresh"),
    path("logout/", AgentLogoutAPIView.as_view(), name="api_agent_logout"),

    # Current agent profile
    path("me/", AgentProfileAPIView.as_view(), name="api_agent_me"),
    path("change-password/", AgentPasswordChangeAPIView.as_view(), name="api_agent_change_password"),

    # Agent management (admin/manager use)
    path("agents/", AgentListAPIView.as_view(), name="api_agent_list"),
    path("agents/<int:pk>/", AgentDetailAPIView.as_view(), name="api_agent_detail"),
    path("agents/<int:pk>/set-password/", AgentSetPasswordAPIView.as_view(), name="api_agent_set_password"),

    # Teams
    path("teams/", TeamListAPIView.as_view(), name="api_team_list"),
]
