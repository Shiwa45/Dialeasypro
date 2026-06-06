"""
TeleCRM Backend — apps/core/consumers.py

Django Channels WebSocket consumers.

AgentMonitorConsumer
  - URL: /ws/agent-monitor/
  - Auth: Session (tenant admin must be logged in)
  - Purpose: Real-time feed of all agents' status for the monitoring dashboard
  - Events pushed: agent_status_update, agent_login, agent_logout, call_started

NotificationConsumer
  - URL: /ws/notifications/{token}/
  - Auth: JWT token in URL
  - Purpose: Per-agent push notifications (new lead, follow-up reminder, etc.)
  - Events pushed: new_lead, followup_reminder, message_received, system_alert
"""
import json
import logging

from channels.exceptions import DenyConnection
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

logger = logging.getLogger(__name__)


class AgentMonitorConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for real-time agent monitoring.
    Only accessible to tenant admins and managers.

    Group naming: monitor_{schema_name}
    All admin connections for the same tenant share one group,
    so broadcasts reach all open monitoring tabs.
    """

    async def connect(self):
        """Authenticate and join the tenant monitoring group."""
        # Get schema from scope (set by django-tenants)
        schema_name = self.scope.get("url_route", {}).get("kwargs", {}).get(
            "schema_name"
        )
        if not schema_name:
            # Try to get from tenant on scope
            tenant = getattr(self.scope.get("user"), "tenant", None)
            schema_name = getattr(tenant, "schema_name", None)

        # Fallback: try session
        session = self.scope.get("session", {})
        agent_id = session.get("agent_id")
        agent_role = session.get("agent_role")

        if not agent_id:
            logger.warning("[WS] AgentMonitor: rejected — no session")
            await self.close(code=4001)
            return

        # Only admins and managers can monitor
        if agent_role not in ["admin", "manager"]:
            logger.warning(
                f"[WS] AgentMonitor: rejected agent {agent_id} — insufficient role {agent_role}"
            )
            await self.close(code=4003)
            return

        # Determine tenant schema from session or scope
        if not schema_name:
            schema_name = session.get("tenant_schema", "public")

        if schema_name == "public":
            await self.close(code=4004)
            return

        self.schema_name = schema_name
        self.group_name = f"monitor_{schema_name}"
        self.agent_id = agent_id

        # Join the monitoring group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        logger.info(
            f"[WS] AgentMonitor: agent {agent_id} connected to {self.group_name}"
        )

        # Send initial connection acknowledgment
        await self.send_json(
            {
                "type": "connection_established",
                "message": "Connected to agent monitoring feed",
                "timestamp": timezone.now().isoformat(),
            }
        )

    async def disconnect(self, close_code):
        """Leave the monitoring group on disconnect."""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(
            f"[WS] AgentMonitor: agent {getattr(self, 'agent_id', '?')} disconnected"
        )

    async def receive_json(self, content, **kwargs):
        """
        Handle messages from client.
        Clients can send pings to keep the connection alive.
        """
        msg_type = content.get("type")
        if msg_type == "ping":
            await self.send_json(
                {"type": "pong", "timestamp": timezone.now().isoformat()}
            )

    # ---- Event handlers (called by channel_layer.group_send) ----

    async def agent_status_update(self, event):
        """Push agent status changes to monitoring dashboard."""
        await self.send_json(event)

    async def call_started(self, event):
        """Notify monitoring dashboard that an agent started a call."""
        await self.send_json(event)

    async def call_ended(self, event):
        """Notify monitoring dashboard that a call ended."""
        await self.send_json(event)

    async def agent_login(self, event):
        """Notify when an agent logs in."""
        await self.send_json(event)

    async def agent_logout(self, event):
        """Notify when an agent logs out."""
        await self.send_json(event)

    async def system_alert(self, event):
        """Push system-level alerts to admin dashboard."""
        await self.send_json(event)


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for per-agent real-time notifications.
    Each agent connects with their JWT token in the URL.

    Group naming: agent_{schema_name}_{agent_id}
    One group per agent — only that agent receives their notifications.
    """

    async def connect(self):
        """Validate JWT token and connect agent to their notification channel."""
        token = self.scope["url_route"]["kwargs"].get("token")
        if not token:
            await self.close(code=4001)
            return

        # Verify token and get agent info
        agent_data = await self._verify_token(token)
        if not agent_data:
            logger.warning("[WS] Notifications: rejected — invalid token")
            await self.close(code=4001)
            return

        self.agent_id = agent_data["agent_id"]
        self.schema_name = agent_data["tenant_schema"]
        self.group_name = f"agent_{self.schema_name}_{self.agent_id}"

        # Join the agent's personal notification group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        logger.info(
            f"[WS] Notifications: agent {self.agent_id} connected ({self.schema_name})"
        )

        await self.send_json(
            {
                "type": "connection_established",
                "message": "Connected to notification feed",
                "timestamp": timezone.now().isoformat(),
            }
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Handle client messages (ping/pong, ack)."""
        msg_type = content.get("type")
        if msg_type == "ping":
            await self.send_json(
                {"type": "pong", "timestamp": timezone.now().isoformat()}
            )
        elif msg_type == "ack":
            # Client acknowledged notification — mark as read
            notification_id = content.get("notification_id")
            if notification_id:
                await self._mark_notification_read(notification_id)

    # ---- Event handlers ----

    async def new_lead(self, event):
        """New lead assigned to this agent."""
        await self.send_json(event)

    async def followup_reminder(self, event):
        """Follow-up reminder for this agent."""
        await self.send_json(event)

    async def message_received(self, event):
        """WhatsApp/email/SMS reply received."""
        await self.send_json(event)

    async def system_alert(self, event):
        """System-level alert for this agent."""
        await self.send_json(event)

    async def call_assigned(self, event):
        """Call assigned to this agent (for auto-dialer)."""
        await self.send_json(event)

    # ---- Helpers ----

    async def _verify_token(self, token: str) -> dict | None:
        """
        Verify JWT token in a sync-to-async wrapper.
        Returns {"agent_id": ..., "tenant_schema": ...} or None.
        """
        from asgiref.sync import sync_to_async

        @sync_to_async
        def verify():
            try:
                from rest_framework_simplejwt.tokens import AccessToken
                payload = AccessToken(token)
                return {
                    "agent_id": payload.get("agent_id"),
                    "tenant_schema": payload.get("tenant_schema"),
                }
            except Exception as exc:
                logger.debug(f"[WS] Token verification failed: {exc}")
                return None

        return await verify()

    async def _mark_notification_read(self, notification_id):
        """Mark a notification as acknowledged (for future notification model)."""
        # Placeholder — implement in Phase 3 when Notification model is added
        pass


# ============================================================
# Helper: Send notification to a specific agent via Channels
# Called from Celery tasks or Django views
# ============================================================

def send_agent_notification(schema_name: str, agent_id: int, event_type: str, data: dict):
    """
    Send a real-time notification to a specific agent's WebSocket connection.
    Call this from Celery tasks or views when you need to push data to an agent.

    Usage:
        send_agent_notification(
            schema_name="acme_realty",
            agent_id=42,
            event_type="new_lead",
            data={"lead_id": 123, "lead_name": "Rahul Sharma", "source": "IndiaMART"}
        )
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    group_name = f"agent_{schema_name}_{agent_id}"

    message = {
        "type": event_type,
        "timestamp": timezone.now().isoformat(),
        **data,
    }

    try:
        async_to_sync(channel_layer.group_send)(group_name, message)
    except Exception as exc:
        logger.error(f"[WS] Failed to send notification to agent {agent_id}: {exc}")


def broadcast_to_monitors(schema_name: str, event_type: str, data: dict):
    """
    Broadcast an event to all admin/manager monitoring dashboards for a tenant.

    Usage:
        broadcast_to_monitors(
            schema_name="acme_realty",
            event_type="call_started",
            data={"agent_id": 5, "agent_name": "Riya Singh", "lead_id": 99}
        )
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    group_name = f"monitor_{schema_name}"

    message = {
        "type": event_type,
        "timestamp": timezone.now().isoformat(),
        **data,
    }

    try:
        async_to_sync(channel_layer.group_send)(group_name, message)
    except Exception as exc:
        logger.error(f"[WS] Failed to broadcast to monitors ({schema_name}): {exc}")
