"""
TeleCRM Backend — apps/hrms/services/incentives.py

The incentive engine: turns CRM outcomes into payable earnings.

Attribution
-----------
A conversion is attributed to the agent who *performed* the status change, on
the date it happened — read from any LeadActivity with meta.new_status
"converted": a status change on the lead page ("status_change") or a call
outcome such as "Sale done" ("call"). Lead.updated_at is deliberately NOT used: any
later edit to the lead would silently move the conversion into another payroll
month. A lead that is converted, lost, and converted again is counted once per
period (distinct lead).

Idempotency
-----------
Earnings are keyed (employee, rule, period_month) and recomputed in place, so
running a period twice never double-pays. An earning attached to a FINALIZED
or PAID payslip is frozen — recomputation skips it rather than silently
changing an amount someone was paid. One attached to a DRAFT slip is still
live: a draft run mid-month used to freeze the month's incentives, usually
at zero.
"""
import logging
from datetime import date
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.core.constants import LeadStatus
from apps.hrms.constants import IncentiveMetric, PayslipStatus
from apps.hrms.models import Employee, IncentiveEarning, IncentiveRule

logger = logging.getLogger(__name__)


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_bounds(period_month: date) -> tuple[date, date]:
    """[first day, first day of next month) for the given month."""
    start = month_start(period_month)
    end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    return start, end


def _converted_lead_ids(agent, start: date, end: date) -> list:
    """Distinct leads this agent moved to `converted` within [start, end)."""
    from apps.leads.models import LeadActivity

    # LeadActivity records its time in `timestamp`; it is a plain Model with
    # no created_at. Filtering on created_at raised FieldError on every call —
    # and compute_all_earnings catches per-employee exceptions so payroll could
    # continue, so the engine reported success while paying nobody anything.
    return list(
        LeadActivity.objects.filter(
            performed_by=agent,
            meta__new_status=LeadStatus.CONVERTED,
            timestamp__date__gte=start,
            timestamp__date__lt=end,
        )
        # A call on a lead that was already converted repeats the status in
        # its meta; that is not a new sale.
        # (has_key first: a plain exclude on a missing key drops the row.)
        .exclude(meta__has_key="old_status", meta__old_status=LeadStatus.CONVERTED)
        # order_by() with no arguments is load-bearing. LeadActivity.Meta sets
        # ordering = ["-timestamp"], and Postgres requires every ORDER BY column
        # to appear in the SELECT of a DISTINCT query — so Django adds timestamp
        # to the row, each conversion event becomes a distinct tuple, and a lead
        # converted twice in a month was counted twice. Incentives were paid on
        # the inflated figure, contradicting this function's own docstring.
        .order_by()
        .values_list("lead_id", flat=True)
        .distinct()
    )


def compute_units(rule: IncentiveRule, employee: Employee, period_month: date) -> Decimal:
    """How many units of the rule's metric the employee earned in the month."""
    from apps.calls.models import CallLog
    from apps.leads.models import Lead

    agent = employee.agent
    start, end = month_bounds(period_month)

    if rule.metric == IncentiveMetric.CONVERTED_LEADS:
        return Decimal(len(_converted_lead_ids(agent, start, end)))

    if rule.metric == IncentiveMetric.REVENUE:
        lead_ids = _converted_lead_ids(agent, start, end)
        if not lead_ids:
            return Decimal("0")
        total = Lead.objects.filter(pk__in=lead_ids).aggregate(t=Sum("deal_value"))["t"]
        return Decimal(total or 0)

    calls = CallLog.objects.filter(
        agent=agent, is_connected=True,
        started_at__date__gte=start, started_at__date__lt=end,
    )

    if rule.metric == IncentiveMetric.CONNECTED_CALLS:
        return Decimal(calls.aggregate(c=Count("id"))["c"] or 0)

    if rule.metric == IncentiveMetric.TALK_MINUTES:
        seconds = calls.aggregate(s=Sum("duration_seconds"))["s"] or 0
        return (Decimal(seconds) / Decimal("60")).quantize(Decimal("0.01"))

    logger.warning(f"[HRMS] unknown incentive metric: {rule.metric}")
    return Decimal("0")


def _rule_applies_to(rule: IncentiveRule, employee: Employee) -> bool:
    roles = rule.applies_to_roles or []
    return (not roles) or (employee.agent.role in roles)


FROZEN = Q(paid_in__status__in=[PayslipStatus.FINALIZED, PayslipStatus.PAID])


def discard_unpaid_earnings(rule: IncentiveRule) -> int:
    """Delete a rule's earnings that no finalized payslip has paid. Returns the count."""
    deleted, _ = IncentiveEarning.objects.filter(rule=rule).exclude(FROZEN).delete()
    return deleted


def compute_earnings_for(employee: Employee, period_month: date) -> list[IncentiveEarning]:
    """
    Recompute every active rule's earning for one employee/month.
    Earnings on a finalized or paid payslip are left untouched; earnings of
    rules that are switched off or no longer cover the employee are removed
    unless they were paid.
    """
    period_month = month_start(period_month)
    results = []
    applicable = [
        rule for rule in IncentiveRule.objects.filter(is_active=True)
        if _rule_applies_to(rule, employee)
    ]

    IncentiveEarning.objects.filter(employee=employee, period_month=period_month).exclude(
        rule__in=applicable
    ).exclude(FROZEN).delete()

    for rule in applicable:
        existing = IncentiveEarning.objects.filter(
            employee=employee, rule=rule, period_month=period_month
        ).select_related("paid_in").first()
        if existing and existing.paid_in_id and existing.paid_in.status != PayslipStatus.DRAFT:
            # Frozen: on a finalized payslip. Never rewrite a paid amount.
            results.append(existing)
            continue

        units = compute_units(rule, employee, period_month)
        amount = rule.compute_payout(units)

        earning, _ = IncentiveEarning.objects.update_or_create(
            employee=employee, rule=rule, period_month=period_month,
            defaults={"units": units, "amount": amount},
        )
        results.append(earning)

    return results


def compute_all_earnings(period_month: date) -> dict:
    """Recompute incentives for every active employee. Returns a summary."""
    period_month = month_start(period_month)
    employees = Employee.objects.filter(is_active=True).select_related("agent")

    total_amount = Decimal("0.00")
    rows = 0
    from apps.hrms.models import Payslip
    from apps.hrms.services.payroll import build_payslip

    drafts = set(
        Payslip.objects.filter(period_month=period_month, status=PayslipStatus.DRAFT)
        .values_list("employee_id", flat=True)
    )
    for employee in employees:
        try:
            earnings = compute_earnings_for(employee, period_month)
            for earning in earnings:
                total_amount += earning.amount
                rows += 1
            if employee.pk in drafts:
                # Keep the draft's totals in step with the new figures.
                build_payslip(employee, period_month)
        except Exception as exc:  # never let one employee abort payroll prep
            logger.error(f"[HRMS] incentive calc failed for {employee.employee_code}: {exc}")

    return {
        "period": period_month.isoformat(),
        "employees": employees.count(),
        "earnings": rows,
        "total_amount": str(total_amount),
    }
