"""
WebSocket authentication.

MED-12: the token travelled in the URL, which web servers log — so logs held
week-long admin tokens. It is now offered as the "bearer" subprotocol.
MED-13: the live-agents socket authorised on the role written inside the
token and never checked the agent was still active, so a demoted or
deactivated manager kept watching the floor until the token expired.
"""
from unittest.mock import patch

import pytest
from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.urls import re_path

from apps.authentication.models import Agent
from apps.authentication.tokens import generate_tokens_for_agent
from apps.core.consumers import AgentMonitorConsumer, NotificationConsumer
from apps.core.constants import AgentRole

pytestmark = pytest.mark.django_db(transaction=False)

APP = URLRouter([
    re_path(r"ws/agent-monitor/$", AgentMonitorConsumer.as_asgi()),
    re_path(r"ws/notifications/$", NotificationConsumer.as_asgi()),
])


@pytest.fixture(autouse=True)
def monitoring_on():
    with patch.object(AgentMonitorConsumer, "_has_monitoring_feature", return_value=True):
        yield


@pytest.fixture
def manager():
    return Agent.objects.create_agent(
        email="m@x.com", name="Mona", password="Pw@12345678", role=AgentRole.MANAGER,
    )


def _token(agent):
    return generate_tokens_for_agent(agent)["access"]


def _connect(path, *, subprotocols=None):
    async def go():
        comm = WebsocketCommunicator(APP, path, subprotocols=subprotocols)
        connected, detail = await comm.connect()
        await comm.disconnect()
        return connected, detail

    return async_to_sync(go)()


# ---- MED-12 ------------------------------------------------------------

@pytest.mark.parametrize("path", ["/ws/agent-monitor/", "/ws/notifications/"])
def test_the_token_can_travel_in_a_header_not_the_url(manager, path):
    connected, subprotocol = _connect(path, subprotocols=["bearer", _token(manager)])

    assert connected
    assert subprotocol == "bearer"


def test_tabs_opened_before_the_change_still_connect(manager):
    connected, _ = _connect(f"/ws/notifications/?token={_token(manager)}")

    assert connected


def test_no_token_is_refused():
    connected, _ = _connect("/ws/notifications/")

    assert not connected


# ---- MED-13 ------------------------------------------------------------
# The URL form, which old and new code both read — so these test the role and
# active checks, not the transport.

def test_a_demoted_manager_stops_seeing_the_floor(manager):
    token = _token(manager)  # issued while still a manager
    manager.role = AgentRole.AGENT
    manager.save(update_fields=["role"])

    connected, _ = _connect(f"/ws/agent-monitor/?token={token}")

    assert not connected


@pytest.mark.parametrize("path", ["/ws/agent-monitor/", "/ws/notifications/"])
def test_a_deactivated_agent_cannot_connect(manager, path):
    token = _token(manager)
    manager.is_active = False
    manager.save(update_fields=["is_active"])

    connected, _ = _connect(f"{path}?token={token}")

    assert not connected


def test_a_promoted_agent_is_let_in_straight_away():
    agent = Agent.objects.create_agent(email="a@x.com", name="A", password="Pw@12345678")
    token = _token(agent)  # issued while still a plain agent
    agent.role = AgentRole.MANAGER
    agent.save(update_fields=["role"])

    connected, _ = _connect(f"/ws/agent-monitor/?token={token}")

    assert connected
