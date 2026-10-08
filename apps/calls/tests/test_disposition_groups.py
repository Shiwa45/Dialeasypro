"""
Call status, call outcome and lead status, kept apart (LEAD_DISPOSITION_PLAN.md).

* An outcome belongs to a group (connected / not connected) and must match the
  call status — it no longer overwrites it.
* A call outcome only moves a lead forward, except outcomes that close it.
* One open automatic follow-up per lead.
* Outcomes can be set on a call afterwards; a retried save is not saved twice.
* Every tenant's outcomes are upgraded in place.
"""
import importlib
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.calls import views as call_views
from apps.calls.disposition_defaults import DEFAULTS, upgrade_dispositions
from apps.calls.models import CallDisposition, CallLog
from apps.calls.services.outcomes import next_status
from apps.leads.models import FollowUp, Lead, LeadActivity
from apps.leads.views import LeadListCreateView, LeadStatusUpdateView

pytestmark = pytest.mark.django_db


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="asha@x.com", name="Asha", password="Pw@12345678")


@pytest.fixture
def bilal():
    return Agent.objects.create_agent(email="bilal@x.com", name="Bilal", password="Pw@12345678")


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(email="owner@x.com", name="Owner", password="Pw@12345678")


@pytest.fixture
def outcomes():
    upgrade_dispositions(CallDisposition)
    return {d.slug: d for d in CallDisposition.objects.all()}


def _lead(agent, status="new", phone="+919812300001"):
    return Lead.objects.create(name="Ravi", phone=phone, assigned_to=agent, status=status)


def _post_call(agent, **data):
    body = {"direction": "outbound", "phone_number": "9812300001", "duration_seconds": 40, **data}
    request = APIRequestFactory().post("/api/v1/calls/", body, format="json")
    force_authenticate(request, user=agent)
    response = call_views.CallLogListCreateView.as_view()(request)
    response.render()
    return response


def _call(agent, lead, disposition, connected=None, minutes_ago=0):
    if connected is None:
        connected = disposition.category == "connected"
    return CallLog.objects.create(
        agent=agent, lead=lead, phone_number=lead.phone, disposition=disposition,
        is_connected=connected, duration_seconds=30 if connected else 0,
        started_at=timezone.now() - timedelta(minutes=minutes_ago),
    )


# ---- The stage rules ---------------------------------------------------

@pytest.mark.parametrize("current,target,connected,expected", [
    ("new", "", False, "attempted"),
    ("new", "", True, "contacted"),
    ("attempted", "", True, "contacted"),
    ("interested", "", True, None),                     # never backwards to Contacted
    ("negotiation", "follow_up", True, None),           # the bug: Callback dropped Negotiation
    ("interested", "follow_up", True, "follow_up"),     # same stage: may switch
    ("follow_up", "interested", True, "interested"),
    ("contacted", "negotiation", True, "negotiation"),
    ("negotiation", "not_interested", True, "not_interested"),  # closing applies anywhere open
    ("attempted", "invalid", False, "invalid"),
    ("lost", "", False, None),                          # a closed lead stays closed...
    ("lost", "interested", True, "interested"),         # ...unless an answered call reopens it
    ("converted", "not_interested", True, None),        # settled for good
    ("duplicate", "interested", True, None),
])
def test_stage_rules(current, target, connected, expected):
    assert next_status(current, target, connected)[0] == expected


def test_a_reopen_is_reported():
    assert next_status("not_interested", "interested", True) == ("interested", True)


# ---- Logging a call ----------------------------------------------------

def test_an_unanswered_call_cannot_take_an_answered_outcome(asha, outcomes):
    lead = _lead(asha)

    r = _post_call(asha, lead=lead.pk, is_connected=False, duration_seconds=0,
                   disposition=outcomes["interested"].pk, client_call_id="c-1")

    assert r.status_code == 400
    assert "answered calls" in str(r.data)
    assert not CallLog.objects.exists()


def test_an_older_app_build_is_let_through_with_the_status_it_sent(asha, outcomes):
    lead = _lead(asha)

    r = _post_call(asha, lead=lead.pk, is_connected=False, duration_seconds=0,
                   disposition=outcomes["interested"].pk)

    assert r.status_code == 201, r.data
    call = CallLog.objects.get()
    assert call.is_connected is False, "the outcome no longer overwrites the call status"


