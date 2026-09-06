"""
TeleCRM Backend — apps/communications/tests/test_bulk_campaigns.py

Bulk messaging. Every test here pins a fault that shipped, because the failure
mode of this subsystem is silence: a campaign that sends nothing still reports
"completed", and a campaign that sends twice looks identical to one that sent
once. Nothing surfaces unless it is asserted.
"""
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.communications.models import (
    BulkCampaign, CampaignRecipient, EmailLog, SMSLog, WhatsAppMessage,
)
from apps.communications.tasks import (
    _campaign_halted, _check_campaign_completion, _enforce_daily_limit,
    _get_sms_provider, send_email_chunk, send_sms_chunk, send_whatsapp_chunk,
)
from apps.leads.models import Lead

TEST_SCHEMA = "test_tenant"


@pytest.fixture
def leads():
    return [
        Lead.objects.create(name=f"Lead {i}", phone=f"+9198765{i:05d}",
                            email=f"lead{i}@example.com")
        for i in range(3)
    ]


def _campaign(channel="sms", status="running", **kwargs):
    defaults = {
        "name": f"Test {channel}",
        "channel": channel,
        "status": status,
        "audience_filters": {},
    }
    if channel == "sms":
        defaults["sms_text"] = "Hello {{name}}"
    if channel == "email":
        defaults["email_subject"] = "Hi {{name}}"
        defaults["email_body"] = "Body"
    defaults.update(kwargs)
    return BulkCampaign.objects.create(**defaults)


def _recipients(campaign, leads, status="pending"):
    return [
        CampaignRecipient.objects.create(
            campaign=campaign, lead=lead, phone=lead.phone, status=status,
        )
        for lead in leads
    ]


# ============================================================
# Never send the same message twice
# ============================================================

@pytest.mark.django_db
def test_sms_chunk_skips_recipients_already_sent(leads):
    """
    A chunk filtered only on id, so a redelivered or retried task re-sent to
    everyone in it — a real second SMS to a real customer.
    """
    campaign = _campaign("sms")
    recipients = _recipients(campaign, leads)
    CampaignRecipient.objects.filter(pk=recipients[0].pk).update(status="sent")

    ids = [r.pk for r in recipients]
    with patch("apps.communications.tasks._get_sms_provider") as provider:
        provider.return_value.send.return_value = "msg-1"
        send_sms_chunk(TEST_SCHEMA, str(campaign.pk), ids)

    assert provider.return_value.send.call_count == 2  # not 3
    assert SMSLog.objects.count() == 2


@pytest.mark.django_db
def test_rerunning_a_chunk_sends_nothing_more(leads):
    """The same chunk executed twice must not double-send."""
    campaign = _campaign("sms")
    ids = [r.pk for r in _recipients(campaign, leads)]

    with patch("apps.communications.tasks._get_sms_provider") as provider:
        provider.return_value.send.return_value = "msg-1"
        send_sms_chunk(TEST_SCHEMA, str(campaign.pk), ids)
        first = provider.return_value.send.call_count
        send_sms_chunk(TEST_SCHEMA, str(campaign.pk), ids)
        assert provider.return_value.send.call_count == first


# ============================================================
# Pause has to actually stop sending
# ============================================================

@pytest.mark.django_db
@pytest.mark.parametrize("halted_status", ["paused", "cancelled", "failed", "completed"])
def test_chunk_refuses_to_run_for_a_halted_campaign(leads, halted_status):
    """
    Pausing revokes the coordinator task, but by then the chunks are already
    queued with their countdowns — revoking it stops nothing. The chunks have
    to check for themselves.
    """
    campaign = _campaign("sms", status=halted_status)
    ids = [r.pk for r in _recipients(campaign, leads)]

    with patch("apps.communications.tasks._get_sms_provider") as provider:
        send_sms_chunk(TEST_SCHEMA, str(campaign.pk), ids)

    provider.return_value.send.assert_not_called()
    assert SMSLog.objects.count() == 0


