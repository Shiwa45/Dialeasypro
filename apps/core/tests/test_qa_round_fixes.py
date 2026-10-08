"""
Regressions for the bugs found testing the live site (QA_BUG_REPORT.md).
Each test names the report item it pins.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent, AgentLoginSession
from apps.core.constants import AgentRole

pytestmark = pytest.mark.django_db
factory = APIRequestFactory()
PW = "Pw@12345678"


def _call(view, method, path, user, data=None, **kwargs):
    request = getattr(factory, method)(path, data, format="json")
    if user is not None:
        force_authenticate(request, user=user)
    request.has_feature = lambda key: True
    response = view.as_view()(request, **kwargs)
    response.render()
    return response


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(email="qa-admin@x.com", name="Admin", password=PW)


@pytest.fixture
def asha():
    return Agent.objects.create_agent(email="qa-asha@x.com", name="Asha Rao", password=PW)


# ---------------------------------------------------------------------------
# H2 / H3 — WhatsApp: nothing "sent" without a connection; variables filled
# ---------------------------------------------------------------------------

def _template(body="Hi {{1}}, call {{2}}.", mapping=None, status="approved"):
    from apps.communications.models import WhatsAppTemplate
    return WhatsAppTemplate.objects.create(
        name=f"tpl_{WhatsAppTemplateCounter.next()}", body_text=body, status=status,
        variable_mapping=mapping or {},
    )


class WhatsAppTemplateCounter:
    n = 0

    @classmethod
    def next(cls):
        cls.n += 1
        return cls.n


def _lead(phone="+919812300501", owner=None, **kw):
    from apps.leads.models import Lead
    return Lead.objects.create(name=kw.pop("name", "Rohan Mishra"), phone=phone, assigned_to=owner, **kw)


def test_template_values_fill_from_the_mapping(asha):
    from apps.communications.whatsapp_ready import template_values
    lead = _lead(owner=asha, city="Pune")
    tpl = _template("Hi {{1}} from {{3}}, {{2}} will call.", {"1": "first_name", "2": "agent_name", "3": "city"})
    assert template_values(tpl, lead) == ["Rohan", "Asha Rao", "Pune"]
    assert tpl.render(lead) == "Hi Rohan from Pune, Asha Rao will call."


def test_unmapped_placeholders_are_reported():
    from apps.communications.whatsapp_ready import unmapped_placeholders
    tpl = _template("Hi {{1}} {{2}}", {"1": "name"})
    assert unmapped_placeholders(tpl) == [2]
    tpl.variable_mapping = {"1": "name", "2": "nonsense"}
    assert unmapped_placeholders(tpl) == [2]


def test_template_serializer_validates_mapping():
    from apps.communications.serializers import WhatsAppTemplateSerializer
    ok = WhatsAppTemplateSerializer(data={"name": "a1", "body_text": "Hi {{1}}", "variable_mapping": {"1": "name"}})
    assert ok.is_valid(), ok.errors
    bad = WhatsAppTemplateSerializer(data={"name": "a2", "body_text": "Hi {{1}}", "variable_mapping": {"1": "salary"}})
    assert not bad.is_valid()
    custom = WhatsAppTemplateSerializer(data={"name": "a3", "body_text": "Hi {{1}}", "variable_mapping": {"1": "custom:company_name"}})
    assert custom.is_valid(), custom.errors


def test_a_campaign_cannot_be_built_on_an_unmapped_template(admin):
    from apps.communications.serializers import BulkCampaignCreateSerializer
    tpl = _template("Hi {{1}}", {})
    s = BulkCampaignCreateSerializer(data={"name": "x", "channel": "whatsapp", "template": tpl.pk, "audience_filters": {}})
    assert not s.is_valid()
    assert "template" in s.errors


def test_launch_is_refused_when_whatsapp_is_not_connected(admin):
    from apps.communications.models import BulkCampaign
    from apps.communications.views import BulkCampaignLaunchView
    tpl = _template("Hi {{1}}", {"1": "name"})
    campaign = BulkCampaign.objects.create(name="D", channel="whatsapp", status="draft",
                                           template=tpl, audience_filters={})
    with patch("apps.communications.tasks.send_bulk_whatsapp_campaign.apply_async") as queued:
        response = _call(BulkCampaignLaunchView, "post", "/x/", admin, pk=campaign.pk)
    assert response.status_code == 400
    assert response.data["error"] == "whatsapp_not_connected"
    queued.assert_not_called()
    campaign.refresh_from_db()
    assert campaign.status == "draft"


def test_launch_is_refused_for_unmapped_variables_even_when_connected(admin, settings):
    settings.WHATSAPP_ALLOW_MOCK = True
    from apps.communications.models import BulkCampaign
    from apps.communications.views import BulkCampaignLaunchView
    tpl = _template("Hi {{1}}", {})
    campaign = BulkCampaign.objects.create(name="D2", channel="whatsapp", status="draft",
                                           template=tpl, audience_filters={})
    response = _call(BulkCampaignLaunchView, "post", "/x/", admin, pk=campaign.pk)
    assert response.status_code == 400
    assert response.data["error"] == "campaign_not_ready"


def test_a_chunk_without_a_provider_fails_recipients_instead_of_sending(asha):
    from apps.communications.models import BulkCampaign, CampaignRecipient
    from apps.communications.tasks import send_whatsapp_chunk
    tpl = _template("Hi {{1}}", {"1": "name"})
    campaign = BulkCampaign.objects.create(name="D3", channel="whatsapp", status="running",
                                           template=tpl, audience_filters={})
    lead = _lead()
    r = CampaignRecipient.objects.create(campaign=campaign, lead=lead, phone=lead.phone)
    send_whatsapp_chunk.apply(args=["test_tenant", str(campaign.pk), [r.pk]])
    r.refresh_from_db(); campaign.refresh_from_db()
    assert r.status == "failed"
    assert "not connected" in r.error_message
    assert campaign.sent_count == 0 and campaign.failed_count == 1


def test_a_connected_send_fills_variables_and_counts_usage(asha, settings):
    settings.WHATSAPP_ALLOW_MOCK = True
    from apps.communications.models import BulkCampaign, CampaignRecipient, WhatsAppMessage
    from apps.communications.tasks import send_whatsapp_chunk
    tpl = _template("Hi {{1}}", {"1": "first_name"})
    campaign = BulkCampaign.objects.create(name="D4", channel="whatsapp", status="running",
                                           template=tpl, audience_filters={})
    lead = _lead()
    r = CampaignRecipient.objects.create(campaign=campaign, lead=lead, phone=lead.phone)
    provider = MagicMock()
    provider.send_template.return_value = "wamid.1"
    with patch("apps.communications.tasks._get_whatsapp_provider", return_value=(provider, "interakt")):
        send_whatsapp_chunk.apply(args=["test_tenant", str(campaign.pk), [r.pk]])
    provider.send_template.assert_called_once()
    kwargs = provider.send_template.call_args.kwargs
    assert kwargs["variables"] == ["Rohan"]
    assert kwargs["template_id"] == tpl.name  # provider name falls back to the template name
    assert WhatsAppMessage.objects.get(lead=lead).content == "Hi Rohan"
    tpl.refresh_from_db()
    assert tpl.usage_count == 1


def test_single_send_refused_without_connection(asha):
    from apps.communications.views import SendWhatsAppView
    lead = _lead(owner=asha)
    with patch("apps.communications.tasks.send_single_whatsapp.apply_async") as queued:
        response = _call(SendWhatsAppView, "post", "/x/", asha, {"lead_id": lead.pk, "message": "hello"})
    assert response.status_code == 400
    assert response.data["error"] == "whatsapp_not_connected"
    queued.assert_not_called()


def test_campaign_recipients_list(admin):
    from apps.communications.models import BulkCampaign, CampaignRecipient
    from apps.communications.views import CampaignRecipientListView
    campaign = BulkCampaign.objects.create(name="D5", channel="sms", sms_text="x", status="completed", audience_filters={})
    lead = _lead()
    CampaignRecipient.objects.create(campaign=campaign, lead=lead, phone=lead.phone, status="failed", error_message="nope")
    response = _call(CampaignRecipientListView, "get", "/x/?status=failed", admin, pk=campaign.pk)
    assert response.status_code == 200
    assert response.data["results"][0]["error_message"] == "nope"


# ---------------------------------------------------------------------------
# H4 — calls: outcome decides "connected"; duration from timestamps/recording
# ---------------------------------------------------------------------------

def _disposition(slug, marks):
    from apps.calls.models import CallDisposition
    category = "not_connected" if marks is False else "connected"
    return CallDisposition.objects.create(name=slug.title(), slug=slug, category=category)


def test_an_outcome_no_longer_overwrites_the_call_status(asha):
    """The call status is a fact from the phone; the outcome must match it
    instead of overwriting it (see calls/services/outcomes.py)."""
    from apps.calls.models import CallLog
    call = CallLog.objects.create(agent=asha, phone_number="+919812300777", is_connected=True,
                                  disposition=_disposition("switched-off-x", False))
    call.refresh_from_db()
    assert call.is_connected is True


def test_an_answered_call_takes_its_duration_from_timestamps(asha):
    from apps.calls.models import CallLog
    start = timezone.now() - timedelta(minutes=5)
    call = CallLog.objects.create(agent=asha, phone_number="+919812300778", is_connected=True,
                                  started_at=start, ended_at=start + timedelta(seconds=95),
                                  duration_seconds=0, disposition=_disposition("conn-int-x", True))
    call.refresh_from_db()
    assert call.is_connected is True
    assert call.duration_seconds == 95


def test_a_neutral_outcome_leaves_the_dialer_answer(asha):
    from apps.calls.models import CallLog
    call = CallLog.objects.create(agent=asha, phone_number="+919812300779", is_connected=True,
                                  disposition=_disposition("dnd-x", None))
    assert CallLog.objects.get(pk=call.pk).is_connected is True


def test_recording_length_fills_a_zero_duration(asha):
    from apps.calls.models import CallLog, CallRecording
    from apps.calls.views import _fill_duration_from_recording
    call = CallLog.objects.create(agent=asha, phone_number="+919812300780", is_connected=True)
    rec = CallRecording.objects.create(call=call, duration_seconds=42)
    _fill_duration_from_recording(call, rec)
    call.refresh_from_db()
    assert call.duration_seconds == 42


def test_backfill_guesses_answered_from_names():
    import importlib
    m = importlib.import_module("apps.calls.migrations.0006_disposition_marks_connected")
    assert m.guess("connected_not_interested", "Connected – Not Interested") is True
    assert m.guess("switched_off", "Switched Off") is False
    assert m.guess("not_reachable", "Not Reachable") is False
    assert m.guess("dnd", "Do Not Disturb") is None


# ---------------------------------------------------------------------------
# H5 — working days default to Mon–Sat; Sunday is a week off
# ---------------------------------------------------------------------------

def test_new_agents_work_monday_to_saturday():
    a = Agent.objects.create_agent(email="wd@x.com", name="WD", password=PW)
    assert a.working_days == [0, 1, 2, 3, 4, 5]


def test_an_empty_schedule_still_gives_sunday_off():
    from apps.hrms.constants import AttendanceStatus
    from apps.hrms.models import Employee
    from apps.hrms.services.attendance import day_off_status
    agent = Agent.objects.create_agent(email="wd2@x.com", name="WD2", password=PW)
    Agent.objects.filter(pk=agent.pk).update(working_days=[])
    agent.refresh_from_db()
    emp = Employee.objects.create(agent=agent, employee_code="WD-2", date_of_joining=date(2026, 1, 1))
    sunday = date(2026, 10, 4)
    assert sunday.weekday() == 6
    assert day_off_status(sunday, emp, holidays=set()) == AttendanceStatus.WEEK_OFF
    assert day_off_status(sunday - timedelta(days=1), emp, holidays=set()) is None


def test_draft_payslip_follows_attendance(django_capture_on_commit_callbacks):
    from apps.hrms.constants import AttendanceStatus
    from apps.hrms.models import Attendance, Employee, Payslip, SalaryStructure
    from apps.hrms.services.payroll import build_payslip
    agent = Agent.objects.create_agent(email="pay@x.com", name="Pay", password=PW)
    emp = Employee.objects.create(agent=agent, employee_code="PAY-9", date_of_joining=date(2025, 1, 1))
    SalaryStructure.objects.create(employee=emp, effective_from=date(2025, 1, 1),
                                   basic=Decimal("31000.00"), hra=Decimal("0"))
    month = date(2026, 3, 1)
    build_payslip(emp, month)
    before = Payslip.objects.get(employee=emp, period_month=month).payable_days
    with django_capture_on_commit_callbacks(execute=True):
        Attendance.objects.create(employee=emp, date=date(2026, 3, 3), status=AttendanceStatus.ABSENT)
    after = Payslip.objects.get(employee=emp, period_month=month).payable_days
    assert after == before - 1


# ---------------------------------------------------------------------------
# M1 / working days on the agent form
# ---------------------------------------------------------------------------

def test_admin_can_change_an_agents_email_and_working_days(admin, asha):
    from apps.authentication.views import AgentDetailAPIView
    response = _call(AgentDetailAPIView, "patch", "/x/", admin,
                     {"email": "Asha.New@X.com", "working_days": [0, 1, 2, 3, 4]}, pk=asha.pk)
    assert response.status_code == 200, response.data
    asha.refresh_from_db()
    assert asha.email == "asha.new@x.com"
    assert asha.working_days == [0, 1, 2, 3, 4]


def test_email_must_stay_unique(admin, asha):
    from apps.authentication.views import AgentDetailAPIView
    response = _call(AgentDetailAPIView, "patch", "/x/", admin, {"email": admin.email}, pk=asha.pk)
    assert response.status_code == 400


def test_working_days_are_validated(admin, asha):
    from apps.authentication.views import AgentDetailAPIView
    response = _call(AgentDetailAPIView, "patch", "/x/", admin, {"working_days": [7]}, pk=asha.pk)
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# M3 — profile shows login count
# ---------------------------------------------------------------------------

def test_profile_includes_login_count(asha):
    from apps.authentication.views import AgentProfileAPIView
    response = _call(AgentProfileAPIView, "get", "/x/", asha)
    assert "total_login_count" in response.data


# ---------------------------------------------------------------------------
# H7 — login report keeps deactivated agents' history; web sign-ins count
# ---------------------------------------------------------------------------

def test_login_report_keeps_a_deactivated_agent_with_calls(asha, admin):
    from apps.calls.models import CallLog
    from apps.reports.login_report import build_login_report
    today = timezone.localdate()
    CallLog.objects.create(agent=asha, phone_number="+919812300900", started_at=timezone.now())
    Agent.objects.filter(pk=asha.pk).update(is_active=False)
    rows = build_login_report(today, today)
    mine = [r for r in rows if r["agent_id"] == asha.pk]
    assert mine and mine[0]["calls"] == 1 and mine[0]["is_active"] is False


def test_login_report_shows_web_sign_in(admin):
    from apps.reports.login_report import build_login_report
    AgentLoginSession.objects.create(agent=admin)
    today = timezone.localdate()
    row = next(r for r in build_login_report(today, today) if r["agent_id"] == admin.pk)
    assert row["first_sign_in"] is not None
    assert row["first_online"] is None


# ---------------------------------------------------------------------------
# M7 — current pipeline; daily trend has every day
# ---------------------------------------------------------------------------

def test_current_funnel_counts_old_leads(admin):
    from apps.leads.models import Lead
    from apps.reports.views import ConversionFunnelView
    lead = _lead(phone="+919812300601")
    Lead.objects.filter(pk=lead.pk).update(created_at=timezone.now() - timedelta(days=60))
    response = _call(ConversionFunnelView, "get", "/x/?current=1", admin)
    assert response.status_code == 200
    assert response.data["total"] >= 1
    dated = _call(ConversionFunnelView, "get", f"/x/?date_from={timezone.localdate()}", admin)
    assert dated.data["total"] == response.data["total"] - 1


def test_daily_trend_has_every_day():
    from apps.reports.views import _fill_days
    rows = [{"date": date(2026, 9, 1), "total": 2, "connected": 1}, {"date": date(2026, 9, 4), "total": 1, "connected": 0}]
    days = _fill_days(rows, "2026-09-01", "2026-09-05")
    assert [d["date"] for d in days] == ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"]
    assert days[1]["total"] == 0 and days[0]["connection_rate"] == 50.0


# ---------------------------------------------------------------------------
# M9 — search
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("term", ["99302 15251", "09930215251", "+91 99302-15251", "919930215251", "mishra rohan", "Meta - Facebook"])
def test_lead_search_understands_how_people_type(term):
    from apps.leads.models import Lead
    from apps.leads.search import lead_search_q
    lead = _lead(phone="+919930215251", source="meta_facebook")
    assert Lead.objects.filter(lead_search_q(term)).filter(pk=lead.pk).exists()


def test_lead_search_does_not_match_everything():
    from apps.leads.models import Lead
    from apps.leads.search import lead_search_q
    _lead(phone="+919930215251")
    assert not Lead.objects.filter(lead_search_q("zzzz-nobody")).exists()


# ---------------------------------------------------------------------------
# M10 — lead edit keeps source, address, DND
# ---------------------------------------------------------------------------

def test_lead_edit_accepts_source_address_and_dnd(admin):
    from apps.leads.views import LeadDetailView
    lead = _lead(phone="+919812300611", owner=admin)
    response = _call(LeadDetailView, "patch", "/x/", admin,
                     {"source": "referral", "address": "12 MG Road", "is_dnd": True, "email": ""}, pk=lead.pk)
    assert response.status_code == 200, response.data
    lead.refresh_from_db()
    assert (lead.source, lead.address, lead.is_dnd) == ("referral", "12 MG Road", True)


# ---------------------------------------------------------------------------
# M16 — Meta field mapping matches labels to field names
# ---------------------------------------------------------------------------

def test_field_mapping_matches_loosely():
    from apps.integrations.field_mapping import apply_field_mapping
    lead_data, custom = apply_field_mapping(
        {"company_name": "Acme", "budget": "50000", "full_name": "Ravi"},
        {"Company name": "custom:company_name", "BUDGET": "budget", "Full name": "name"},
    )
    assert custom == {"company_name": "Acme"}
    assert lead_data["budget"] == "50000"
    assert lead_data["name"] == "Ravi"


# ---------------------------------------------------------------------------
# GST — state code spellings
# ---------------------------------------------------------------------------

def test_same_state_under_two_spellings_is_intra_state():
    from apps.erp.gst import split_gst
    split = split_gst(Decimal("100"), Decimal("18"), seller_state="TS", buyer_state="TG")
    assert split["is_interstate"] is False
    assert split_gst(Decimal("100"), Decimal("18"), seller_state="MH", buyer_state="KA")["is_interstate"] is True


def test_customer_state_is_stored_canonically():
    from apps.erp.serializers import CustomerSerializer
    s = CustomerSerializer(data={"name": "C", "state_code": "tg"})
    assert s.is_valid(), s.errors
    assert s.validated_data["state_code"] == "TS"
    assert not CustomerSerializer(data={"name": "C", "state_code": "ZZ"}).is_valid()


# ---------------------------------------------------------------------------
# H8 — queues show deactivated members
# ---------------------------------------------------------------------------

def test_queue_agents_carry_their_active_flag(admin, asha):
    from apps.leads.models import CallQueue, CallQueueMembership
    from apps.leads.serializers import CallQueueSerializer
    q = CallQueue.objects.create(name="Q")
    CallQueueMembership.objects.create(queue=q, agent=asha)
    Agent.objects.filter(pk=asha.pk).update(is_active=False)
    data = CallQueueSerializer(CallQueue.objects.get(pk=q.pk)).data
    assert data["agents"][0]["is_active"] is False