def test_without_a_status_the_outcome_group_says_it(asha, outcomes):
    lead = _lead(asha)

    r = _post_call(asha, lead=lead.pk, disposition=outcomes["busy"].pk)

    assert r.status_code == 201, r.data
    assert CallLog.objects.get().is_connected is False


def test_an_outcome_is_required(asha, outcomes):
    lead = _lead(asha)

    r = _post_call(asha, lead=lead.pk, is_connected=True)

    assert r.status_code == 400
    assert "Choose the call outcome" in str(r.data)


def test_the_response_names_the_outcome(asha, outcomes):
    lead = _lead(asha)

    r = _post_call(asha, lead=lead.pk, is_connected=True, disposition=outcomes["interested"].pk,
                   client_call_id="c-2")

    assert r.status_code == 201
    assert r.data["disposition_name"] == "Interested"
    assert r.data["disposition_category"] == "connected"


def test_a_retried_save_returns_the_call_already_saved(asha, outcomes):
    lead = _lead(asha)
    body = dict(lead=lead.pk, is_connected=True, disposition=outcomes["interested"].pk, client_call_id="c-3")

    first = _post_call(asha, **body)
    again = _post_call(asha, **body)

    assert first.status_code == 201 and again.status_code == 200
    assert first.data["id"] == again.data["id"]
    assert CallLog.objects.count() == 1
    lead.refresh_from_db()
    assert lead.dial_attempts == 1


# ---- What a call does to the lead -------------------------------------

def test_a_callback_does_not_drop_a_lead_in_negotiation(asha, outcomes):
    lead = _lead(asha, status="negotiation")

    _call(asha, lead, outcomes["callback"])

    lead.refresh_from_db()
    assert lead.status == "negotiation"


def test_an_answered_call_without_a_status_rule_makes_the_lead_contacted(asha, outcomes):
    lead = _lead(asha, status="attempted")

    _call(asha, lead, outcomes["language_barrier"])

    lead.refresh_from_db()
    assert lead.status == "contacted"


def test_an_unanswered_call_makes_a_new_lead_attempted(asha, outcomes):
    lead = _lead(asha)

    _call(asha, lead, outcomes["switched_off"])

    lead.refresh_from_db()
    assert lead.status == "attempted"
    assert lead.has_been_worked


def test_a_lost_lead_reopened_by_a_call_is_logged(asha, outcomes):
    lead = _lead(asha, status="lost")

    _call(asha, lead, outcomes["busy"])
    lead.refresh_from_db()
    assert lead.status == "lost"

    _call(asha, lead, outcomes["interested"])
    lead.refresh_from_db()
    assert lead.status == "interested"
    assert LeadActivity.objects.filter(lead=lead, description__contains="reopened").exists()


def test_a_won_deal_is_not_touched(asha, outcomes):
    lead = _lead(asha, status="converted")

    _call(asha, lead, outcomes["not_interested"])

    lead.refresh_from_db()
    assert lead.status == "converted"


def test_dnd_marks_the_lead_and_closes_its_follow_ups(asha, outcomes):
    lead = _lead(asha, status="attempted")
    _call(asha, lead, outcomes["busy"], minutes_ago=5)
    assert FollowUp.objects.filter(lead=lead, is_auto=True, is_completed=False).count() == 1

    _call(asha, lead, outcomes["dnd_request"])

    lead.refresh_from_db()
    assert lead.is_dnd is True
    assert lead.status == "lost"
    assert not FollowUp.objects.filter(lead=lead, is_completed=False).exists()


def test_wrong_number_makes_the_lead_invalid_not_lost(asha, outcomes):
    lead = _lead(asha, status="attempted")

    _call(asha, lead, outcomes["wrong_person"])

    lead.refresh_from_db()
    assert lead.status == "invalid"


def test_only_one_automatic_follow_up_stays_open(asha, outcomes):
    lead = _lead(asha)

    _call(asha, lead, outcomes["busy"], minutes_ago=10)
    _call(asha, lead, outcomes["voicemail"])

    open_auto = FollowUp.objects.filter(lead=lead, is_auto=True, is_completed=False)
    assert open_auto.count() == 1
    assert "Voicemail" in open_auto.get().notes


@pytest.mark.parametrize("slug", ["busy", "callback", "voicemail"])
def test_busy_callback_and_voicemail_book_a_follow_up(asha, outcomes, slug):
    lead = _lead(asha)

    _call(asha, lead, outcomes[slug])

    assert FollowUp.objects.filter(lead=lead, is_auto=True, is_completed=False).count() == 1


