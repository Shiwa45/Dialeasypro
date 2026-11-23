"""
Workflows — triggers, conditions, steps, waits and safety.

Runs are started after the caller's transaction commits, so tests that need
a run to execute wrap the triggering change in
django_capture_on_commit_callbacks(execute=True). Celery runs eagerly in the
test settings.
"""
from datetime import time, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.automation.constants import RunStatus, Trigger
from apps.automation.models import Workflow, WorkflowRun
from apps.automation.services import matching
from apps.automation.services.engine import advance, fire
from apps.communications.models import WhatsAppConfig, WhatsAppMessage, WhatsAppTemplate
from apps.core.constants import AgentRole, FeatureKey
from apps.leads.models import FollowUp, Lead, LeadNote

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def plan_has_workflows():
    with patch("apps.automation.services.engine.automation_enabled", return_value=True):
        yield


@pytest.fixture(autouse=True)
def no_real_sends():
    with patch("apps.communications.tasks.send_single_whatsapp.apply_async") as wa, \
         patch("apps.communications.tasks.send_single_sms.apply_async") as sms, \
         patch("apps.core.consumers.send_agent_notification"):
        yield {"wa": wa, "sms": sms}


@pytest.fixture
def agent():
    return Agent.objects.create_agent(email="a@x.com", name="Asha", password="Pw@12345678")


@pytest.fixture
def agent2():
    return Agent.objects.create_agent(email="b@x.com", name="Bala", password="Pw@12345678")


@pytest.fixture
def admin():
    return Agent.objects.create_agent(email="ad@x.com", name="Admin", password="Pw@12345678",
                                      role=AgentRole.ADMIN)


@pytest.fixture
def whatsapp():
    acct = WhatsAppConfig(label="Sales", provider="meta_cloud", is_active=True,
                          credentials={"access_token": "t", "phone_number_id": "p1"})
    acct.save()
    return acct


@pytest.fixture
def template(whatsapp):
    return WhatsAppTemplate.objects.create(
        name="welcome", body_text="Hi {{1}}", variable_mapping={"1": "name"},
        status="approved", account=whatsapp,
    )


def _wf(trigger=Trigger.LEAD_CREATED, steps=None, **kw):
    kw.setdefault("quiet_hours_enabled", False)
    return Workflow.objects.create(
        name=kw.pop("name", "WF"), trigger=trigger, is_active=kw.pop("is_active", True),
        steps=steps or [{"type": "add_note", "text": "Hello {name}"}], **kw,
    )


def _lead(**kw):
    kw.setdefault("name", "Ravi Kumar")
    kw.setdefault("phone", "+919812300001")
    return Lead.objects.create(**kw)


# ============================================================
# Triggers
# ============================================================

def test_a_new_lead_starts_a_lead_created_workflow(django_capture_on_commit_callbacks):
    wf = _wf()
    with django_capture_on_commit_callbacks(execute=True):
        lead = _lead()
    run = WorkflowRun.objects.get(workflow=wf, lead=lead)
    assert run.status == RunStatus.COMPLETED
    assert LeadNote.objects.get(lead=lead).content == "Hello Ravi Kumar"
    wf.refresh_from_db()
    assert wf.runs_count == 1 and wf.last_run_at is not None


def test_a_switched_off_workflow_does_nothing(django_capture_on_commit_callbacks):
    _wf(is_active=False)
    with django_capture_on_commit_callbacks(execute=True):
        _lead()
    assert not WorkflowRun.objects.exists()


def test_without_the_plan_feature_nothing_runs(django_capture_on_commit_callbacks):
    _wf()
    with patch("apps.automation.services.engine.automation_enabled", return_value=False):
        with django_capture_on_commit_callbacks(execute=True):
            _lead()
    assert not WorkflowRun.objects.exists()


def test_status_change_matches_from_and_to(django_capture_on_commit_callbacks):
    wf = _wf(Trigger.LEAD_STATUS_CHANGED, trigger_config={"to": ["interested"], "from": []})
    lead = _lead()
    with django_capture_on_commit_callbacks(execute=True):
        lead.update_status("contacted")
    assert not WorkflowRun.objects.filter(workflow=wf).exists()
    with django_capture_on_commit_callbacks(execute=True):
        lead.update_status("interested")
    run = WorkflowRun.objects.get(workflow=wf)
    assert run.context["old_status"] == "contacted" and run.context["new_status"] == "interested"