@pytest.mark.django_db
def test_pausing_mid_chunk_stops_the_remaining_recipients(leads):
    """
    A 50-message chunk takes long enough that "stops after this chunk" is not
    what an admin pressing Pause means.
    """
    campaign = _campaign("sms")
    ids = [r.pk for r in _recipients(campaign, leads)]

    def pause_after_first(*args, **kwargs):
        BulkCampaign.objects.filter(pk=campaign.pk).update(status="paused")
        return "msg-1"

    with patch("apps.communications.tasks._get_sms_provider") as provider:
        provider.return_value.send.side_effect = pause_after_first
        send_sms_chunk(TEST_SCHEMA, str(campaign.pk), ids)

    assert provider.return_value.send.call_count == 1
    assert CampaignRecipient.objects.filter(
        campaign=campaign, status="pending").count() == 2


@pytest.mark.django_db
def test_campaign_halted_reads_current_state_not_a_stale_object(leads):
    """The object a chunk loaded at start-up cannot know about a later pause."""
    campaign = _campaign("sms")
    assert _campaign_halted(campaign, "test") is False

    BulkCampaign.objects.filter(pk=campaign.pk).update(status="paused")
    # Same in-memory instance, still says running.
    assert campaign.status == "running"
    assert _campaign_halted(campaign, "test") is True


# ============================================================
# Completion must not undo a pause
# ============================================================

@pytest.mark.django_db
def test_completion_does_not_resurrect_a_paused_campaign(leads):
    """
    The last chunk of a just-paused campaign flipped it to "completed" — the
    pause silently undone.
    """
    campaign = _campaign("sms", status="paused")
    _recipients(campaign, leads, status="sent")

    _check_campaign_completion(str(campaign.pk))

    campaign.refresh_from_db()
    assert campaign.status == "paused"


@pytest.mark.django_db
def test_completion_still_completes_a_running_campaign(leads):
    campaign = _campaign("sms", status="running")
    _recipients(campaign, leads, status="sent")

    _check_campaign_completion(str(campaign.pk))

    campaign.refresh_from_db()
    assert campaign.status == "completed"
    assert campaign.completed_at is not None


@pytest.mark.django_db
def test_completion_waits_while_recipients_are_pending(leads):
    campaign = _campaign("sms", status="running")
    _recipients(campaign, leads)  # all pending

    _check_campaign_completion(str(campaign.pk))

    campaign.refresh_from_db()
    assert campaign.status == "running"


# ============================================================
# SMS was never actually sent
# ============================================================

@pytest.mark.django_db
def test_sms_provider_is_real_when_credentials_exist(settings):
    """
    _get_sms_provider() returned MockSMSProvider unconditionally: every bulk
    SMS campaign logged a fake id, marked everyone "sent", and delivered
    nothing, reporting 100% success.
    """
    from apps.communications.providers.sms import MSG91Provider

    settings.MSG91_AUTH_KEY = "test-key"
    assert isinstance(_get_sms_provider(), MSG91Provider)


@pytest.mark.django_db
def test_sms_provider_falls_back_to_mock_when_unconfigured(settings):
    from apps.communications.providers.sms import MockSMSProvider

    settings.MSG91_AUTH_KEY = ""
    assert isinstance(_get_sms_provider(), MockSMSProvider)


def test_msg91_targets_the_json_api_not_the_legacy_endpoint():
    """
    The JSON body is MSG91's v2 shape; it was being POSTed to sendhttp.php,
    the legacy query-string endpoint, which ignores a JSON body.
    """
    from apps.communications.providers.sms import MSG91Provider

    assert MSG91Provider.BASE_URL.endswith("/v2/sendsms")
    assert "sendhttp.php" not in MSG91Provider.BASE_URL


# ============================================================
# Plan caps
# ============================================================