@pytest.mark.parametrize("slug", [
    "interested", "send_details", "meeting_scheduled", "call_dropped", "language_barrier",
    "no_answer", "switched_off", "not_reachable", "rejected",
])
def test_other_outcomes_book_no_follow_up(asha, outcomes, slug):
    """Interested, Ringing, Switched off… used to book one for every lead."""
    lead = _lead(asha)

    _call(asha, lead, outcomes[slug])

    assert not FollowUp.objects.filter(lead=lead).exists()


def test_reaching_the_lead_retires_the_pending_retry(asha, outcomes):
    lead = _lead(asha)
    _call(asha, lead, outcomes["busy"], minutes_ago=10)
    assert FollowUp.objects.filter(lead=lead, is_auto=True, is_completed=False).count() == 1

    _call(asha, lead, outcomes["interested"])

    assert not FollowUp.objects.filter(lead=lead, is_completed=False).exists()


def test_the_agent_sets_the_call_back_time_with_the_call(asha, outcomes):
    lead = _lead(asha)
    when = (timezone.now() + timedelta(days=2)).replace(microsecond=0)

    r = _post_call(asha, lead=lead.pk, is_connected=True, disposition=outcomes["callback"].pk,
                   client_call_id="c-fu", followup_at=when.isoformat())

    assert r.status_code == 201, r.data
    fu = FollowUp.objects.get(lead=lead)
    assert fu.is_auto is False and fu.scheduled_at == when
    assert "Call back later" in fu.notes


def test_a_call_back_time_in_the_past_is_refused(asha, outcomes):
    lead = _lead(asha)

    r = _post_call(asha, lead=lead.pk, is_connected=True, disposition=outcomes["callback"].pk,
                   client_call_id="c-fu2", followup_at=(timezone.now() - timedelta(days=1)).isoformat())

    assert r.status_code == 400


def test_the_defaults_book_follow_ups_only_for_busy_callback_and_voicemail(outcomes):
    booking = set(CallDisposition.objects.exclude(auto_followup_hours=None).values_list("slug", flat=True))
    assert booking == {"busy", "callback", "voicemail"}


def test_an_admin_can_still_turn_it_on_for_another_outcome(admin, asha, outcomes):
    request = APIRequestFactory().patch(
        f"/api/v1/calls/dispositions/{outcomes['no_answer'].pk}/", {"auto_followup_hours": 3}, format="json")
    force_authenticate(request, user=admin)
    r = call_views.CallDispositionDetailView.as_view()(request, pk=outcomes["no_answer"].pk)
    assert r.status_code == 200, r.data

    lead = _lead(asha)
    _call(asha, lead, CallDisposition.objects.get(pk=outcomes["no_answer"].pk))
    assert FollowUp.objects.filter(lead=lead, is_auto=True).count() == 1


def test_the_migration_keeps_only_the_three(outcomes):
    migration = importlib.import_module("apps.calls.migrations.0009_auto_followup_busy_callback_voicemail")
    CallDisposition.objects.filter(slug__in=["interested", "no_answer"]).update(auto_followup_hours=24)
    CallDisposition.objects.filter(slug="callback").update(auto_followup_hours=None)
    CallDisposition.objects.filter(slug="busy").update(auto_followup_hours=3)
    custom = CallDisposition.objects.create(name="Site visit", slug="site-visit-m", auto_followup_hours=48)

    migration.forwards(django_apps, None)

    hours = dict(CallDisposition.objects.values_list("slug", "auto_followup_hours"))
    assert hours["interested"] is None and hours["no_answer"] is None
    assert hours["callback"] == 4, "turned back on with its default"
    assert hours["busy"] == 3, "a tenant's own hours are kept"
    assert hours[custom.slug] == 48, "outcomes a tenant added keep their setting"


def test_a_hand_booked_follow_up_is_left_alone(asha, outcomes):
    lead = _lead(asha)
    mine = FollowUp.objects.create(lead=lead, assigned_to=asha, followup_type="call",
                                   scheduled_at=timezone.now() + timedelta(days=2))

    _call(asha, lead, outcomes["callback"])

    mine.refresh_from_db()
    assert mine.is_completed is False