def test_assignment_starts_lead_assigned(agent, django_capture_on_commit_callbacks):
    wf = _wf(Trigger.LEAD_ASSIGNED)
    lead = _lead()
    with django_capture_on_commit_callbacks(execute=True):
        lead.assign_to(agent)
    assert WorkflowRun.objects.filter(workflow=wf, lead=lead).exists()


def test_call_triggers_follow_the_call(agent, django_capture_on_commit_callbacks):
    from apps.calls.models import CallDisposition, CallLog

    not_connected = _wf(Trigger.CALL_NOT_CONNECTED, name="missed")
    connected = _wf(Trigger.CALL_CONNECTED, name="talked")
    busy = CallDisposition.objects.create(name="Busy (test)", slug="busy-x", category="not_connected")
    outcome = _wf(Trigger.CALL_OUTCOME, name="busy", trigger_config={"dispositions": [busy.pk]})
    lead = _lead(assigned_to=agent)
    with django_capture_on_commit_callbacks(execute=True):
        CallLog.objects.create(agent=agent, lead=lead, phone_number=lead.phone, direction="outbound",
                               started_at=timezone.now(), is_connected=False, disposition=busy)
    assert WorkflowRun.objects.filter(workflow=not_connected).exists()
    assert not WorkflowRun.objects.filter(workflow=connected).exists()
    assert WorkflowRun.objects.filter(workflow=outcome).exists()


def test_keyword_auto_reply(whatsapp, template, no_real_sends, django_capture_on_commit_callbacks):
    from apps.automation.hooks import whatsapp_received

    wf = _wf(Trigger.WHATSAPP_RECEIVED, repeat=True,
             trigger_config={"keywords": ["price", "brochure"], "match": "contains"},
             steps=[{"type": "send_whatsapp", "template": template.pk}])
    lead = _lead()
    with django_capture_on_commit_callbacks(execute=True):
        whatsapp_received(lead, message_id="wamid.1", text="Hi, what is the PRICE?", account_id=whatsapp.pk)
        whatsapp_received(lead, message_id="wamid.2", text="ok thanks", account_id=whatsapp.pk)
        whatsapp_received(lead, message_id="wamid.1", text="Hi, what is the PRICE?", account_id=whatsapp.pk)
    assert WorkflowRun.objects.filter(workflow=wf).count() == 1
    sent = no_real_sends["wa"].call_args.kwargs["kwargs"]
    assert sent["template_id"] == template.pk and sent["variables"] == ["Ravi Kumar"]
    assert sent["account_id"] == whatsapp.pk


def test_missed_followups_are_found_by_the_scan(agent, django_capture_on_commit_callbacks):
    from apps.automation.services.scans import run_scans

    wf = _wf(Trigger.FOLLOWUP_MISSED, trigger_config={"minutes": 30})
    lead = _lead(assigned_to=agent)
    FollowUp.objects.create(lead=lead, assigned_to=agent, scheduled_at=timezone.now() - timedelta(hours=1))
    FollowUp.objects.create(lead=lead, assigned_to=agent, scheduled_at=timezone.now() - timedelta(minutes=5))
    with django_capture_on_commit_callbacks(execute=True):
        assert run_scans() == 1
        assert run_scans() == 0   # the same missed follow-up is not chased twice
    assert WorkflowRun.objects.filter(workflow=wf).count() == 1


def test_inactive_leads_are_found_by_the_scan(django_capture_on_commit_callbacks):
    from apps.automation.services.scans import run_scans

    wf = _wf(Trigger.LEAD_INACTIVE, trigger_config={"days": 3})
    quiet = _lead(phone="+919812300011")
    Lead.objects.filter(pk=quiet.pk).update(last_contacted_at=timezone.now() - timedelta(days=5))
    recent = _lead(phone="+919812300012")
    Lead.objects.filter(pk=recent.pk).update(last_contacted_at=timezone.now() - timedelta(days=1))
    won = _lead(phone="+919812300013", status="converted")
    Lead.objects.filter(pk=won.pk).update(last_contacted_at=timezone.now() - timedelta(days=9))
    with django_capture_on_commit_callbacks(execute=True):
        run_scans()
        run_scans()
    assert list(WorkflowRun.objects.filter(workflow=wf).values_list("lead_id", flat=True)) == [quiet.pk]


# ============================================================
# Conditions and dedupe
# ============================================================

