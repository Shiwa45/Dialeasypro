"""
Tests for the ATS pipeline and the Recruitment → HRMS handover.

The cases here are the ones that would silently corrupt data rather than
raise: a stage and a status disagreeing, a double-click creating two
employees, an application to a closed role.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.core.capabilities import Cap, has_capability
from apps.core.constants import AgentRole
from apps.recruitment.constants import ApplicationStatus, OfferStatus, OpeningStatus
from apps.recruitment.models import Candidate, JobOpening, Offer, PipelineStage
from apps.recruitment.services import onboarding as onboarding_svc
from apps.recruitment.services import pipeline as pipeline_svc

pytestmark = pytest.mark.django_db


@pytest.fixture
def stages():
    pipeline_svc.seed_pipeline()
    return {s.name: s for s in PipelineStage.objects.all()}


@pytest.fixture
def opening():
    return JobOpening.objects.create(
        title="Sales Executive", code="SLS-001",
        department="Sales", status=OpeningStatus.OPEN, openings=2,
        opened_on=date.today(),
    )


@pytest.fixture
def candidate():
    return Candidate.objects.create(
        name="Asha Menon", email="asha@example.com", phone="9876543210",
        total_experience_years=Decimal("3.0"),
    )


def test_seed_pipeline_is_idempotent():
    assert pipeline_svc.seed_pipeline() == 6
    # Running it again on a tenant that already has stages must not duplicate.
    assert pipeline_svc.seed_pipeline() == 0
    assert PipelineStage.objects.count() == 6


def test_first_stage_is_the_lowest_non_terminal(stages):
    assert pipeline_svc.first_stage().name == "Applied"


def test_application_lands_on_the_first_stage(stages, opening, candidate):
    app = pipeline_svc.create_application(candidate=candidate, opening=opening)
    assert app.stage.name == "Applied"
    assert app.status == ApplicationStatus.ACTIVE
    # Creation always leaves a trail row.
    assert app.activities.count() == 1


def test_cannot_apply_to_a_draft_opening(stages, candidate):
    draft = JobOpening.objects.create(title="Ops", code="OPS-1", status=OpeningStatus.DRAFT)
    with pytest.raises(ValueError, match="not accepting applications"):
        pipeline_svc.create_application(candidate=candidate, opening=draft)


def test_cannot_apply_the_same_person_twice(stages, opening, candidate):
    pipeline_svc.create_application(candidate=candidate, opening=opening)
    with pytest.raises(ValueError, match="already been applied"):
        pipeline_svc.create_application(candidate=candidate, opening=opening)


def test_moving_into_a_terminal_stage_closes_the_status(stages, opening, candidate):
    """
    The classic ATS reporting bug: a candidate sitting in "Rejected" while
    still counted as an active application.
    """
    app = pipeline_svc.create_application(candidate=candidate, opening=opening)
    pipeline_svc.move_stage(app, stages["Rejected"], note="Not enough experience")
    app.refresh_from_db()
    assert app.status == ApplicationStatus.REJECTED
    assert app.rejection_reason == "Not enough experience"


def test_moving_to_hired_marks_the_application_hired(stages, opening, candidate):
    app = pipeline_svc.create_application(candidate=candidate, opening=opening)
    pipeline_svc.move_stage(app, stages["Hired"])
    app.refresh_from_db()
    assert app.status == ApplicationStatus.HIRED
    assert opening.hired_count == 1
    assert opening.is_filled is False  # two positions, one filled


def test_a_closed_application_cannot_be_moved(stages, opening, candidate):
    app = pipeline_svc.create_application(candidate=candidate, opening=opening)
    pipeline_svc.move_stage(app, stages["Rejected"])
    app.refresh_from_db()
    with pytest.raises(ValueError, match="cannot be moved"):
        pipeline_svc.move_stage(app, stages["Interview"])


def test_every_move_writes_an_activity_row(stages, opening, candidate):
    app = pipeline_svc.create_application(candidate=candidate, opening=opening)
    pipeline_svc.move_stage(app, stages["Screening"])
    pipeline_svc.move_stage(app, stages["Interview"])
    summaries = list(app.activities.values_list("summary", flat=True))
    assert "Screening → Interview" in summaries
    assert "Applied → Screening" in summaries


def test_duplicate_detection_matches_on_email_or_phone(candidate):
    assert pipeline_svc.find_duplicates(email="ASHA@example.com").count() == 1
    # Last ten digits, so +91 and a bare number match the same person.
    assert pipeline_svc.find_duplicates(phone="+919876543210").count() == 1
    assert pipeline_svc.find_duplicates(email="nobody@example.com").count() == 0
    # A candidate never matches itself when editing.
    assert pipeline_svc.find_duplicates(
        email="asha@example.com", exclude_id=candidate.id,
    ).count() == 0


# ============================================================
# Offer → Employee
# ============================================================

@pytest.fixture
def accepted_offer(stages, opening, candidate):
    app = pipeline_svc.create_application(candidate=candidate, opening=opening)
    return Offer.objects.create(
        application=app,
        annual_ctc=Decimal("600000.00"),
        fixed_component=Decimal("600000.00"),
        designation="Sales Executive",
        department="Sales",
        joining_date=date.today() + timedelta(days=30),
        status=OfferStatus.ACCEPTED,
    )


def test_only_an_accepted_offer_converts(accepted_offer):
    accepted_offer.status = OfferStatus.SENT
    accepted_offer.save()
    with pytest.raises(ValueError, match="Only an accepted offer"):
        onboarding_svc.convert_to_employee(accepted_offer)


def test_conversion_requires_an_existing_agent(accepted_offer):
    """
    Converting must never invent a login — handing out CRM access is a
    deliberate admin decision, not a side effect of accepting an offer.
    """
    with pytest.raises(ValueError, match="No agent account exists"):
        onboarding_svc.convert_to_employee(accepted_offer)


def test_conversion_creates_employee_and_salary_structure(accepted_offer):
    from apps.authentication.models import Agent

    agent = Agent.objects.create_agent(
        email="asha@example.com", password="x", name="Asha Menon", role=AgentRole.AGENT,
    )
    employee = onboarding_svc.convert_to_employee(accepted_offer, agent=agent)

    assert employee.designation == "Sales Executive"
    assert employee.date_of_joining == accepted_offer.joining_date
    # Monthly 50/30/20 split of a ₹6L annual fixed component.
    structure = employee.salary_structures.first()
    assert structure.basic == Decimal("25000.00")
    assert structure.hra == Decimal("15000.00")
    assert structure.special_allowance == Decimal("10000.00")
    # Statutory deductions are deliberately left at zero.
    assert structure.total_deductions == Decimal("0.00")


def test_conversion_is_idempotent(accepted_offer):
    """This sits behind a button somebody will double-click."""
    from apps.authentication.models import Agent

    agent = Agent.objects.create_agent(
        email="asha@example.com", password="x", name="Asha Menon", role=AgentRole.AGENT,
    )
    first = onboarding_svc.convert_to_employee(accepted_offer, agent=agent)
    second = onboarding_svc.convert_to_employee(accepted_offer, agent=agent)
    assert first.pk == second.pk


def test_suggest_employee_code_reads_the_highest_used(accepted_offer):
    from apps.authentication.models import Agent
    from apps.hrms.models import Employee

    a1 = Agent.objects.create_agent(email="a1@x.test", password="x", name="A One")
    Employee.objects.create(agent=a1, employee_code="EMP-0041", date_of_joining=date.today())
    # Counting rows instead of reading the max would hand out EMP-0002 here.
    assert onboarding_svc.suggest_employee_code() == "EMP-0042"


# ============================================================
# Capabilities
# ============================================================

class _FakeAgent:
    def __init__(self, role):
        self.role = role


def test_hr_owns_hrms_but_not_crm_admin():
    hr = _FakeAgent(AgentRole.HR)
    assert has_capability(hr, Cap.HRMS_PAYROLL)
    assert has_capability(hr, Cap.HRMS_MANAGE)
    assert has_capability(hr, Cap.ATS_MANAGE)
    # The whole point of the role: no tenant settings, no agent management.
    assert not has_capability(hr, Cap.CRM_SETTINGS)
    assert not has_capability(hr, Cap.CRM_MANAGE_AGENTS)
    assert not has_capability(hr, Cap.ERP_INVOICE_ISSUE)


def test_accounts_owns_billing_but_not_hrms():
    acc = _FakeAgent(AgentRole.ACCOUNTS)
    assert has_capability(acc, Cap.ERP_INVOICE_ISSUE)
    assert has_capability(acc, Cap.ERP_PAYMENTS)
    assert not has_capability(acc, Cap.HRMS_PAYROLL)
    assert not has_capability(acc, Cap.CRM_SETTINGS)


def test_manager_approves_leave_but_never_reads_salary():
    mgr = _FakeAgent(AgentRole.MANAGER)
    assert has_capability(mgr, Cap.HRMS_APPROVE)
    assert has_capability(mgr, Cap.HRMS_VIEW_ALL)
    assert not has_capability(mgr, Cap.HRMS_PAYROLL)


def test_senior_agent_can_interview_but_not_see_offers():
    sa = _FakeAgent(AgentRole.SENIOR_AGENT)
    assert has_capability(sa, Cap.ATS_INTERVIEW)
    assert not has_capability(sa, Cap.ATS_OFFER)
    assert not has_capability(sa, Cap.ATS_VIEW)


def test_unknown_capability_fails_closed():
    assert not has_capability(_FakeAgent(AgentRole.ADMIN), "ats.not_a_real_capability")