def test_the_lead_keeps_a_summary_of_its_calls(asha, outcomes):
    lead = _lead(asha)
    _call(asha, lead, outcomes["no_answer"], minutes_ago=20)
    _call(asha, lead, outcomes["busy"], minutes_ago=10)
    _call(asha, lead, outcomes["interested"])

    lead.refresh_from_db()
    assert lead.dial_attempts == 3
    assert lead.connected_calls == 1
    assert lead.contact_count == 1, "only answered calls are contacts"
    assert lead.last_disposition == outcomes["interested"]
    assert lead.last_call_connected is True
    assert lead.last_connected_at is not None


def test_one_activity_line_per_call(asha, outcomes):
    lead = _lead(asha)

    _call(asha, lead, outcomes["interested"])

    lines = LeadActivity.objects.filter(lead=lead)
    assert lines.count() == 1
    assert "Interested" in lines.get().description and "status Interested" in lines.get().description


# ---- Setting an outcome afterwards ------------------------------------

def _patch_outcome(user, call, **body):
    request = APIRequestFactory().patch(f"/api/v1/calls/{call.pk}/outcome/", body, format="json")
    force_authenticate(request, user=user)
    response = call_views.CallOutcomeView.as_view()(request, pk=call.pk)
    response.render()
    return response


def test_an_outcome_can_be_set_on_a_call_saved_without_one(asha, outcomes):
    lead = _lead(asha)
    call = CallLog.objects.create(agent=asha, lead=lead, phone_number=lead.phone)
    lead.refresh_from_db()
    assert lead.status == "attempted" and lead.dial_attempts == 1

    r = _patch_outcome(asha, call, disposition=outcomes["interested"].pk, is_connected=True, duration_seconds=50)

    assert r.status_code == 200, r.data
    assert r.data["disposition_name"] == "Interested"
    lead.refresh_from_db()
    assert lead.status == "interested"
    assert lead.dial_attempts == 1, "setting the outcome is not a second dial"
    assert lead.connected_calls == 1


def test_setting_an_outcome_checks_the_group(asha, outcomes):
    lead = _lead(asha)
    call = CallLog.objects.create(agent=asha, lead=lead, phone_number=lead.phone)

    r = _patch_outcome(asha, call, disposition=outcomes["busy"].pk, is_connected=True)

    assert r.status_code == 400


def test_only_the_caller_or_a_manager_sets_the_outcome(asha, bilal, admin, outcomes):
    lead = _lead(asha)
    lead.assigned_to = bilal
    lead.save()
    call = CallLog.objects.create(agent=asha, lead=lead, phone_number=lead.phone)

    assert _patch_outcome(bilal, call, disposition=outcomes["busy"].pk).status_code in (403, 404)
    assert _patch_outcome(admin, call, disposition=outcomes["busy"].pk).status_code == 200


def test_calls_waiting_for_an_outcome_can_be_listed(admin, asha, outcomes):
    lead = _lead(asha)
    CallLog.objects.create(agent=asha, lead=lead, phone_number=lead.phone)
    _call(asha, lead, outcomes["busy"])

    request = APIRequestFactory().get("/api/v1/calls/?disposition=none")
    force_authenticate(request, user=admin)
    r = call_views.CallLogListCreateView.as_view()(request)

    assert r.data["count"] == 1


def test_a_call_remembers_who_was_called(asha, outcomes):
    lead = _lead(asha)
    call = _call(asha, lead, outcomes["busy"])
    CallLog.objects.filter(pk=call.pk).update(lead=None)

    request = APIRequestFactory().get("/api/v1/calls/")
    force_authenticate(request, user=asha)
    from apps.calls.serializers import CallLogSerializer

    assert CallLogSerializer(CallLog.objects.get(pk=call.pk)).data["lead_name"] == "Ravi"


# ---- Outcome settings --------------------------------------------------

def test_a_built_in_outcome_cannot_be_deleted_or_moved(admin, outcomes):
    busy = outcomes["busy"]

    request = APIRequestFactory().delete(f"/api/v1/calls/dispositions/{busy.pk}/")
    force_authenticate(request, user=admin)
    r = call_views.CallDispositionDetailView.as_view()(request, pk=busy.pk)
    assert r.status_code == 400

    request = APIRequestFactory().patch(f"/api/v1/calls/dispositions/{busy.pk}/", {"category": "connected"},
                                        format="json")
    force_authenticate(request, user=admin)
    r = call_views.CallDispositionDetailView.as_view()(request, pk=busy.pk)
    assert r.status_code == 400


