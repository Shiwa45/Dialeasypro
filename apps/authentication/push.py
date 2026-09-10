"""
TeleCRM Backend — apps/authentication/push.py

Device push, and an honest account of what it does today.

Agent.fcm_token has existed since the first migration and nothing has ever
read it. This module is the single place that would, so notify() has one
seam to call instead of scattering push logic through the tasks.

WHAT WORKS TODAY: nothing is sent. `send_push` records that it was asked,
reports why it could not deliver, and returns. That is deliberate — a
function that pretends to have sent a push is worse than one that says it
did not, because the failure is then invisible until somebody misses a
follow-up.

WHY: FCM's legacy `fcm.googleapis.com/fcm/send` endpoint, which took a plain
server key, was switched off by Google in 2024. The replacement HTTP v1 API
needs an OAuth token minted from a service-account JSON, which needs the
`google-auth` package and a credentials file this project does not have.

TO TURN IT ON:
  1. pip install google-auth
  2. Put the Firebase service-account JSON on the server and set
     FCM_CREDENTIALS_FILE to its path, and FCM_PROJECT_ID to the project id.
  3. Fill in `_send_via_fcm_v1` below. The call site, the token lookup and
     the payload are already here and already exercised.

Until then the mobile app covers scheduled follow-ups by its own means: it
reads the agent's upcoming follow-ups and asks Android to raise a local
notification at the right time, which needs no server push at all. Push is
only required to reach a device that has not opened the app since the
follow-up was created.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """True when a real transport could actually deliver."""
    return bool(
        getattr(settings, "FCM_CREDENTIALS_FILE", "")
        and getattr(settings, "FCM_PROJECT_ID", "")
    )


def send_push(agent_id: int, *, title: str, body: str = "", data: dict | None = None) -> dict:
    """
    Deliver one notification to an agent's registered device.

    Returns a small result dict rather than raising: a push that cannot be
    sent must never take down the thing that raised the notification, and the
    notification itself is already saved by the time this is called.
    """
    from apps.authentication.models import Agent

    token = (
        Agent.objects.filter(pk=agent_id)
        .values_list("fcm_token", flat=True)
        .first()
    )
    if not token:
        # Overwhelmingly the normal case right now: no client registers one.
        logger.debug("[Push] agent %s has no device token", agent_id)
        return {"sent": False, "reason": "no_token"}

    if not is_configured():
        logger.info(
            "[Push] not configured — would have sent to agent %s: %r. "
            "See apps/authentication/push.py to enable.",
            agent_id, title,
        )
        return {"sent": False, "reason": "not_configured"}

    return _send_via_fcm_v1(token, title=title, body=body, data=data or {})


def _send_via_fcm_v1(token: str, *, title: str, body: str, data: dict) -> dict:
    """
    The real send. Unimplemented on purpose — see the module docstring.

    Left as an explicit failure rather than a silent `pass` so that a
    deployment which sets FCM_PROJECT_ID and expects push to start working
    finds out here, in the log, rather than by an agent missing a call.
    """
    logger.error(
        "[Push] FCM credentials are configured but the v1 sender is not "
        "implemented; dropping %r. Implement _send_via_fcm_v1.", title,
    )
    return {"sent": False, "reason": "sender_not_implemented"}
