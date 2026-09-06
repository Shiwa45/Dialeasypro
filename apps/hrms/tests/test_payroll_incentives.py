"""
TeleCRM Backend — apps/hrms/tests/test_payroll_incentives.py

Payroll and incentives. Both failure modes here were silent and financial: the
incentive engine raised an exception that its own caller swallowed per
employee, and a payslip rebuild dropped reimbursements while leaving them
marked as reimbursed.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.authentication.models import Agent
from apps.core.constants import LeadStatus
from apps.hrms.constants import ApprovalStatus
from apps.hrms.models import Employee, ExpenseClaim, SalaryStructure
from apps.hrms.services.incentives import _converted_lead_ids, month_start
from apps.hrms.services.payroll import build_payslip
from apps.leads.models import Lead, LeadActivity

PERIOD = date(2026, 9, 1)


@pytest.fixture
def agent(db):
    return Agent.objects.create(
        name="Payroll Agent", email="payroll.agent@test.local", role="agent",
    )


@pytest.fixture
def employee(agent):
    emp = Employee.objects.create(agent=agent, employee_code="EMP-PAY-1",
                                  date_of_joining=date(2025, 1, 1))
    SalaryStructure.objects.create(
        employee=emp, effective_from=date(2025, 1, 1),
        basic=Decimal("30000.00"), hra=Decimal("10000.00"),
    )
    return emp


# ============================================================
# The FieldError that zeroed every incentive
# ============================================================

@pytest.mark.django_db
def test_conversions_are_found_by_the_field_that_exists(agent):
    """
    LeadActivity stores its time in `timestamp` and has no created_at, so the
    lookup raised FieldError — and compute_all_earnings catches per-employee
    exceptions, so the engine reported success while paying nobody.
    """
    lead = Lead.objects.create(name="Converted", phone="+919812300001")
    LeadActivity.objects.create(
        lead=lead, activity_type="status_change", performed_by=agent,
        description="converted", meta={"new_status": LeadStatus.CONVERTED},
        timestamp=timezone.make_aware(
            timezone.datetime(2026, 9, 15, 10, 0)
        ),
    )

    found = _converted_lead_ids(agent, date(2026, 9, 1), date(2026, 10, 1))
    assert found == [lead.pk]


@pytest.mark.django_db
def test_conversions_outside_the_period_are_excluded(agent):
    lead = Lead.objects.create(name="August", phone="+919812300002")
    LeadActivity.objects.create(
        lead=lead, activity_type="status_change", performed_by=agent,
        description="converted", meta={"new_status": LeadStatus.CONVERTED},
        timestamp=timezone.make_aware(timezone.datetime(2026, 8, 20, 10, 0)),
    )
    assert _converted_lead_ids(agent, date(2026, 9, 1), date(2026, 10, 1)) == []


@pytest.mark.django_db
def test_one_lead_converted_twice_counts_once(agent):
    """A lead converted, lost, and converted again is one conversion."""
    lead = Lead.objects.create(name="Twice", phone="+919812300003")
    for day in (5, 20):
        LeadActivity.objects.create(
            lead=lead, activity_type="status_change", performed_by=agent,
            description="converted", meta={"new_status": LeadStatus.CONVERTED},
            timestamp=timezone.make_aware(timezone.datetime(2026, 9, day, 10, 0)),
        )
    assert _converted_lead_ids(agent, date(2026, 9, 1), date(2026, 10, 1)) == [lead.pk]


# ============================================================
# Rebuilding a draft payslip dropped its reimbursements
# ============================================================

@pytest.mark.django_db
def test_rebuilding_a_draft_payslip_keeps_reimbursements(employee):
    """
    The first build links the claims to the slip; the query then filtered on
    reimbursed_in__isnull=True, so a recompute found none and silently removed
    them from net pay while leaving them marked reimbursed — money owed,
    recorded as paid, and absent from the payslip.
    """
    ExpenseClaim.objects.create(
        employee=employee, status=ApprovalStatus.APPROVED,
        amount=Decimal("1500.00"), date=date(2026, 9, 10),
    )

    first = build_payslip(employee, PERIOD)
    assert first.reimbursements_amount == Decimal("1500.00")

    second = build_payslip(employee, PERIOD)
    assert second.reimbursements_amount == Decimal("1500.00"), (
        "a rebuild must not drop reimbursements already linked to this slip"
    )
    assert second.net_pay == first.net_pay


@pytest.mark.django_db
def test_a_claim_reimbursed_elsewhere_is_not_paid_again(employee):
    """The linking exists to stop a claim being paid in two months."""
    claim = ExpenseClaim.objects.create(
        employee=employee, status=ApprovalStatus.APPROVED,
        amount=Decimal("900.00"), date=date(2026, 9, 10),
    )
    other = build_payslip(employee, PERIOD)
    claim.refresh_from_db()
    assert claim.reimbursed_in_id == other.pk

    # A different month must not see it.
    later = build_payslip(employee, date(2026, 10, 1))
    assert later.reimbursements_amount == Decimal("0.00")


@pytest.mark.django_db
def test_unapproved_claims_are_never_reimbursed(employee):
    ExpenseClaim.objects.create(
        employee=employee, status=ApprovalStatus.PENDING,
        amount=Decimal("5000.00"), date=date(2026, 9, 10),
    )
    slip = build_payslip(employee, PERIOD)
    assert slip.reimbursements_amount == Decimal("0.00")


@pytest.mark.django_db
def test_a_finalized_payslip_is_never_silently_rebuilt(employee):
    from apps.hrms.constants import PayslipStatus

    slip = build_payslip(employee, PERIOD)
    slip.status = PayslipStatus.PAID
    slip.save(update_fields=["status"])

    again = build_payslip(employee, PERIOD)
    assert again.pk == slip.pk
    assert again.status == PayslipStatus.PAID

    with pytest.raises(ValueError):
        build_payslip(employee, PERIOD, recompute=True)