def test_the_list_can_be_asked_for_one_group(asha, outcomes):
    request = APIRequestFactory().get("/api/v1/calls/dispositions/?category=not_connected")
    force_authenticate(request, user=asha)
    r = call_views.CallDispositionListView.as_view()(request)

    assert r.data and all(d["category"] == "not_connected" for d in r.data)
    assert all(d["marks_connected"] is False for d in r.data)


# ---- Upgrading a tenant's outcomes --------------------------------------

OLD_SET = [
    ("connected_interested", "Connected – Interested", True, "interested", 24, True, 1),
    ("connected_callback", "Connected – Callback Requested", True, "follow_up", 4, True, 2),
    ("connected_not_interested", "Connected – Not Interested", True, "not_interested", None, False, 3),
    ("connected_purchased", "Connected – Already Purchased", True, "", None, False, 4),
    ("not_reachable", "Not Reachable", False, "", 6, False, 5),
    ("busy", "Busy", False, "", 2, False, 6),
    ("switched_off", "Switched Off", False, "", 12, False, 7),
    ("wrong_number", "Wrong Number", True, "", None, False, 8),
    ("dnd", "Do Not Disturb", None, "", None, False, 9),
    ("voicemail", "Voicemail Left", False, "", 24, False, 10),
]


def _old_tenant():
    for slug, name, marks, status, hours, positive, order in OLD_SET:
        CallDisposition.objects.create(slug=slug, name=name, lead_status=status, auto_followup_hours=hours,
                                       is_positive=positive, sort_order=order)
        CallDisposition.objects.filter(slug=slug).update(marks_connected=marks, category="connected")


def test_an_existing_tenant_is_upgraded_in_place(asha):
    _old_tenant()
    # The tenant had changed one default and added their own outcomes.
    CallDisposition.objects.filter(slug="busy").update(auto_followup_hours=3)
    CallDisposition.objects.create(slug="site-visit", name="Site visit booked")
    CallDisposition.objects.create(slug="rnr", name="RNR")
    # As they stood before the upgrade: no group yet, answered/not unknown.
    CallDisposition.objects.filter(slug__in=["site-visit", "rnr"]).update(marks_connected=None)
    lead = _lead(asha)
    old_interested = CallDisposition.objects.get(slug="connected_interested")
    call = _call(asha, lead, old_interested)

    upgrade_dispositions(CallDisposition)

    by_slug = {d.slug: d for d in CallDisposition.objects.all()}
    assert set(r[0] for r in DEFAULTS) <= set(by_slug)
    assert "connected_interested" not in by_slug
    assert by_slug["interested"].pk == old_interested.pk, "renamed in place"
    assert CallLog.objects.get(pk=call.pk).disposition.slug == "interested", "calls keep their outcome"
    assert by_slug["interested"].name == "Interested"
    assert by_slug["busy"].auto_followup_hours == 3, "a value the tenant changed is kept"
    assert by_slug["busy"].category == "not_connected"
    assert by_slug["wrong_person"].lead_status == "invalid"
    assert by_slug["dnd_request"].sets_dnd is True and by_slug["dnd_request"].category == "connected"
    assert by_slug["site-visit"].category == "connected" and not by_slug["site-visit"].is_system
    assert by_slug["rnr"].category == "not_connected"

    again = upgrade_dispositions(CallDisposition)
    assert again == {"renamed": 0, "created": 0}


def test_a_new_tenant_gets_the_full_set():
    result = upgrade_dispositions(CallDisposition)

    assert result["created"] == len(DEFAULTS)
    assert CallDisposition.objects.filter(category="connected").count() == 11
    assert CallDisposition.objects.filter(category="not_connected").count() == 7


# ---- Lead status by hand -------------------------------------------------

def _set_status(user, lead, **body):
    request = APIRequestFactory().patch(f"/api/v1/leads/{lead.pk}/status/", body, format="json")
    force_authenticate(request, user=user)
    response = LeadStatusUpdateView.as_view()(request, pk=lead.pk)
    response.render()
    return response


def test_lost_needs_a_reason(admin, asha):
    lead = _lead(asha)

    assert _set_status(admin, lead, status="lost").status_code == 400
    r = _set_status(admin, lead, status="lost", reason="Bought from a competitor")

    assert r.status_code == 200
    assert LeadActivity.objects.filter(lead=lead, description__contains="Bought from a competitor").exists()


