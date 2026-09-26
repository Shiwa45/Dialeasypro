"""
A campaign launches once.

Manual Launch checked the status, dispatched the sender, and only then marked
the campaign running. Two clicks — or one click as the scheduler picked up a
scheduled campaign — both passed the check and both dispatched, sending the
whole audience twice. The scheduler already claimed the campaign with a
conditional UPDATE; Launch now does the same.
"""
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.communications.models import BulkCampaign
from apps.communications.views import BulkCampaignLaunchView
from apps.core.constants import AgentRole

pytestmark = pytest.mark.django_db

SENDER = "apps.communications.tasks.send_bulk_sms_campaign.apply_async"


@pytest.fixture
def manager():
    return Agent.objects.create_agent(
        email="m@example.com", name="Mona", password="Pw@12345678", role=AgentRole.MANAGER,
    )


@pytest.fixture
def campaign():
    return BulkCampaign.objects.create(
        name="Diwali", channel="sms", status="draft", sms_text="Hi", audience_filters={},
    )


def _launch(user, campaign):
    request = APIRequestFactory().post(f"/api/v1/comms/campaigns/{campaign.pk}/launch/")
    force_authenticate(request, user=user)
    request.has_feature = lambda key: True
    response = BulkCampaignLaunchView.as_view()(request, pk=campaign.pk)
    response.render()
    return response


def test_a_second_click_during_the_first_does_not_send_again(manager, campaign):
    """The second click lands while the first is still dispatching."""
    dispatches = []
    second = {}

    def dispatch(*args, **kwargs):
        dispatches.append(1)
        if len(dispatches) == 1:
            second["response"] = _launch(manager, campaign)
        return MagicMock(id=f"task-{len(dispatches)}")

    with patch(SENDER, side_effect=dispatch):
        first = _launch(manager, campaign)

    assert first.status_code == 200
    assert second["response"].status_code in (404, 409)
    assert len(dispatches) == 1


def test_losing_the_race_to_the_scheduler_does_not_send_again(manager, campaign):
    """The scheduler claims the campaign after Launch has read it as launchable."""
    from apps.communications import views

    real_gate = views.require_channel_feature

    def scheduler_claims_it(*args, **kwargs):
        BulkCampaign.objects.filter(pk=campaign.pk).update(status="running")
        return real_gate(*args, **kwargs)

    with patch.object(views, "require_channel_feature", side_effect=scheduler_claims_it), \
            patch(SENDER) as sender:
        response = _launch(manager, campaign)

    assert response.status_code == 409
    assert not sender.called


def test_a_launch_that_could_not_be_queued_can_be_retried(manager, campaign):
    with patch(SENDER, side_effect=ConnectionError("broker down")):
        response = _launch(manager, campaign)

    assert response.status_code >= 500

    campaign.refresh_from_db()
    assert campaign.status == "draft"


def test_an_ordinary_launch_still_works(manager, campaign):
    with patch(SENDER, return_value=MagicMock(id="task-1")) as sender:
        response = _launch(manager, campaign)

    assert response.status_code == 200
    assert sender.call_count == 1
    campaign.refresh_from_db()
    assert campaign.status == "running"
    assert campaign.celery_task_id == "task-1"