def test_conditions_must_all_match(agent):
    lead = _lead(source="website", city="Noida", tags=["Hot"], assigned_to=agent)
    assert matching.lead_matches(lead, {"sources": ["website"], "cities": ["noida"], "tags": ["hot"]})
    assert not matching.lead_matches(lead, {"sources": ["website"], "cities": ["Delhi"]})
    assert matching.lead_matches(lead, {"assigned_to": [agent.pk]})
    assert not matching.lead_matches(lead, {"assigned_to": [0]})


def test_a_lead_goes_through_a_once_per_lead_workflow_once(django_capture_on_commit_callbacks):
    wf = _wf(Trigger.LEAD_STATUS_CHANGED, trigger_config={"to": ["interested", "follow_up"]})
    lead = _lead()
    with django_capture_on_commit_callbacks(execute=True):
        lead.update_status("interested")
        lead.update_status("follow_up")
    assert WorkflowRun.objects.filter(workflow=wf).count() == 1


def test_a_repeating_workflow_runs_for_each_event(django_capture_on_commit_callbacks):
    wf = _wf(Trigger.LEAD_STATUS_CHANGED, repeat=True, trigger_config={"to": ["interested", "follow_up"]})
    lead = _lead()
    with django_capture_on_commit_callbacks(execute=True):
        lead.update_status("interested")
        lead.update_status("follow_up")
    assert WorkflowRun.objects.filter(workflow=wf).count() == 2


def test_a_workflows_own_change_does_not_set_off_another(django_capture_on_commit_callbacks):
    changer = _wf(name="changer", steps=[{"type": "change_status", "status": "interested"}])
    reactor = _wf(Trigger.LEAD_STATUS_CHANGED, name="reactor", trigger_config={"to": ["interested"]})
    with django_capture_on_commit_callbacks(execute=True):
        lead = _lead()
    lead.refresh_from_db()
    assert lead.status == "interested"
    assert WorkflowRun.objects.filter(workflow=changer).exists()
    assert not WorkflowRun.objects.filter(workflow=reactor).exists()


# ============================================================
# Steps, waits, guards, quiet hours
# ============================================================

def test_a_wait_pauses_and_the_tick_resumes(agent, django_capture_on_commit_callbacks):
    wf = _wf(steps=[
        {"type": "add_note", "text": "first"},
        {"type": "wait", "amount": 2, "unit": "days"},
        {"type": "add_note", "text": "second"},
    ])
    with django_capture_on_commit_callbacks(execute=True):
        lead = _lead()
    run = WorkflowRun.objects.get(workflow=wf)
    assert run.status == RunStatus.WAITING and run.current_step == 2
    assert run.next_run_at > timezone.now() + timedelta(days=1, hours=23)
    advance(run.pk)  # too early: nothing happens
    assert LeadNote.objects.filter(lead=lead).count() == 1

    WorkflowRun.objects.filter(pk=run.pk).update(next_run_at=timezone.now() - timedelta(seconds=1))
    from apps.automation.tasks import _tick_one

    _tick_one("test_tenant")
    run.refresh_from_db()
    assert run.status == RunStatus.COMPLETED
    assert sorted(LeadNote.objects.filter(lead=lead).values_list("content", flat=True)) == ["first", "second"]


def test_a_reminder_is_skipped_when_the_lead_has_replied(
        whatsapp, template, no_real_sends, django_capture_on_commit_callbacks):
    wf = _wf(steps=[
        {"type": "send_whatsapp", "template": template.pk},
        {"type": "wait", "amount": 1, "unit": "days"},
        {"type": "send_whatsapp", "template": template.pk, "only_if_no_reply": True},
    ])
    with django_capture_on_commit_callbacks(execute=True):
        lead = _lead()
    run = WorkflowRun.objects.get(workflow=wf)
    WhatsAppMessage.objects.create(lead=lead, direction="inbound", content="yes", status="received")
    WorkflowRun.objects.filter(pk=run.pk).update(next_run_at=timezone.now())
    advance(run.pk)
    run.refresh_from_db()
    assert no_real_sends["wa"].call_count == 1
    assert run.log[-1]["result"] == "skipped" and "replied" in run.log[-1]["detail"]


def test_status_guard_stops_a_step_when_the_lead_moved_on(django_capture_on_commit_callbacks):
    wf = _wf(repeat=True, steps=[{"type": "add_note", "text": "x", "only_if_status_in": ["new"]}])
    lead = _lead(status="interested")
    run = fire(Trigger.LEAD_CREATED, lead, event_key=f"t:{lead.pk}", only=wf)[0]
    advance(run.pk)
    assert not LeadNote.objects.filter(lead=lead).exists()