@pytest.mark.django_db
def test_daily_limit_counts_what_was_already_sent(leads):
    """
    The old check compared `0 + count` against the cap, so a tenant could run
    twenty campaigns just under it and never trip the limit.
    """
    from apps.core.exceptions import PlanLimitExceededException

    campaign = _campaign("sms")
    for lead in leads:
        SMSLog.objects.create(lead=lead, campaign=campaign, phone_number=lead.phone,
                              message="x", status="sent")

    class _Plan:
        max_sms_per_day = 4
        max_email_bulk_per_day = 4
        max_whatsapp_bulk_per_day = 4

    class _Sub:
        plan = _Plan()

    with patch("apps.communications.tasks._current_plan", return_value=_Sub()):
        _enforce_daily_limit("sms", 1)  # 3 + 1 = 4, at the cap
        with pytest.raises(PlanLimitExceededException):
            _enforce_daily_limit("sms", 2)  # 3 + 2 = 5, over


@pytest.mark.django_db
def test_no_subscription_does_not_block_sending():
    """The cap is a billing guardrail, not a security control."""
    with patch("apps.communications.tasks._current_plan", return_value=None):
        _enforce_daily_limit("sms", 10_000)  # must not raise


@pytest.mark.django_db
def test_a_zero_limit_means_unlimited():
    class _Plan:
        max_sms_per_day = 0

    class _Sub:
        plan = _Plan()

    with patch("apps.communications.tasks._current_plan", return_value=_Sub()):
        _enforce_daily_limit("sms", 10_000)  # must not raise


# ============================================================
# Scheduling
# ============================================================

@pytest.mark.django_db
def test_a_scheduled_campaign_is_marked_scheduled():
    """
    scheduled_at was accepted while status stayed "draft", and the beat task
    only looks for status="scheduled" — so scheduled campaigns never sent.
    """
    from apps.communications.serializers import BulkCampaignCreateSerializer

    serializer = BulkCampaignCreateSerializer(data={
        "name": "Later", "channel": "sms", "sms_text": "hi",
        "audience_filters": {},
        "scheduled_at": (timezone.now() + timezone.timedelta(hours=2)).isoformat(),
    })
    assert serializer.is_valid(), serializer.errors
    campaign = serializer.save()
    assert campaign.status == "scheduled"


@pytest.mark.django_db
def test_an_unscheduled_campaign_stays_a_draft():
    from apps.communications.serializers import BulkCampaignCreateSerializer

    serializer = BulkCampaignCreateSerializer(data={
        "name": "Now", "channel": "sms", "sms_text": "hi", "audience_filters": {},
    })
    assert serializer.is_valid(), serializer.errors
    assert serializer.save().status == "draft"


@pytest.mark.django_db
def test_scheduling_in_the_past_is_rejected():
    from apps.communications.serializers import BulkCampaignCreateSerializer

    serializer = BulkCampaignCreateSerializer(data={
        "name": "Yesterday", "channel": "sms", "sms_text": "hi",
        "audience_filters": {},
        "scheduled_at": (timezone.now() - timezone.timedelta(hours=1)).isoformat(),
    })
    assert not serializer.is_valid()
    assert "scheduled_at" in serializer.errors


@pytest.mark.django_db
def test_an_email_campaign_needs_a_body_not_just_a_subject():
    """A subject with no body sends blank emails to the whole audience."""
    from apps.communications.serializers import BulkCampaignCreateSerializer

    serializer = BulkCampaignCreateSerializer(data={
        "name": "Empty", "channel": "email", "email_subject": "Hi",
        "email_body": "   ", "audience_filters": {},
    })
    assert not serializer.is_valid()
    assert "email_body" in serializer.errors


# ============================================================
# Email transport
# ============================================================