def test_an_agent_needs_a_note_to_mark_a_sale(asha):
    lead = _lead(asha)

    assert _set_status(asha, lead, status="converted").status_code == 400
    assert _set_status(asha, lead, status="converted", reason="Order #551").status_code == 200


def test_a_manager_can_mark_a_sale_without_one(admin, asha):
    lead = _lead(asha)

    assert _set_status(admin, lead, status="converted").status_code == 200


# ---- Leads list and reports -----------------------------------------------

def _list(user, query):
    request = APIRequestFactory().get(f"/api/v1/leads/?{query}")
    force_authenticate(request, user=user)
    return LeadListCreateView.as_view()(request)


def test_leads_filter_by_last_outcome(admin, asha, outcomes):
    reached = _lead(asha, phone="+919812300011")
    never = _lead(asha, phone="+919812300012")
    _call(asha, reached, outcomes["interested"])
    _call(asha, never, outcomes["busy"])

    r = _list(admin, f"last_disposition={outcomes['interested'].pk}")
    assert [x["id"] for x in r.data["results"]] == [reached.pk]
    assert r.data["results"][0]["last_disposition_name"] == "Interested"

    r = _list(admin, "never_connected=true")
    assert [x["id"] for x in r.data["results"]] == [never.pk]


def test_the_pipeline_counts_every_lead(admin, asha):
    from apps.reports.views import ConversionFunnelView

    cache.clear()
    for i, status in enumerate(["new", "follow_up", "not_interested", "invalid"]):
        _lead(asha, status=status, phone=f"+91981230010{i}")
    request = APIRequestFactory().get("/api/v1/reports/conversion-funnel/?current=true")
    force_authenticate(request, user=admin)
    request.has_feature = lambda key: True
    r = ConversionFunnelView.as_view()(request)

    pipeline = {row["status"]: row["count"] for row in r.data["pipeline"]}
    assert sum(pipeline.values()) == r.data["total"] == 4
    assert pipeline["follow_up"] == 1 and pipeline["not_interested"] == 1 and pipeline["invalid"] == 1


def test_outcomes_are_credited_to_the_agent_who_called(admin, asha, bilal, outcomes):
    from apps.reports.views import AgentOutcomeReportView

    cache.clear()
    theirs = _lead(bilal)  # Bilal owns it; Asha calls it.
    _call(asha, theirs, outcomes["interested"])
    _call(asha, theirs, outcomes["busy"])
    today = timezone.localdate().isoformat()
    request = APIRequestFactory().get(f"/api/v1/reports/agent-outcomes/?date_from={today}&date_to={today}")
    force_authenticate(request, user=admin)
    request.has_feature = lambda key: True
    r = AgentOutcomeReportView.as_view()(request)

    row = next(a for a in r.data["agents"] if a["agent_id"] == asha.pk)
    assert row["dials"] == 2 and row["connected"] == 1
    assert row["outcomes"][str(outcomes["interested"].pk)] == 1
    assert row["outcomes"][str(outcomes["busy"].pk)] == 1
    assert not any(a["agent_id"] == bilal.pk for a in r.data["agents"])


# ---- The lead backfill migration ------------------------------------------

def test_the_backfill_summarises_existing_leads(asha, outcomes):
    backfill = importlib.import_module("apps.leads.migrations.0010_backfill_call_summary")
    lead = _lead(asha)
    CallLog.objects.bulk_create([
        CallLog(agent=asha, lead=lead, phone_number=lead.phone, disposition=outcomes["busy"],
                started_at=timezone.now() - timedelta(hours=1)),
        CallLog(agent=asha, lead=lead, phone_number=lead.phone, disposition=outcomes["language_barrier"],
                is_connected=True, started_at=timezone.now()),
    ])
    Lead.objects.filter(pk=lead.pk).update(status="attempted", contact_count=7)
    for _ in range(2):
        FollowUp.objects.create(lead=lead, assigned_to=asha, followup_type="call", is_auto=True,
                                scheduled_at=timezone.now() + timedelta(hours=2))

    backfill.backfill(django_apps, None)

    lead.refresh_from_db()
    assert lead.dial_attempts == 2 and lead.connected_calls == 1 and lead.contact_count == 1
    assert lead.status == "contacted"
    assert lead.last_disposition == outcomes["language_barrier"]
    assert FollowUp.objects.filter(lead=lead, is_auto=True, is_completed=False).count() == 1