def test_quiet_hours_hold_messages_until_morning(whatsapp, template, no_real_sends):
    wf = _wf(repeat=True, steps=[{"type": "send_whatsapp", "template": template.pk}],
             quiet_hours_enabled=True, quiet_start=time(21, 0), quiet_end=time(9, 0))
    lead = _lead()
    run = fire(Trigger.LEAD_CREATED, lead, event_key=f"t:{lead.pk}", only=wf)[0]
    late = timezone.localtime().replace(hour=23, minute=15)
    with patch("apps.automation.services.engine.timezone.now", return_value=late):
        advance(run.pk)
    run.refresh_from_db()
    assert run.status == RunStatus.WAITING and not no_real_sends["wa"].called
    assert timezone.localtime(run.next_run_at).hour == 9


def test_quiet_hours_cross_midnight():
    wf = Workflow(quiet_hours_enabled=True, quiet_start=time(21, 0), quiet_end=time(9, 0))
    assert matching.in_quiet_hours(wf, time(22, 0))
    assert matching.in_quiet_hours(wf, time(3, 0))
    assert not matching.in_quiet_hours(wf, time(12, 0))


def test_round_robin_assignment(agent, agent2):
    wf = _wf(repeat=True, steps=[{"type": "assign", "agents": [agent.pk, agent2.pk], "mode": "round_robin"}])
    owners = []
    for i in range(3):
        lead = _lead(phone=f"+91981230020{i}")
        run = fire(Trigger.LEAD_CREATED, lead, event_key=f"t:{lead.pk}", only=wf)[0]
        advance(run.pk)
        lead.refresh_from_db()
        owners.append(lead.assigned_to_id)
    assert owners == [agent.pk, agent2.pk, agent.pk]


def test_followup_and_notification(agent):
    from apps.authentication.models import Notification

    wf = _wf(repeat=True, steps=[
        {"type": "create_followup", "in_hours": 4, "note": "Call {first_name}"},
        {"type": "notify", "to": "owner", "message": "New hot lead {name}"},
    ])
    lead = _lead(assigned_to=agent)
    run = fire(Trigger.LEAD_CREATED, lead, event_key=f"t:{lead.pk}", only=wf)[0]
    advance(run.pk)
    fu = FollowUp.objects.get(lead=lead)
    assert fu.notes == "Call Ravi" and fu.assigned_to == agent
    assert Notification.objects.filter(recipient=agent, title="New hot lead Ravi Kumar").exists()


def test_sms_skips_dnd_leads(no_real_sends):
    wf = _wf(repeat=True, steps=[{"type": "send_sms", "message": "Hi {name}"}])
    lead = _lead(is_dnd=True)
    run = fire(Trigger.LEAD_CREATED, lead, event_key=f"t:{lead.pk}", only=wf)[0]
    advance(run.pk)
    run.refresh_from_db()
    assert not no_real_sends["sms"].called
    assert run.log[0]["result"] == "skipped"


def test_whatsapp_not_connected_is_logged_not_raised(template, settings):
    settings.WHATSAPP_ALLOW_MOCK = False
    WhatsAppConfig.objects.update(is_active=False)
    wf = _wf(repeat=True, steps=[{"type": "send_whatsapp", "template": template.pk}, {"type": "add_note", "text": "after"}])
    lead = _lead()
    run = fire(Trigger.LEAD_CREATED, lead, event_key=f"t:{lead.pk}", only=wf)[0]
    advance(run.pk)
    run.refresh_from_db()
    assert run.status == RunStatus.COMPLETED and run.has_errors
    assert run.log[0]["result"] == "failed"
    assert LeadNote.objects.filter(lead=lead, content="after").exists()


def test_webhook_refuses_private_addresses():
    wf = _wf(repeat=True, steps=[{"type": "webhook", "url": "https://127.0.0.1/hook"}])
    lead = _lead()
    run = fire(Trigger.LEAD_CREATED, lead, event_key=f"t:{lead.pk}", only=wf)[0]
    with patch("requests.post") as posted:
        advance(run.pk)
    run.refresh_from_db()
    assert not posted.called and run.log[0]["result"] == "failed"


def test_webhook_posts_the_lead():
    wf = _wf(repeat=True, steps=[{"type": "webhook", "url": "https://hooks.example.com/x"}])
    lead = _lead()
    run = fire(Trigger.LEAD_CREATED, lead, event_key=f"t:{lead.pk}", only=wf)[0]
    with patch("apps.core.safe_fetch._check_public"), \
         patch("requests.post", return_value=MagicMock(status_code=200)) as posted:
        advance(run.pk)
    body = posted.call_args.kwargs["json"]
    assert body["lead"]["phone"] == lead.phone and body["workflow"]["name"] == "WF"


