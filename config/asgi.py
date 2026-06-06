"""
TeleCRM Backend — config/asgi.py

ASGI application entry point.
Handles both HTTP (via Django) and WebSocket (via Django Channels).

WebSocket routes:
  /ws/agent-monitor/          → Real-time agent activity for tenant admin
  /ws/notifications/{token}/  → Push notifications for agents
  /ws/lead-updates/           → Live lead update feed (Phase 2+)
"""
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application
from django.urls import re_path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

# Initialize Django ASGI application early to populate AppRegistry
django_asgi_app = get_asgi_application()

# Import consumers AFTER Django setup to avoid AppRegistryNotReady
from apps.core.consumers import (  # noqa: E402
    AgentMonitorConsumer,
    NotificationConsumer,
)

# ============================================================
# WebSocket URL routing
# ============================================================
websocket_urlpatterns = [
    # Real-time agent monitoring (tenant admin → sees all agents)
    re_path(r"ws/agent-monitor/$", AgentMonitorConsumer.as_asgi()),

    # Per-agent notification stream (agent → receives their notifications)
    re_path(r"ws/notifications/(?P<token>[\w.-]+)/$", NotificationConsumer.as_asgi()),
]

# ============================================================
# Main ASGI Application
# ============================================================
application = ProtocolTypeRouter(
    {
        # HTTP → handled by Django normally
        "http": django_asgi_app,

        # WebSocket → handled by Django Channels
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(websocket_urlpatterns)
            )
        ),
    }
)
