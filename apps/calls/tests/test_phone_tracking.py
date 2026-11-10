"""
Phone call tracking: the app sends the phone's call log; the company admin
switches it on for the company and off per agent.
"""
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.authentication.serializers import AgentProfileSerializer
from apps.calls.models import CallDisposition, CallLog, CallRecording
from apps.calls.views import CallLogListCreateView, CallTrackingSettingsView, PhoneCallSyncView
from apps.core.constants import LeadStatus
from apps.leads.models import Lead
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    t = Tenant.objects.get(schema_name=connection.schema_name)
    Tenant.objects.filter(pk=t.pk).update(call_tracking_enabled=True)
    return t


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="asha@pt.t", name="Asha", password="Pw@12345678")


@pytest.fixture
def boss():
    return Agent.objects.create_tenant_admin(email="boss@pt.t", name="Boss", password="Pw@12345678")


@pytest.fixture
def answered():
    return CallDisposition.objects.create(name="Interested", slug="interested-pt", category="connected")


def _ms(dt):
    return int(dt.timestamp() * 1000)


def _sync(agent, calls):
    request = APIRequestFactory().post("/api/v1/calls/sync/", {"calls": calls}, format="json")
    force_authenticate(request, user=agent)
    r = PhoneCallSyncView.as_view()(request)
    r.render()
    return r


def _entry(device_id="101", number="9812300001", kind="outgoing", at=None, duration=42):
    at = at or timezone.now() - timedelta(minutes=5)
    return {"device_id": device_id, "number": number, "type": kind,
            "started_at": _ms(at), "duration_seconds": duration}


# ---- Switches ------------------------------------------------------------

def test_off_by_default_for_the_company(asha):
    Tenant.objects.filter(schema_name=connection.schema_name).update(call_tracking_enabled=False)
    r = _sync(asha, [_entry()])
    assert r.status_code == 403 and r.data["error"] == "call_tracking_off"
    assert AgentProfileSerializer(asha).data["call_tracking"] is False


def test_on_for_the_company_covers_agents(tenant, asha):
    assert AgentProfileSerializer(asha).data["call_tracking"] is True


def test_an_agent_switched_off_is_not_tracked(tenant, asha):
    Agent.objects.filter(pk=asha.pk).update(call_tracking_enabled=False)
    asha.refresh_from_db()
    assert AgentProfileSerializer(asha).data["call_tracking"] is False
    assert _sync(asha, [_entry()]).status_code == 403


def test_admin_switches_company_and_agents(tenant, boss, asha):
    Tenant.objects.filter(pk=tenant.pk).update(call_tracking_enabled=False)
    request = APIRequestFactory().patch(
        "/api/v1/calls/tracking/", {"enabled": True, "agents": {str(asha.pk): False}}, format="json")
    force_authenticate(request, user=boss)
    r = CallTrackingSettingsView.as_view()(request)
    assert r.status_code == 200, r.data
    assert r.data["enabled"] is True
    assert Tenant.objects.get(pk=tenant.pk).call_tracking_enabled is True
    asha.refresh_from_db()
    assert asha.call_tracking_enabled is False


def test_agents_cannot_change_the_switch(tenant, asha):
    request = APIRequestFactory().patch("/api/v1/calls/tracking/", {"enabled": False}, format="json")
    force_authenticate(request, user=asha)
    assert CallTrackingSettingsView.as_view()(request).status_code == 403


# ---- Sync ----------------------------------------------------------------

def test_outgoing_and_incoming_calls_are_saved_on_the_lead(tenant, asha):
    lead = Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=asha)
    r = _sync(asha, [
        _entry("1", kind="outgoing", duration=30),
        _entry("2", kind="incoming", duration=0, at=timezone.now() - timedelta(minutes=30)),
    ])
    assert r.status_code == 200, r.data
    out, missed = r.data["results"]
    assert out["created"] and out["needs_recording"] is True
    assert missed["created"] and missed["needs_recording"] is False
    call = CallLog.objects.get(pk=out["call_id"])
    assert call.lead_id == lead.pk and call.direction == "outbound" and call.is_connected
    assert call.duration_seconds == 30
    assert call.provider_meta["source"] == "phone_call_log"
    m = CallLog.objects.get(pk=missed["call_id"])
    assert m.direction == "missed" and not m.is_connected


def test_a_missed_incoming_call_does_not_move_the_lead(tenant, asha):
    lead = Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=asha)
    _sync(asha, [_entry("2", kind="missed", duration=0)])
    lead.refresh_from_db()
    assert lead.status == LeadStatus.NEW


