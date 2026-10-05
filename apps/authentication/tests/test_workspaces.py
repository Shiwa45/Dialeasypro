"""
Role workspaces: what an agent, a read-only user and a recruiter can reach,
and the tenant's switch for agent web sign-in.

The web UI hides screens from these roles; these tests pin the part that
matters — what the API itself will and will not do for them.
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.authentication.views import (
    AgentDetailAPIView, AgentListAPIView, AgentLoginAPIView, AgentProfileAPIView,
    AgentWebAccessAPIView, TenantFeaturesAPIView,
)
from apps.authentication.web_access import feature_checker
from apps.calls.models import CallLog
from apps.communications.models import WhatsAppConversation
from apps.communications.views import WhatsAppConversationListView
from apps.core.capabilities import Cap, Workspace, has_capability, workspace_for
from apps.core.constants import AgentRole, FeatureKey, ModuleKey
from apps.leads.models import Lead
from apps.leads.views import LeadDetailView, LeadNoteListCreateView, LeadStatusUpdateView
from apps.recruitment.views import (
    OfferConvertView, RecruitmentPeopleView, ReportingOptionsView,
)
from apps.reports.views import MyPerformanceView
from apps.tenants.models import Tenant
from conftest import TEST_SCHEMA

pytestmark = pytest.mark.django_db

PASSWORD = "Pw@12345678"
factory = APIRequestFactory()

# Plan shapes, as the feature map a request would carry.
EVERYTHING = set(FeatureKey.ALL)
NO_AGENT_WEB = EVERYTHING - {FeatureKey.AGENT_WEB_ACCESS}
NO_RECRUITMENT = EVERYTHING - set(ModuleKey.FEATURES[ModuleKey.RECRUITMENT])


def _agent(email, role):
    if role == AgentRole.ADMIN:
        return Agent.objects.create_tenant_admin(email=email, name=email.split("@")[0], password=PASSWORD)
    return Agent.objects.create_agent(email=email, name=email.split("@")[0], password=PASSWORD, role=role)


@pytest.fixture
def admin():
    return _agent("boss@x.com", AgentRole.ADMIN)


@pytest.fixture
def asha():
    return _agent("asha@x.com", AgentRole.AGENT)


@pytest.fixture
def bilal():
    return _agent("bilal@x.com", AgentRole.AGENT)


@pytest.fixture
def viewer():
    return _agent("viewer@x.com", AgentRole.READONLY)


@pytest.fixture
def recruiter():
    return _agent("rita@x.com", AgentRole.RECRUITER)


@pytest.fixture
def hr():
    return _agent("hr@x.com", AgentRole.HR)


@pytest.fixture
def tenant():
    t = Tenant.objects.get(schema_name=TEST_SCHEMA)
    original = t.agent_web_access
    yield t
    t.agent_web_access = original
    t.save(update_fields=["agent_web_access"])


def _set_web_access(tenant, on):
    tenant.agent_web_access = on
    tenant.save(update_fields=["agent_web_access"])


def _lead(phone, owner=None, **kw):
    return Lead.objects.create(name=f"Lead {phone[-3:]}", phone=phone, assigned_to=owner, **kw)


def _call(view, method, path, user, data=None, features=EVERYTHING, headers=None, **kwargs):
    request = getattr(factory, method)(path, data, format="json", **(headers or {}))
    if user is not None:
        force_authenticate(request, user=user)
    if features is not None:
        enabled = set(features)
        request.has_feature = lambda key: key in enabled
    response = view.as_view()(request, **kwargs)
    response.render()
    return response


# ---------------------------------------------------------------------------
# Workspace + capabilities
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role,expected", [
    (AgentRole.AGENT, Workspace.AGENT),
    (AgentRole.READONLY, Workspace.AGENT),
    (AgentRole.RECRUITER, Workspace.RECRUITER),
    (AgentRole.SENIOR_AGENT, Workspace.FULL),
    (AgentRole.MANAGER, Workspace.FULL),
    (AgentRole.ADMIN, Workspace.FULL),
    (AgentRole.HR, Workspace.FULL),
    (AgentRole.ACCOUNTS, Workspace.FULL),
])
def test_workspace_follows_role(role, expected):
    assert workspace_for(Agent(role=role)) == expected


def test_workspace_of_anonymous_is_full_not_a_crash():
    assert workspace_for(None) == Workspace.FULL


def test_recruiter_capabilities_are_recruitment_only():
    rita = Agent(role=AgentRole.RECRUITER)
    for cap in (Cap.ATS_VIEW, Cap.ATS_MANAGE, Cap.ATS_INTERVIEW, Cap.ATS_OFFER):
        assert has_capability(rita, cap), cap
    assert not has_capability(rita, Cap.ATS_ONBOARD)
    assert not has_capability(rita, Cap.CRM_VIEW)
    assert not has_capability(rita, Cap.CRM_SETTINGS)
    for name in dir(Cap):
        value = getattr(Cap, name)
        if isinstance(value, str) and value.startswith(("hrms.", "erp.")):
            assert not has_capability(rita, value), value


def test_hr_and_admin_keep_onboarding():
    assert has_capability(Agent(role=AgentRole.HR), Cap.ATS_ONBOARD)
    assert has_capability(Agent(role=AgentRole.ADMIN), Cap.ATS_ONBOARD)


# ---------------------------------------------------------------------------
# Web sign-in switch
# ---------------------------------------------------------------------------

WEB = {"HTTP_X_CLIENT": "web"}


def _login(email, password=PASSWORD, web=True, features=EVERYTHING):
    return _call(AgentLoginAPIView, "post", "/api/v1/auth/login/", None,
                 {"email": email, "password": password}, features=features,
                 headers=WEB if web else None)


def test_agent_signs_in_on_web_by_default(tenant, asha):
    assert tenant.agent_web_access is True
    assert _login(asha.email).status_code == 200


def test_web_access_off_refuses_agent_on_web(tenant, asha):
    _set_web_access(tenant, False)
    response = _login(asha.email)
    assert response.status_code == 403
    assert response.data["error"] == "web_access_disabled"
    assert response.data["reason"] == "setting"
    assert "access" not in response.data


def test_web_access_off_also_refuses_readonly(tenant, viewer):
    _set_web_access(tenant, False)
    assert _login(viewer.email).status_code == 403


def test_web_access_off_still_lets_the_mobile_app_in(tenant, asha):
    _set_web_access(tenant, False)
    assert _login(asha.email, web=False).status_code == 200


@pytest.mark.parametrize("role", [AgentRole.ADMIN, AgentRole.MANAGER, AgentRole.SENIOR_AGENT,
                                  AgentRole.HR, AgentRole.RECRUITER])
def test_web_access_off_never_blocks_other_roles(tenant, role):
    person = _agent(f"{role}@x.com", role)
    _set_web_access(tenant, False)
    assert _login(person.email).status_code == 200


def test_wrong_password_does_not_reveal_the_web_policy(tenant, asha):
    _set_web_access(tenant, False)
    response = _login(asha.email, password="wrong-password-1")
    assert response.status_code != 403 or response.data.get("error") != "web_access_disabled"
    assert response.status_code in (400, 401)


def test_features_report_workspace_and_web_access(tenant, asha, recruiter, admin):
    for person, workspace in ((asha, "agent"), (recruiter, "recruiter"), (admin, "full")):
        response = _call(TenantFeaturesAPIView, "get", "/api/v1/auth/features/", person)
        assert response.status_code == 200
        assert response.data["workspace"] == workspace
        assert response.data["web_access_allowed"] is True

    _set_web_access(tenant, False)
    response = _call(TenantFeaturesAPIView, "get", "/api/v1/auth/features/", asha)
    assert response.data["web_access_allowed"] is False
    response = _call(TenantFeaturesAPIView, "get", "/api/v1/auth/features/", admin)
    assert response.data["web_access_allowed"] is True


def test_admin_reads_and_flips_the_switch(tenant, admin):
    response = _call(AgentWebAccessAPIView, "get", "/api/v1/auth/web-access/", admin)
    assert response.status_code == 200
    assert response.data == {"agent_web_access": True, "available_in_plan": True}

    response = _call(AgentWebAccessAPIView, "patch", "/api/v1/auth/web-access/", admin,
                     {"agent_web_access": False})
    assert response.status_code == 200
    tenant.refresh_from_db()
    assert tenant.agent_web_access is False


def test_switch_rejects_non_boolean(tenant, admin):
    response = _call(AgentWebAccessAPIView, "patch", "/api/v1/auth/web-access/", admin,
                     {"agent_web_access": "no"})
    assert response.status_code == 400
    tenant.refresh_from_db()
    assert tenant.agent_web_access is True


@pytest.mark.parametrize("role", [AgentRole.AGENT, AgentRole.READONLY, AgentRole.RECRUITER, AgentRole.HR])
def test_only_settings_admins_can_touch_the_switch(tenant, role):
    person = _agent(f"{role}-sw@x.com", role)
    response = _call(AgentWebAccessAPIView, "patch", "/api/v1/auth/web-access/", person,
                     {"agent_web_access": False})
    assert response.status_code == 403
    tenant.refresh_from_db()
    assert tenant.agent_web_access is True


# ---------------------------------------------------------------------------
# My performance
# ---------------------------------------------------------------------------

def test_my_performance_counts_only_my_own_work(asha, bilal):
    mine = _lead("+919812300101", asha)
    _lead("+919812300102", asha)
    _lead("+919812300103", bilal)
    CallLog.objects.create(agent=asha, lead=mine, phone_number=mine.phone,
                           is_connected=True, duration_seconds=120)
    CallLog.objects.create(agent=asha, phone_number="+919812300199", is_connected=False)
    for _ in range(5):
        CallLog.objects.create(agent=bilal, phone_number="+919812300198", is_connected=True,
                               duration_seconds=60)
    mine.update_status("converted", agent=asha)

    response = _call(MyPerformanceView, "get", f"/api/v1/reports/my-performance/?days=7&agent_id={bilal.pk}", asha)
    assert response.status_code == 200
    data = response.data
    assert data["calls"]["total"] == 2
    assert data["calls"]["connected"] == 1
    assert data["calls"]["talk_seconds"] == 120
    assert data["leads"]["assigned_total"] == 2
    assert data["leads"]["converted_in_period"] == 1
    assert len(data["calls_by_day"]) == 7
    assert sum(day["calls"] for day in data["calls_by_day"]) == 2


def test_my_performance_bad_period_falls_back_to_a_week(asha):
    response = _call(MyPerformanceView, "get", "/api/v1/reports/my-performance/?days=9999", asha)
    assert response.status_code == 200
    assert len(response.data["calls_by_day"]) == 7


# ---------------------------------------------------------------------------
# Read-only users can look, not touch
# ---------------------------------------------------------------------------

def test_readonly_can_read_but_not_write_a_lead(viewer):
    lead = _lead("+919812300201", viewer)
    assert _call(LeadDetailView, "get", f"/api/v1/leads/{lead.pk}/", viewer, pk=lead.pk).status_code == 200
    assert _call(LeadDetailView, "patch", f"/api/v1/leads/{lead.pk}/", viewer,
                 {"city": "Pune"}, pk=lead.pk).status_code == 403
    assert _call(LeadStatusUpdateView, "patch", f"/api/v1/leads/{lead.pk}/status/", viewer,
                 {"status": "contacted"}, pk=lead.pk).status_code == 403
    assert _call(LeadNoteListCreateView, "post", f"/api/v1/leads/{lead.pk}/notes/", viewer,
                 {"content": "hi", "note": "hi"}, lead_id=lead.pk).status_code == 403
    lead.refresh_from_db()
    assert lead.status == "new"


def test_agent_can_work_own_lead(asha):
    lead = _lead("+919812300301", asha)
    response = _call(LeadStatusUpdateView, "patch", f"/api/v1/leads/{lead.pk}/status/", asha,
                     {"status": "contacted"}, pk=lead.pk)
    assert response.status_code == 200
    lead.refresh_from_db()
    assert lead.status == "contacted"


def test_agent_cannot_work_a_colleagues_lead(asha, bilal):
    lead = _lead("+919812300302", bilal)
    response = _call(LeadStatusUpdateView, "patch", f"/api/v1/leads/{lead.pk}/status/", asha,
                     {"status": "contacted"}, pk=lead.pk)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# WhatsApp conversations follow lead visibility
# ---------------------------------------------------------------------------

def _thread(lead, n):
    return WhatsAppConversation.objects.create(
        lead=lead, contact_wa_id=f"91981230{n:04d}", business_phone_number_id="pn-1",
    )


def _thread_ids(user):
    response = _call(WhatsAppConversationListView, "get", "/api/v1/comms/whatsapp/conversations/", user)
    assert response.status_code == 200
    rows = response.data["results"] if isinstance(response.data, dict) else response.data
    return {str(row["id"]) for row in rows}


def test_whatsapp_threads_are_scoped_to_visible_leads(admin, asha, bilal, hr):
    a = _thread(_lead("+919812300401", asha), 1)
    b = _thread(_lead("+919812300402", bilal), 2)

    assert _thread_ids(admin) == {str(a.pk), str(b.pk)}
    assert _thread_ids(asha) == {str(a.pk)}
    assert _thread_ids(bilal) == {str(b.pk)}
    # HR used to list every thread in the tenant.
    assert _thread_ids(hr) == set()


# ---------------------------------------------------------------------------
# Recruitment pickers and onboarding
# ---------------------------------------------------------------------------

def test_recruiter_people_picker_returns_only_picker_fields(recruiter, asha):
    response = _call(RecruitmentPeopleView, "get", "/api/v1/recruitment/people/", recruiter)
    assert response.status_code == 200
    assert response.data
    for row in response.data:
        assert set(row) == {"id", "name", "role"}
    assert asha.pk in {row["id"] for row in response.data}


@pytest.mark.parametrize("role", [AgentRole.AGENT, AgentRole.READONLY, AgentRole.ACCOUNTS])
def test_non_recruitment_roles_cannot_use_the_pickers(role):
    person = _agent(f"{role}-pk@x.com", role)
    assert _call(RecruitmentPeopleView, "get", "/api/v1/recruitment/people/", person).status_code == 403
    assert _call(ReportingOptionsView, "get", "/api/v1/recruitment/reporting-options/", person).status_code == 403


@pytest.mark.parametrize("role", [AgentRole.RECRUITER, AgentRole.HR])
def test_reporting_options_open_to_recruitment(role):
    person = _agent(f"{role}-ro@x.com", role)
    response = _call(ReportingOptionsView, "get", "/api/v1/recruitment/reporting-options/", person)
    assert response.status_code == 200
    assert isinstance(response.data, list)


def test_recruiter_cannot_onboard_but_hr_reaches_the_offer(recruiter, hr):
    path = "/api/v1/recruitment/offers/999999/convert-to-employee/"
    assert _call(OfferConvertView, "post", path, recruiter, {}, pk=999999).status_code == 403
    # HR passes the permission check and gets the honest "no such offer".
    assert _call(OfferConvertView, "post", path, hr, {}, pk=999999).status_code == 404


# ---------------------------------------------------------------------------
# Plan gating: agent web access
# ---------------------------------------------------------------------------

def test_plan_without_agent_web_refuses_agents_on_web(tenant, asha, viewer):
    for person in (asha, viewer):
        response = _login(person.email, features=NO_AGENT_WEB)
        assert response.status_code == 403
        assert response.data["error"] == "web_access_disabled"
        assert response.data["reason"] == "plan"
        assert "access" not in response.data


def test_plan_without_agent_web_still_allows_the_mobile_app(tenant, asha):
    assert _login(asha.email, web=False, features=NO_AGENT_WEB).status_code == 200


def test_plan_without_agent_web_never_blocks_admins(tenant, admin):
    assert _login(admin.email, features=NO_AGENT_WEB).status_code == 200


def test_plan_beats_the_tenant_switch(tenant, asha):
    # Switch on (the default) does not help without the plan feature.
    assert tenant.agent_web_access is True
    assert _login(asha.email, features=NO_AGENT_WEB).status_code == 403


def test_features_report_the_plan_refusal_with_its_reason(tenant, asha, admin):
    response = _call(TenantFeaturesAPIView, "get", "/api/v1/auth/features/", asha,
                     features=NO_AGENT_WEB)
    assert response.data["web_access_allowed"] is False
    assert "plan" in response.data["web_access_message"]
    assert FeatureKey.AGENT_WEB_ACCESS in response.data["features"]
    response = _call(TenantFeaturesAPIView, "get", "/api/v1/auth/features/", admin,
                     features=NO_AGENT_WEB)
    assert response.data["web_access_allowed"] is True
    assert response.data["web_access_message"] == ""


def test_switch_reports_plan_availability(tenant, admin):
    response = _call(AgentWebAccessAPIView, "get", "/api/v1/auth/web-access/", admin,
                     features=NO_AGENT_WEB)
    assert response.status_code == 200
    assert response.data == {"agent_web_access": True, "available_in_plan": False}


def test_switch_cannot_be_changed_without_the_plan_feature(tenant, admin):
    response = _call(AgentWebAccessAPIView, "patch", "/api/v1/auth/web-access/", admin,
                     {"agent_web_access": False}, features=NO_AGENT_WEB)
    assert response.status_code == 402
    assert response.data["feature_key"] == FeatureKey.AGENT_WEB_ACCESS
    tenant.refresh_from_db()
    assert tenant.agent_web_access is True


# ---------------------------------------------------------------------------
# Plan gating: the Recruiter role
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("web", [True, False])
def test_recruiter_cannot_sign_in_without_recruitment(tenant, recruiter, web):
    response = _login(recruiter.email, web=web, features=NO_RECRUITMENT)
    assert response.status_code == 403
    assert response.data["error"] == "recruitment_not_in_plan"
    assert "access" not in response.data


def test_recruiter_signs_in_with_recruitment(tenant, recruiter):
    assert _login(recruiter.email, features=EVERYTHING).status_code == 200


def test_partial_recruitment_is_not_recruitment(tenant, recruiter):
    partial = EVERYTHING - {FeatureKey.ATS_OFFERS}
    assert _login(recruiter.email, features=partial).status_code == 403


def test_open_recruiter_session_is_told_to_leave(tenant, recruiter):
    response = _call(TenantFeaturesAPIView, "get", "/api/v1/auth/features/", recruiter,
                     features=NO_RECRUITMENT)
    assert response.data["web_access_allowed"] is False
    assert "Recruitment" in response.data["web_access_message"]


def _create(actor, role, features):
    return _call(AgentListAPIView, "post", "/api/v1/auth/agents/", actor, {
        "email": f"new-{role}@x.com", "name": "New Person", "role": role,
        "password": PASSWORD, "confirm_password": PASSWORD,
    }, features=features)


def test_recruiter_role_cannot_be_created_without_recruitment(admin):
    response = _create(admin, AgentRole.RECRUITER, NO_RECRUITMENT)
    assert response.status_code == 400
    assert "role" in response.data or "Recruit" in str(response.data)
    assert not Agent.objects.filter(email="new-recruiter@x.com").exists()


def test_recruiter_role_can_be_created_with_recruitment(admin):
    response = _create(admin, AgentRole.RECRUITER, EVERYTHING)
    assert response.status_code == 201, response.data
    assert Agent.objects.get(email="new-recruiter@x.com").role == AgentRole.RECRUITER


def test_other_roles_do_not_need_recruitment(admin):
    assert _create(admin, AgentRole.AGENT, NO_RECRUITMENT).status_code == 201


def test_nobody_can_be_switched_to_recruiter_without_recruitment(admin, asha):
    response = _call(AgentDetailAPIView, "patch", f"/api/v1/auth/agents/{asha.pk}/", admin,
                     {"role": AgentRole.RECRUITER}, features=NO_RECRUITMENT, pk=asha.pk)
    assert response.status_code == 400
    asha.refresh_from_db()
    assert asha.role == AgentRole.AGENT


def test_an_existing_recruiter_can_still_be_edited_after_a_downgrade(admin, recruiter):
    response = _call(AgentDetailAPIView, "patch", f"/api/v1/auth/agents/{recruiter.pk}/", admin,
                     {"name": "Rita K", "role": AgentRole.RECRUITER}, features=NO_RECRUITMENT,
                     pk=recruiter.pk)
    assert response.status_code == 200
    recruiter.refresh_from_db()
    assert recruiter.name == "Rita K"


# ---------------------------------------------------------------------------
# Own profile: no self-promotion
# ---------------------------------------------------------------------------

def test_an_agent_cannot_promote_themselves_through_their_profile(asha):
    response = _call(AgentProfileAPIView, "patch", "/api/v1/auth/me/", asha,
                     {"name": "Asha R", "role": "admin", "is_active": True, "employee_id": "X1"})
    assert response.status_code == 200
    asha.refresh_from_db()
    assert asha.name == "Asha R"
    assert asha.role == AgentRole.AGENT
    assert asha.employee_id != "X1"


def test_feature_checker_works_without_a_request():
    has_feature = feature_checker()
    assert isinstance(has_feature(FeatureKey.AGENT_WEB_ACCESS), bool)
