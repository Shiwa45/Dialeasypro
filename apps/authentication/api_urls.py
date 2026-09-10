"""
TeleCRM Backend — apps/authentication/api_urls.py

DRF API URL patterns for Flutter mobile app.
Mounted at: /api/v1/auth/  (in config/urls.py)
"""
from django.urls import path

from apps.authentication.notification_views import (
    FcmTokenAPIView,
    NotificationListAPIView,
    NotificationReadAllAPIView,
    NotificationReadAPIView,
    NotificationUnreadCountAPIView,
)
from apps.authentication.views import (
    AgentDetailAPIView,
    AgentHeartbeatAPIView,
    AgentListAPIView,
    AgentLoginAPIView,
    AgentLogoutAPIView,
    AgentPasswordChangeAPIView,
    AgentProfileAPIView,
    AgentReactivateAPIView,
    AgentRefreshTokenAPIView,
    AgentSetPasswordAPIView,
    AgentStatusUpdateAPIView,
    LiveAgentsAPIView,
    TeamListAPIView,
    CapabilitiesAPIView,
    TenantFeaturesAPIView,
    TenantInfoAPIView,
    CompanyProfileAPIView,
)

urlpatterns = [
    # Workspace probe — used by Flutter app to verify workspace name
    path("tenant-info/", TenantInfoAPIView.as_view(), name="api_tenant_info"),
    path("company/", CompanyProfileAPIView.as_view(), name="api_company_profile"),

    # Auth lifecycle
    path("login/", AgentLoginAPIView.as_view(), name="api_agent_login"),
    path("refresh/", AgentRefreshTokenAPIView.as_view(), name="api_agent_refresh"),
    path("logout/", AgentLogoutAPIView.as_view(), name="api_agent_logout"),

    # Current agent profile
    path("me/", AgentProfileAPIView.as_view(), name="api_agent_me"),
    path("change-password/", AgentPasswordChangeAPIView.as_view(), name="api_agent_change_password"),

    # Tenant plan / feature entitlements (drives client-side UI gating)
    path("features/", TenantFeaturesAPIView.as_view(), name="api_tenant_features"),
    path("capabilities/", CapabilitiesAPIView.as_view(), name="api_capabilities"),

    # Live agent monitoring
    path("status/", AgentStatusUpdateAPIView.as_view(), name="api_agent_status"),
    path("status/heartbeat/", AgentHeartbeatAPIView.as_view(), name="api_agent_heartbeat"),
    path("live-agents/", LiveAgentsAPIView.as_view(), name="api_live_agents"),

    # Agent management (admin/manager use)
    path("agents/", AgentListAPIView.as_view(), name="api_agent_list"),
    path("agents/<int:pk>/", AgentDetailAPIView.as_view(), name="api_agent_detail"),
    path("agents/<int:pk>/set-password/", AgentSetPasswordAPIView.as_view(), name="api_agent_set_password"),
    path("agents/<int:pk>/reactivate/", AgentReactivateAPIView.as_view(), name="api_agent_reactivate"),

    # Teams
    path("teams/", TeamListAPIView.as_view(), name="api_team_list"),

    # Notifications — the agent's own, always scoped to request.user.
    path("notifications/", NotificationListAPIView.as_view(),
         name="api_notifications"),
    path("notifications/unread-count/", NotificationUnreadCountAPIView.as_view(),
         name="api_notifications_unread_count"),
    path("notifications/read-all/", NotificationReadAllAPIView.as_view(),
         name="api_notifications_read_all"),
    path("notifications/device/", FcmTokenAPIView.as_view(),
         name="api_notifications_device"),
    # Last: a bare <int:pk> would otherwise swallow the literal routes above.
    path("notifications/<int:pk>/read/", NotificationReadAPIView.as_view(),
         name="api_notification_read"),
]
