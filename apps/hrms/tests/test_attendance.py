"""
Attendance check-in/check-out.

The bug these cover: mark_check_in never set `status`. Attendance.status
defaults to ABSENT, and `status` was not even in the save's update_fields, so
an agent tapping "check in" on the phone produced an ABSENT row carrying a
check-in time — and the CRM showed them absent.

It was also unrecoverable. Check-in promotes the row to MANUAL, and
sync_attendance_for refuses to touch anything that is not AUTO, so the derived
path could never correct it. The agent stayed absent all day however long they
worked.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.constants import AgentWorkStatus
from apps.hrms.constants import AttendanceSource, AttendanceStatus
from apps.hrms.models import Attendance, Employee, Holiday
from apps.hrms.services.attendance import (
    mark_check_in,
    mark_check_out,
    sync_attendance_for,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def employee():
    from apps.authentication.models import Agent

    agent = Agent.objects.create_agent(
        email="att@example.com", name="Attendance Tester", password="x",
    )
    return Employee.objects.create(
        agent=agent,
        employee_code="EMP-ATT-1",
        date_of_joining=timezone.localdate() - timedelta(days=30),
    )


def test_check_in_marks_the_agent_present(employee):
    """The reported bug, directly."""
    row = mark_check_in(employee)

    assert row.status == AttendanceStatus.PRESENT, (
        "checking in must not leave the row at the model's ABSENT default"
    )
    assert row.check_in is not None
    assert row.source == AttendanceSource.MANUAL


def test_the_status_actually_reaches_the_database(employee):
    """
    `status` was missing from update_fields, so even setting it in memory
    would not have been written. Re-read rather than trusting the instance.
    """
    mark_check_in(employee)

    stored = Attendance.objects.get(employee=employee, date=timezone.localdate())
    assert stored.status == AttendanceStatus.PRESENT


def test_a_manual_row_is_not_reverted_by_the_auto_sync(employee):
    """
    Check-in sets source=MANUAL, which sync_attendance_for deliberately will
    not overwrite. That is the behaviour that made the original bug stick, so
    the row it leaves behind has to be right in the first place.
    """
    mark_check_in(employee)
    synced = sync_attendance_for(employee, timezone.localdate())

    assert synced.status == AttendanceStatus.PRESENT
    assert synced.source == AttendanceSource.MANUAL


def test_checking_in_twice_keeps_the_first_time(employee):
    first = mark_check_in(employee)
    original = first.check_in

    again = mark_check_in(employee, at=timezone.now() + timedelta(hours=2))

    assert again.check_in == original
    assert again.status == AttendanceStatus.PRESENT


def test_check_out_downgrades_a_short_day(employee):
    """
    Presence claimed at check-in is provisional. A twenty-minute day is not a
    present day, and check-out is where that gets settled.
    """
    start = timezone.now() - timedelta(minutes=20)
    mark_check_in(employee, at=start)
    row = mark_check_out(employee)

    assert row.status == AttendanceStatus.ABSENT
    assert 0 < row.worked_seconds < 3600


def test_check_out_keeps_a_full_day_present(employee):
    mark_check_in(employee, at=timezone.now() - timedelta(hours=8))
    row = mark_check_out(employee)

    assert row.status == AttendanceStatus.PRESENT
    assert row.worked_seconds >= 6 * 3600


def test_check_out_gives_a_half_day_its_own_status(employee):
    mark_check_in(employee, at=timezone.now() - timedelta(hours=4))
    row = mark_check_out(employee)

    assert row.status == AttendanceStatus.HALF_DAY


def test_check_out_without_a_check_in_falls_back_to_worked_time(employee):
    """
    Somebody who dialled all morning and only pressed the button on the way
    out should not be filed as absent. With no check_in the span cannot be
    measured, so the status logs answer instead.
    """
    from apps.authentication.models import AgentStatusLog

    now = timezone.now()
    AgentStatusLog.objects.create(
        agent=employee.agent,
        status=AgentWorkStatus.ON_CALL,
        started_at=now - timedelta(hours=7),
        ended_at=now,
        duration_seconds=7 * 3600,
    )

    row = mark_check_out(employee)

    assert row.status == AttendanceStatus.PRESENT
    assert row.worked_seconds >= 6 * 3600


def test_approved_leave_is_not_overturned_by_a_stray_check_in(employee):
    """Leave is a decision somebody already made and approved."""
    day = timezone.localdate()
    Attendance.objects.create(
        employee=employee, date=day,
        status=AttendanceStatus.ON_LEAVE, source=AttendanceSource.MANUAL,
    )

    row = mark_check_in(employee)

    assert row.status == AttendanceStatus.ON_LEAVE
    assert row.check_in is None


def test_a_holiday_still_reads_as_a_holiday_at_check_out(employee):
    day = timezone.localdate()
    Holiday.objects.create(date=day, name="Test holiday")

    mark_check_in(employee, at=timezone.now() - timedelta(hours=8))
    row = mark_check_out(employee)

    assert row.status == AttendanceStatus.HOLIDAY