@pytest.mark.django_db
def test_email_chunk_reuses_one_smtp_connection(leads):
    """
    send_mail() per message opens and tears down a connection each time, which
    trips an SMTP provider's connection-rate limit partway through a campaign.
    """
    campaign = _campaign("email")
    ids = [r.pk for r in _recipients(campaign, leads)]

    with patch("django.core.mail.get_connection") as get_conn:
        send_email_chunk(TEST_SCHEMA, str(campaign.pk), ids)
        assert get_conn.call_count == 1


@pytest.mark.django_db
def test_an_unreachable_mail_server_fails_the_chunk_with_a_reason(leads):
    campaign = _campaign("email")
    ids = [r.pk for r in _recipients(campaign, leads)]

    with patch("django.core.mail.get_connection") as get_conn:
        get_conn.return_value.open.side_effect = OSError("connection refused")
        send_email_chunk(TEST_SCHEMA, str(campaign.pk), ids)

    failed = CampaignRecipient.objects.filter(campaign=campaign, status="failed")
    assert failed.count() == 3
    assert "connection refused" in failed.first().error_message
    campaign.refresh_from_db()
    assert campaign.failed_count == 3


# ============================================================
# Recipient counting
# ============================================================

@pytest.mark.django_db
def test_total_recipients_counts_rows_that_exist(leads):
    """
    bulk_create(ignore_conflicts=True) silently drops duplicates, so counting
    the list we tried to insert over-reports on a relaunch and the progress
    bar never reaches 100%.
    """
    from apps.communications.tasks import send_bulk_sms_campaign

    campaign = _campaign("sms", status="draft")
    with patch("apps.communications.tasks._resolve_campaign_audience",
               return_value=leads + leads):  # every lead twice
        with patch("apps.communications.tasks.send_sms_chunk"):
            send_bulk_sms_campaign(TEST_SCHEMA, str(campaign.pk))

    campaign.refresh_from_db()
    assert campaign.total_recipients == 3
    assert CampaignRecipient.objects.filter(campaign=campaign).count() == 3


# ============================================================
# Why a campaign stopped
# ============================================================
# Now that the daily caps actually enforce, "failed" is a state real tenants
# hit on an ordinary day. A red badge with no reason is not a usable answer.

@pytest.mark.django_db
def test_a_cap_breach_records_a_readable_reason(leads):
    from apps.communications.tasks import send_bulk_sms_campaign

    campaign = _campaign("sms", status="draft")

    class _Plan:
        max_sms_per_day = 1

    class _Sub:
        plan = _Plan()

    with patch("apps.communications.tasks._resolve_campaign_audience", return_value=leads):
        with patch("apps.communications.tasks._current_plan", return_value=_Sub()):
            with pytest.raises(Exception):
                send_bulk_sms_campaign(TEST_SCHEMA, str(campaign.pk))

    campaign.refresh_from_db()
    assert campaign.status == "failed"
    assert campaign.failure_reason, "a failed campaign must say why"
    assert "limit" in campaign.failure_reason.lower()


@pytest.mark.django_db
def test_relaunching_clears_the_previous_failure(leads):
    from apps.communications.tasks import send_bulk_sms_campaign

    campaign = _campaign("sms", status="draft", failure_reason="Daily SMS limit reached")

    with patch("apps.communications.tasks._resolve_campaign_audience", return_value=leads):
        with patch("apps.communications.tasks.send_sms_chunk"):
            send_bulk_sms_campaign(TEST_SCHEMA, str(campaign.pk))

    campaign.refresh_from_db()
    assert campaign.failure_reason == ""


@pytest.mark.django_db
def test_pending_count_is_what_resuming_would_send(leads):
    """The question an admin has when looking at a paused campaign."""
    from apps.communications.serializers import BulkCampaignSerializer

    campaign = _campaign("sms", status="paused")
    recipients = _recipients(campaign, leads)
    CampaignRecipient.objects.filter(pk=recipients[0].pk).update(status="sent")

    data = BulkCampaignSerializer(campaign).data
    assert data["pending_count"] == 2
    assert data["failure_reason"] == ""
