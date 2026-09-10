"""
TeleCRM Backend — apps/recruitment/services/onboarding.py

The Recruitment → HRMS bridge: turn an accepted offer into a real employee.

This is the piece that makes the suite one system rather than two products
sharing a login. Without it, every hire is retyped by hand into HRMS — which
is exactly where the designation, joining date and reporting line drift apart
between the two modules.

What it does NOT do: create a login. An Agent is an identity with a password
and CRM access, and handing one out is a decision an admin makes deliberately,
not a side effect of a candidate accepting an offer. So the flow is:

    accept offer → (admin creates the Agent) → convert → Employee

and convert() matches the Agent by email, telling the caller plainly when it
can't find one rather than silently inventing a login.
"""
import logging
import re
from decimal import Decimal

from django.db import transaction

from apps.hrms.models import Employee, SalaryStructure
from apps.recruitment.constants import ActivityKind, ApplicationStatus, OfferStatus
from apps.recruitment.models import Offer
from apps.recruitment.services.pipeline import log

logger = logging.getLogger(__name__)


def suggest_employee_code(prefix: str = "EMP") -> str:
    """
    Next free employee code, e.g. EMP-0042.

    Reads the highest numeric suffix already used rather than counting rows:
    counting breaks the moment anyone is deleted, and quietly hands the new
    joiner a code somebody already has.
    """
    highest = 0
    for code in Employee.objects.values_list("employee_code", flat=True):
        match = re.search(r"(\d+)\s*$", code or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:04d}"


@transaction.atomic
def convert_to_employee(offer: Offer, *, actor=None, agent=None, employee_code: str = "") -> Employee:
    """
    Create the HRMS Employee (and an opening salary structure) for an accepted
    offer.

    Idempotent: calling it twice returns the employee created the first time
    rather than a duplicate. That matters because this sits behind a button
    somebody will double-click.
    """
    if offer.status != OfferStatus.ACCEPTED:
        raise ValueError(
            f"This offer is {offer.get_status_display().lower()}. "
            f"Only an accepted offer can be converted to an employee."
        )
    if offer.converted_employee_id:
        return offer.converted_employee

    application = offer.application
    candidate = application.candidate

    # Match the Agent by email — see the module docstring for why this never
    # creates one.
    if agent is None:
        from apps.authentication.models import Agent

        if not candidate.email:
            raise ValueError(
                f"{candidate.name} has no email address, so their login cannot be matched. "
                f"Add one to the candidate, then create their agent account."
            )
        agent = Agent.objects.filter(email__iexact=candidate.email).first()
    if agent is None:
        raise ValueError(
            f"No agent account exists for {candidate.email}. "
            f"Create their login under Agents first, then convert this offer."
        )
    if Employee.objects.filter(agent=agent).exists():
        raise ValueError(f"{candidate.name} is already enrolled in HRMS.")

    employee = Employee.objects.create(
        agent=agent,
        employee_code=employee_code or suggest_employee_code(),
        designation=offer.designation or candidate.current_designation,
        department=offer.department or application.opening.department,
        employment_type=offer.employment_type,
        reporting_to=offer.reporting_to,
        date_of_joining=offer.joining_date,
    )

    # Seed an opening salary structure from the offer so payroll has something
    # to run against on day one. Monthly figures; statutory deductions stay
    # zero because their rates depend on wage slab and state — see
    # hrms/services/payroll.py.
    monthly = (offer.fixed_component or offer.annual_ctc) / 12
    SalaryStructure.objects.create(
        employee=employee,
        effective_from=offer.joining_date,
        # A 50/30/20 basic-HRA-special split is the common Indian default and
        # a sane starting point; HR edits it before the first payroll run.
        basic=round(monthly * Decimal("0.50"), 2),
        hra=round(monthly * Decimal("0.30"), 2),
        special_allowance=round(monthly * Decimal("0.20"), 2),
    )

    offer.converted_employee = employee
    offer.save(update_fields=["converted_employee", "updated_at"])

    if application.status != ApplicationStatus.HIRED:
        application.status = ApplicationStatus.HIRED
        application.save(update_fields=["status", "updated_at"])

    log(application, ActivityKind.OFFER,
        f"Converted to employee {employee.employee_code}",
        actor=actor,
        detail=f"Joining {offer.joining_date}. A draft salary structure was created "
               f"from the offer — review it before the first payroll run.")
    logger.info("Offer %s converted to employee %s", offer.pk, employee.employee_code)
    return employee