def test_switching_a_workflow_off_stops_waiting_runs():
    wf = _wf(repeat=True, steps=[{"type": "wait", "amount": 1, "unit": "minutes"}, {"type": "add_note", "text": "x"}])
    lead = _lead()
    run = fire(Trigger.LEAD_CREATED, lead, event_key=f"t:{lead.pk}", only=wf)[0]
    advance(run.pk)
    Workflow.objects.filter(pk=wf.pk).update(is_active=False)
    WorkflowRun.objects.filter(pk=run.pk).update(next_run_at=timezone.now())
    advance(run.pk)
    run.refresh_from_db()
    assert run.status == RunStatus.CANCELLED
    assert not LeadNote.objects.filter(lead=lead).exists()


# ============================================================
# API
# ============================================================

def _api(view, method, user, data=None, features=(FeatureKey.FOLLOW_UP_AUTOMATION,), **kw):
    request = getattr(APIRequestFactory(), method)("/x/", data or {}, format="json")
    force_authenticate(request, user=user)
    request.has_feature = lambda key: key in features
    return view.as_view()(request, **kw)


def test_create_validates_steps(admin, template):
    from apps.automation.views import WorkflowListCreateView

    bad = _api(WorkflowListCreateView, "post", admin, {
        "name": "Welcome", "trigger": "lead_created", "steps": [{"type": "send_whatsapp"}],
    })
    assert bad.status_code == 400 and "Step 1" in str(bad.data)

    ok = _api(WorkflowListCreateView, "post", admin, {
        "name": "Welcome", "trigger": "lead_created",
        "conditions": {"sources": ["website"]},
        "steps": [{"type": "send_whatsapp", "template": template.pk},
                  {"type": "wait", "amount": 1, "unit": "days"},
                  {"type": "create_followup", "in_hours": 2}],
    })
    assert ok.status_code == 201, ok.data
    wf = Workflow.objects.get(name="Welcome")
    assert wf.created_by == admin and not wf.is_active and len(wf.steps) == 3


def test_status_trigger_needs_a_status(admin):
    from apps.automation.views import WorkflowListCreateView

    response = _api(WorkflowListCreateView, "post", admin, {
        "name": "x", "trigger": "lead_status_changed", "trigger_config": {},
        "steps": [{"type": "add_note", "text": "x"}],
    })
    assert response.status_code == 400


def test_the_plan_gate_and_admin_only(admin, agent):
    from apps.automation.views import WorkflowListCreateView

    assert _api(WorkflowListCreateView, "get", admin, features=()).status_code in (402, 403)
    assert _api(WorkflowListCreateView, "get", agent).status_code == 403
    assert _api(WorkflowListCreateView, "get", admin).status_code == 200


def test_run_now_toggle_duplicate_and_runs(admin, django_capture_on_commit_callbacks):
    from apps.automation.views import (
        WorkflowDuplicateView, WorkflowRunListView, WorkflowRunNowView, WorkflowToggleView,
    )

    wf = _wf(is_active=False)
    lead = _lead()
    with django_capture_on_commit_callbacks(execute=True):
        response = _api(WorkflowRunNowView, "post", admin, {"lead_id": lead.pk}, pk=wf.pk)
    assert response.status_code == 201
    assert LeadNote.objects.filter(lead=lead).exists()   # manual runs work on a switched-off draft

    assert _api(WorkflowToggleView, "post", admin, {"is_active": True}, pk=wf.pk).data["is_active"]
    copy = _api(WorkflowDuplicateView, "post", admin, pk=wf.pk)
    assert copy.status_code == 201 and copy.data["is_active"] is False

    runs = _api(WorkflowRunListView, "get", admin, {"workflow": wf.pk})
    assert runs.data["count"] == 1 and runs.data["results"][0]["log"][0]["result"] == "done"


def test_options_list_what_the_editor_needs(admin, template):
    from apps.automation.views import WorkflowOptionsView

    data = _api(WorkflowOptionsView, "get", admin).data
    assert {t["key"] for t in data["triggers"]} >= {"lead_created", "whatsapp_received", "lead_inactive"}
    assert data["templates"][0]["name"] == "welcome"
    assert "send_whatsapp" in {a["key"] for a in data["actions"]}