def test_a_retry_returns_the_same_calls(tenant, asha):
    e = _entry("7")
    first = _sync(asha, [e]).data["results"][0]
    again = _sync(asha, [e]).data["results"][0]
    assert first["call_id"] == again["call_id"] and again["created"] is False
    assert CallLog.objects.filter(agent=asha).count() == 1


def test_numbers_of_other_peoples_leads_are_not_attached(tenant, asha):
    bilal = Agent.objects.create_agent(email="bilal@pt.t", name="Bilal", password="Pw@12345678")
    Lead.objects.create(name="Not hers", phone="+919812300009", assigned_to=bilal)
    res = _sync(asha, [_entry("9", number="9812300009")]).data["results"][0]
    assert CallLog.objects.get(pk=res["call_id"]).lead_id is None


def test_unknown_numbers_are_saved_without_a_lead(tenant, asha):
    res = _sync(asha, [_entry("5", number="+91 98765 43210")]).data["results"][0]
    call = CallLog.objects.get(pk=res["call_id"])
    assert call.lead_id is None and call.phone_number == "+919876543210"


def test_bad_entries_are_skipped_not_fatal(tenant, asha):
    r = _sync(asha, [
        _entry("1"),
        {"device_id": "2", "number": "", "type": "incoming", "started_at": _ms(timezone.now())},
        {"device_id": "3", "number": "9812300001", "type": "voicemail", "started_at": _ms(timezone.now())},
        _entry("4", at=timezone.now() - timedelta(days=30)),
    ])
    assert r.status_code == 200
    assert len(r.data["results"]) == 1
    assert {s["device_id"] for s in r.data["skipped"]} == {"2", "3", "4"}


def test_a_call_with_a_recording_needs_none(tenant, asha):
    res = _sync(asha, [_entry("1")]).data["results"][0]
    CallRecording.objects.create(call_id=res["call_id"], cloud_url="https://example.com/a.mp3")
    again = _sync(asha, [_entry("1")]).data["results"][0]
    assert again["needs_recording"] is False


# ---- One call, one row ----------------------------------------------------

def _app_save(agent, disposition, at, **extra):
    body = {"direction": "outbound", "phone_number": "9812300001", "duration_seconds": 40,
            "is_connected": True, "disposition": disposition.pk,
            "started_at": at.isoformat(), "ended_at": (at + timedelta(seconds=40)).isoformat(),
            "client_call_id": "app-1", **extra}
    request = APIRequestFactory().post("/api/v1/calls/", body, format="json")
    force_authenticate(request, user=agent)
    r = CallLogListCreateView.as_view()(request)
    r.render()
    return r


def test_the_phone_entry_finds_the_call_the_app_saved(tenant, asha, answered):
    lead = Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=asha)
    at = timezone.now() - timedelta(minutes=10)
    app = _app_save(asha, answered, at, lead=lead.pk)
    assert app.status_code == 201, app.data
    res = _sync(asha, [_entry("1", at=at + timedelta(seconds=6), duration=38)]).data["results"][0]
    assert res["merged"] is True and res["call_id"] == str(app.data["id"])
    assert CallLog.objects.filter(agent=asha).count() == 1


def test_the_app_completes_the_phone_entry(tenant, asha, answered):
    lead = Lead.objects.create(name="Ravi", phone="+919812300001", assigned_to=asha)
    at = timezone.now() - timedelta(minutes=10)
    res = _sync(asha, [_entry("1", at=at + timedelta(seconds=5), duration=38)]).data["results"][0]
    app = _app_save(asha, answered, at, lead=lead.pk, notes="Wants a call back")
    assert app.status_code == 201, app.data
    assert str(app.data["id"]) == res["call_id"]
    call = CallLog.objects.get(pk=res["call_id"])
    assert call.disposition_id == answered.pk and call.notes == "Wants a call back"
    assert call.duration_seconds == 40 and call.client_call_id == "app-1"
    assert CallLog.objects.filter(agent=asha).count() == 1
    # A retry of the app's save still finds it.
    assert _app_save(asha, answered, at, lead=lead.pk).status_code == 200


def test_calls_far_apart_are_not_merged(tenant, asha, answered):
    at = timezone.now() - timedelta(hours=2)
    _app_save(asha, answered, at)
    res = _sync(asha, [_entry("1", at=at + timedelta(minutes=30))]).data["results"][0]
    assert res["created"] is True
    assert CallLog.objects.filter(agent=asha).count() == 2
