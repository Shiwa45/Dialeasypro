"""
How payroll turns a month of attendance and leave into payable days.

The payslip only carried "payable days", so nobody could see how pay was
reached, and a few days were counted wrongly:
  * an unpaid leave spanning a Sunday docked the Sunday;
  * days before joining were credited as "unrecorded", paying a new joiner for
    the whole month;
  * marking a leaver inactive dropped their final month from the run;
  * pending leave was paid as absence without a word.

September 2026: Sundays are the 6th, 13th, 20th and 27th.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.authentication.models import Agent
from apps.hrms.constants import ApprovalStatus, AttendanceStatus
from apps.hrms.models import Attendance, Employee, Holiday, LeaveRequest, LeaveType, SalaryStructure
from apps.hrms.services.leave import approve_leave
from apps.hrms.services.payroll import build_payslip, run_payroll

PERIOD = date(2026, 9, 1)
SUNDAYS = {6, 13, 20, 27}
MON_TO_SAT = [0, 1, 2, 3, 4, 5]


def _employee(code, *, joined=date(2025, 1, 1), working_days=MON_TO_SAT, **extra):
    agent = Agent.objects.create(
        name=f"Agent {code}", email=f"{code.lower()}@test.local", role="agent",
        working_days=working_days,
    )
    emp = Employee.objects.create(agent=agent, employee_code=code, date_of_joining=joined, **extra)
    SalaryStructure.objects.create(
        employee=emp, effective_from=date(2025, 1, 1),
        basic=Decimal("30000.00"), hra=Decimal("10000.00"),
    )
    return emp


def _leave(emp, leave_type, start, end, days, status=ApprovalStatus.PENDING):
    return LeaveRequest.objects.create(
        employee=emp, leave_type=leave_type, start_date=start, end_date=end,
        days=Decimal(days), status=status,
    )


@pytest.fixture
def casual(db):
    return LeaveType.objects.create(name="Casual Leave", annual_quota_days=Decimal("12"), is_paid=True)


@pytest.fixture
def unpaid(db):
    return LeaveType.objects.create(name="Leave Without Pay", annual_quota_days=Decimal("0"), is_paid=False)


@pytest.fixture
def month(casual, unpaid):
    """
    A full month of attendance with a bit of everything:
      paid leave   7–8 (Mon, Tue)
      unpaid leave 12–14 (Sat, Sun, Mon) — the Sunday stays a week-off
      holiday      17
      half day     21
      absent       22
    """
    emp = _employee("EMP-DAYS")
    Holiday.objects.create(date=date(2026, 9, 17), name="Festival")
    leave_dates = {7, 8, 12, 13, 14}
    for d in range(1, 31):
        if d in leave_dates:
            continue
        status = (
            AttendanceStatus.WEEK_OFF if d in SUNDAYS
            else AttendanceStatus.HOLIDAY if d == 17
            else AttendanceStatus.HALF_DAY if d == 21
            else AttendanceStatus.ABSENT if d == 22
            else AttendanceStatus.PRESENT
        )
        Attendance.objects.create(employee=emp, date=PERIOD.replace(day=d), status=status)

    approver = Agent.objects.create(name="HR", email="hr@test.local", role="admin")
    approve_leave(_leave(emp, casual, date(2026, 9, 7), date(2026, 9, 8), "2"), approver)
    approve_leave(_leave(emp, unpaid, date(2026, 9, 12), date(2026, 9, 14), "3"), approver)
    return emp


@pytest.mark.django_db
def test_every_day_of_the_month_is_accounted_for(month):
    slip = build_payslip(month, PERIOD)
    days = slip.breakdown["attendance"]

    assert days["present"] == 19
    assert days["half_day"] == 1
    assert days["paid_leave"] == 2
    assert days["paid_leave_by_type"] == {"Casual Leave": 2}
    assert days["unpaid_leave"] == 2
    assert days["absent"] == 1
    assert days["holiday"] == 1
    assert days["week_off"] == 4
    assert days["unrecorded"] == 0
    assert days["working_days"] == 25
    assert days["days_worked"] == "19.5"
    assert days["lop_days"] == "3.5"

    assert slip.payable_days == Decimal("26.5")
    assert slip.total_days == Decimal("30")
    # 40,000 × 26.5 / 30
    assert slip.gross_earnings == Decimal("35333.33")
    assert slip.breakdown["lop_amount"] == "4666.67"
    assert slip.breakdown["earnings_full"]["basic"] == "30000.00"


@pytest.mark.django_db
def test_unpaid_leave_does_not_dock_the_sunday_inside_it(month):
    sunday = Attendance.objects.get(employee=month, date=date(2026, 9, 13))
    assert sunday.status == AttendanceStatus.WEEK_OFF

    saturday = Attendance.objects.get(employee=month, date=date(2026, 9, 12))
    assert saturday.status == AttendanceStatus.ABSENT


@pytest.mark.django_db
def test_days_before_joining_are_not_paid(db):
    emp = _employee("EMP-NEW", joined=date(2026, 9, 15), working_days=[])

    slip = build_payslip(emp, PERIOD)

    assert slip.breakdown["attendance"]["not_employed"] == 14
    assert slip.payable_days == Decimal("16")
    assert slip.gross_earnings == Decimal("21333.33")  # 40,000 × 16 / 30


@pytest.mark.django_db
def test_a_leaver_is_paid_to_the_exit_date_and_then_dropped(db):
    emp = _employee("EMP-LEFT", working_days=[], is_active=False, date_of_exit=date(2026, 9, 10))

    result = run_payroll(PERIOD)

    assert result["payslips"] == 1
    slip = emp.payslips.get(period_month=PERIOD)
    assert slip.payable_days == Decimal("10")
    assert run_payroll(date(2026, 10, 1))["payslips"] == 0


@pytest.mark.django_db
def test_the_run_flags_leave_still_waiting_for_a_decision(casual):
    emp = _employee("EMP-WAIT")
    _leave(emp, casual, date(2026, 9, 21), date(2026, 9, 22), "2")

    result = run_payroll(PERIOD)

    assert result["pending_leave"] == [
        {"employee_code": "EMP-WAIT", "name": "Agent EMP-WAIT", "requests": 1},
    ]


@pytest.mark.django_db
def test_approved_leave_without_attendance_rows_is_still_counted(casual, unpaid):
    """Payroll reads the leave itself, not only the rows its approval wrote."""
    emp = _employee("EMP-ROWLESS", working_days=[])
    _leave(emp, casual, date(2026, 9, 1), date(2026, 9, 2), "2", status=ApprovalStatus.APPROVED)
    _leave(emp, unpaid, date(2026, 9, 3), date(2026, 9, 3), "1", status=ApprovalStatus.APPROVED)
    for d in range(4, 31):
        Attendance.objects.create(employee=emp, date=PERIOD + timedelta(days=d - 1),
                                  status=AttendanceStatus.PRESENT)

    days = build_payslip(emp, PERIOD).breakdown["attendance"]

    assert (days["paid_leave"], days["unpaid_leave"], days["present"]) == (2, 1, 27)
