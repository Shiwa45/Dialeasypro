"""
Regression tests for the HRMS QA report (HRMS_QA_REPORT.md, H1–H38).

Each test names the finding it covers. Dates are fixed in September 2026 (a
finished month) unless a test is about the running month, where `today` is
passed explicitly.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.hrms import views as hv
from apps.hrms.constants import ApprovalStatus, AttendanceSource, AttendanceStatus, PayslipStatus
from apps.hrms.models import (
    Attendance, Employee, ExpenseClaim, Holiday, HrmsPolicy, IncentiveEarning, IncentiveRule,
    LeaveBalance, LeaveRequest, LeaveType, Payslip, SalaryStructure,
)
from apps.hrms.services import leave as leave_svc
from apps.hrms.services.attendance import mark_check_in, sync_attendance_for, sync_attendance_for_date
from apps.hrms.services.incentives import compute_earnings_for
from apps.hrms.services.payroll import build_payslip, finalize_blockers, run_payroll

pytestmark = pytest.mark.django_db
MON_TO_SAT = [0, 1, 2, 3, 4, 5]
SEP = date(2026, 9, 1)
OCT = date(2026, 10, 1)


def emp(code, joined=date(2025, 1, 1), struct_from=date(2025, 1, 1), role="agent", basic="30000"):
    a = Agent.objects.create(name=f"A {code}", email=f"{code.lower()}@t.l", role=role,
                             working_days=MON_TO_SAT)
    e = Employee.objects.create(agent=a, employee_code=code, date_of_joining=joined)
    if struct_from:
        SalaryStructure.objects.create(employee=e, effective_from=struct_from, basic=Decimal(basic))
    return e


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(email="adm@t.l", name="Adm", password="Pw@12345678")


def call(view, method, user, data=None, **kw):
    req = getattr(APIRequestFactory(), method)("/x/", data or {}, format="json")
    force_authenticate(req, user=user)
    req.has_feature = lambda k: True
    r = view.as_view()(req, **kw)
    r.render()
    return r


def leave_type(name="CL", quota="12", paid=True, **kw):
    return LeaveType.objects.create(name=name, annual_quota_days=Decimal(quota), is_paid=paid, **kw)


def request_leave(e, t, start, end, half_day=False):
    return LeaveRequest.objects.create(employee=e, leave_type=t, start_date=start, end_date=end,
                                       days=Decimal("1"), half_day=half_day)


# ============================================================
# Pay and money
# ============================================================

def test_h1_a_mid_month_run_does_not_pay_the_days_still_to_come():
    e = emp("H1")
    slip = build_payslip(e, OCT, today=date(2026, 10, 9))
    days = slip.breakdown["attendance"]
    assert days["upcoming"] == 22
    # 1–9 Oct: eight unrecorded working days and Sunday the 4th.
    assert slip.payable_days == Decimal("9")
    assert slip.gross_earnings == (Decimal("30000") * 9 / 31).quantize(Decimal("0.01"))
    assert "isn't over yet" in finalize_blockers(slip, today=date(2026, 10, 9))
    # Built early, the draft still can't be finalized after the month ends.
    assert "Run payroll again" in finalize_blockers(slip, today=date(2026, 11, 2))
    slip = build_payslip(e, OCT, today=date(2026, 11, 2))
    assert slip.breakdown["upcoming_days"] == 0
    assert finalize_blockers(slip, today=date(2026, 11, 2)) is None


def test_h2_a_draft_payslip_does_not_freeze_incentives():
    from apps.calls.models import CallLog

    e = emp("H2")
    rule = IncentiveRule.objects.create(name="Talk", metric="connected_calls", per_unit_amount=Decimal("10"))
    build_payslip(e, SEP)  # draft, links the (zero) earning
    for _ in range(5):
        CallLog.objects.create(agent=e.agent, phone_number="+919800000001", is_connected=True,
                               started_at=timezone.make_aware(datetime(2026, 9, 15, 11)))
    compute_earnings_for(e, SEP)
    earning = IncentiveEarning.objects.get(employee=e, rule=rule)
    assert earning.units == 5 and earning.amount == Decimal("50.00")
    slip = build_payslip(e, SEP)
    assert slip.incentives_amount == Decimal("50.00")

    # Once finalized it is frozen.
    Payslip.objects.filter(pk=slip.pk).update(status=PayslipStatus.FINALIZED)
    CallLog.objects.create(agent=e.agent, phone_number="+919800000001", is_connected=True,
                           started_at=timezone.make_aware(datetime(2026, 9, 16, 11)))
    compute_earnings_for(e, SEP)
    assert IncentiveEarning.objects.get(pk=earning.pk).units == 5


def test_h3_a_sale_recorded_by_call_outcome_counts_for_incentives():
    from apps.calls.disposition_defaults import upgrade_dispositions
    from apps.calls.models import CallDisposition, CallLog
    from apps.leads.models import Lead

    upgrade_dispositions(CallDisposition)
    e = emp("H3")
    IncentiveRule.objects.create(name="Conv", metric="converted_leads", per_unit_amount=Decimal("500"))
    lead = Lead.objects.create(name="L", phone="+919800000002", assigned_to=e.agent, status="interested")
    CallLog.objects.create(agent=e.agent, lead=lead, phone_number=lead.phone, is_connected=True,
                           disposition=CallDisposition.objects.get(slug="converted"))
    lead.refresh_from_db()
    assert lead.status == "converted"
    [earning] = compute_earnings_for(e, timezone.localdate())
    assert earning.units == 1 and earning.amount == Decimal("500.00")

    # Another call on the already-converted lead is not a second sale.
    CallLog.objects.create(agent=e.agent, lead=lead, phone_number=lead.phone, is_connected=True,
                           disposition=CallDisposition.objects.get(slug="converted"))
    [earning] = compute_earnings_for(e, timezone.localdate())
    assert earning.units == 1


def test_h4_a_new_joiners_first_month_is_paid():
    e = emp("H4", joined=date(2026, 9, 11), struct_from=date(2026, 9, 29))
    slip = build_payslip(e, SEP)
    days = slip.breakdown["attendance"]
    assert days["not_employed"] == 10
    assert slip.payable_days == Decimal("20")  # 11–30 Sep, all unrecorded or Sundays
    assert slip.gross_earnings == Decimal("20000.00")


def test_h5_a_mid_month_raise_pays_the_new_rate_from_its_date():
    e = emp("H5")
    SalaryStructure.objects.create(employee=e, effective_from=date(2026, 9, 15), basic=Decimal("60000"))
    slip = build_payslip(e, SEP)
    # 14 days at 30,000 and 16 at 60,000, over 30.
    assert slip.gross_earnings == Decimal("46000.00")
    assert len(slip.breakdown["structures"]) == 2
    assert slip.breakdown["earnings_full"]["basic"] == "60000.00"


def test_h6_a_claim_from_an_already_paid_month_is_reimbursed_next_month():
    e = emp("H6")
    build_payslip(e, SEP).finalize()
    claim = ExpenseClaim.objects.create(employee=e, date=date(2026, 9, 28), category="travel",
                                        amount=Decimal("700"), status=ApprovalStatus.APPROVED)
    oct_slip = build_payslip(e, OCT, today=date(2026, 10, 31))
    claim.refresh_from_db()
    assert oct_slip.reimbursements_amount == Decimal("700") and claim.reimbursed_in == oct_slip


def test_h7_finalize_refuses_a_paid_slip(admin):
    e = emp("H7")
    slip = build_payslip(e, SEP)
    Payslip.objects.filter(pk=slip.pk).update(status=PayslipStatus.PAID, paid_at=timezone.now())
    r = call(hv.PayslipFinalizeView, "post", admin, pk=slip.pk)
    slip.refresh_from_db()
    assert r.status_code == 400 and slip.status == PayslipStatus.PAID


def test_h8_structures_and_payslips_can_be_corrected(admin):
    e = emp("H8")
    structure = e.salary_structures.get()
    r = call(hv.SalaryStructureDetailView, "patch", admin, {"basic": "32000"}, pk=structure.pk)
    assert r.status_code == 200, r.data

    claim = ExpenseClaim.objects.create(employee=e, date=date(2026, 9, 5), category="travel",
                                        amount=Decimal("100"), status=ApprovalStatus.APPROVED)
    slip = build_payslip(e, SEP)
    call(hv.PayslipFinalizeView, "post", admin, pk=slip.pk)
    slip.refresh_from_db()
    assert slip.status == PayslipStatus.FINALIZED

    # A structure a finalized slip used is locked.
    r = call(hv.SalaryStructureDetailView, "patch", admin, {"basic": "1"}, pk=structure.pk)
    assert r.status_code == 400 and r.data["error"] == "in_use"
    r = call(hv.SalaryStructureDetailView, "delete", admin, pk=structure.pk)
    assert r.status_code == 400

    # Reopen, then delete the draft: the claim is released.
    r = call(hv.PayslipDetailView, "delete", admin, pk=slip.pk)
    assert r.status_code == 400
    r = call(hv.PayslipReopenView, "post", admin, pk=slip.pk)
    assert r.status_code == 200 and r.data["status"] == PayslipStatus.DRAFT
    r = call(hv.PayslipDetailView, "delete", admin, pk=slip.pk)
    assert r.status_code == 204
    claim.refresh_from_db()
    assert claim.reimbursed_in is None

    # A paid slip can't be reopened.
    slip = build_payslip(e, SEP)
    Payslip.objects.filter(pk=slip.pk).update(status=PayslipStatus.PAID)
    assert call(hv.PayslipReopenView, "post", admin, pk=slip.pk).status_code == 400


def test_h9_impossible_salary_structures_are_refused(admin):
    e = emp("H9")
    r = call(hv.SalaryStructureListCreateView, "post", admin,
             {"employee": e.pk, "effective_from": "2026-11-01", "basic": "-5000"})
    assert r.status_code == 400
    r = call(hv.SalaryStructureListCreateView, "post", admin,
             {"employee": e.pk, "effective_from": "2026-11-01", "basic": "0", "tds": "90000"})
    assert r.status_code == 400
    r = call(hv.SalaryStructureListCreateView, "post", admin,
             {"employee": e.pk, "effective_from": "2026-11-01", "basic": "20000", "tds": "2000"})
    assert r.status_code == 201, r.data


def test_h10_nightly_jobs_run_after_midnight_ist():
    from django.conf import settings

    from config.celery import app

    assert settings.CELERY_TIMEZONE == "Asia/Kolkata"
    schedule = app.conf.beat_schedule
    sync = schedule["hrms-sync-attendance"]["schedule"]
    incentives = schedule["hrms-recompute-incentives"]["schedule"]
    assert sync.hour == {0} and sync.minute == {30}
    assert incentives.hour == {1} and incentives.minute == {30}


def test_h11_adding_or_removing_a_holiday_updates_attendance(admin):
    e = emp("H11")
    day = date(2026, 10, 2)
    Attendance.objects.create(employee=e, date=day, status=AttendanceStatus.ABSENT,
                              source=AttendanceSource.AUTO)
    r = call(hv.HolidayListCreateView, "post", admin, {"date": day.isoformat(), "name": "Gandhi Jayanti"})
    assert r.status_code == 201
    assert Attendance.objects.get(employee=e, date=day).status == AttendanceStatus.HOLIDAY

    r = call(hv.HolidayDetailView, "delete", admin, pk=r.data["id"])
    assert r.status_code == 204
    assert Attendance.objects.get(employee=e, date=day).status == AttendanceStatus.ABSENT


# ============================================================
# Leave
# ============================================================

def test_h12_not_enrolled_gets_a_message_not_a_server_error(admin):
    t = leave_type()
    r = call(hv.LeaveRequestListCreateView, "post", admin,
             {"leave_type": t.pk, "start_date": "2026-11-02", "end_date": "2026-11-02"})
    assert r.status_code == 400 and r.data["error"] == "not_enrolled"
    r = call(hv.ExpenseClaimListCreateView, "post", admin,
             {"date": "2026-10-01", "category": "travel", "amount": "10"})
    assert r.status_code == 400 and r.data["error"] == "not_enrolled"


def test_h13_hr_can_file_for_an_employee(admin):
    e = emp("H13")
    t = leave_type()
    r = call(hv.LeaveRequestListCreateView, "post", admin,
             {"employee": e.pk, "leave_type": t.pk, "start_date": "2026-11-02", "end_date": "2026-11-03"})
    assert r.status_code == 201, r.data
    assert LeaveRequest.objects.get().employee == e
    r = call(hv.ExpenseClaimListCreateView, "post", admin,
             {"employee": e.pk, "date": "2026-10-01", "category": "travel", "amount": "10"})
    assert r.status_code == 201, r.data


def test_h14_leave_days_are_counted_from_the_dates(admin):
    e = emp("H14")
    t = leave_type()
    Holiday.objects.create(date=date(2026, 11, 3), name="Hol")
    # Mon 2 – Sun 8 Nov: 7 calendar days, one holiday, one Sunday → 5. "0.5" is ignored.
    r = call(hv.LeaveRequestListCreateView, "post", e.agent,
             {"leave_type": t.pk, "start_date": "2026-11-02", "end_date": "2026-11-08", "days": "0.5"})
    assert r.status_code == 201, r.data
    assert Decimal(r.data["days"]) == Decimal("5")

    r = call(hv.LeaveRequestListCreateView, "post", e.agent,
             {"leave_type": t.pk, "start_date": "2026-11-10", "end_date": "2026-11-10", "half_day": True})
    assert r.status_code == 201 and Decimal(r.data["days"]) == Decimal("0.5")

    r = call(hv.LeaveRequestListCreateView, "post", e.agent,
             {"leave_type": t.pk, "start_date": "2026-11-15", "end_date": "2026-11-15"})
    assert r.status_code == 400  # a Sunday: no working days

    r = call(hv.LeaveRequestListCreateView, "post", e.agent,
             {"leave_type": t.pk, "start_date": "2026-11-16", "end_date": "2026-11-17", "half_day": True})
    assert r.status_code == 400


def test_h15_approval_never_erases_a_worked_day():
    e = emp("H15")
    t = leave_type()
    Attendance.objects.create(employee=e, date=date(2026, 9, 8), status=AttendanceStatus.PRESENT,
                              worked_seconds=8 * 3600, source=AttendanceSource.AUTO)
    lv = request_leave(e, t, date(2026, 9, 8), date(2026, 9, 8))
    with pytest.raises(leave_svc.LeaveError, match="08 Sep 2026"):
        leave_svc.approve_leave(lv, None)
    assert Attendance.objects.get(employee=e, date=date(2026, 9, 8)).worked_seconds == 8 * 3600


def test_h15_half_day_leave_keeps_the_worked_half():
    e = emp("H15B")
    t = leave_type()
    Attendance.objects.create(employee=e, date=date(2026, 9, 9), status=AttendanceStatus.HALF_DAY,
                              worked_seconds=4 * 3600, source=AttendanceSource.AUTO)
    lv = request_leave(e, t, date(2026, 9, 9), date(2026, 9, 9), half_day=True)
    leave_svc.approve_leave(lv, None)
    row = Attendance.objects.get(employee=e, date=date(2026, 9, 9))
    assert row.status == AttendanceStatus.HALF_DAY and row.worked_seconds == 4 * 3600
    assert LeaveBalance.objects.get(employee=e).used_days == Decimal("0.5")
    days = build_payslip(e, SEP).breakdown["attendance"]
    assert days["half_day_leave"] == 1 and days["lop_days"] == "0"
    assert days["paid_leave_by_type"] == {"CL": 0.5}


def test_h16_leave_across_new_year_is_charged_to_both_years():
    e = emp("H16")
    t = leave_type()
    # Wed 30 Dec – Sat 2 Jan: 2 days in 2026, 2 in 2027.
    lv = request_leave(e, t, date(2026, 12, 30), date(2027, 1, 2))
    leave_svc.approve_leave(lv, None)
    assert LeaveBalance.objects.get(employee=e, year=2026).used_days == 2
    assert LeaveBalance.objects.get(employee=e, year=2027).used_days == 2
    assert lv.charged_days == {"2026": "2", "2027": "2"}
    leave_svc.cancel_leave(lv)
    assert LeaveBalance.objects.get(employee=e, year=2026).used_days == 0
    assert LeaveBalance.objects.get(employee=e, year=2027).used_days == 0


def test_h17_leave_in_a_finalized_month_cannot_be_cancelled():
    e = emp("H17")
    t = leave_type()
    lv = request_leave(e, t, date(2026, 9, 8), date(2026, 9, 8))
    leave_svc.approve_leave(lv, None)
    build_payslip(e, SEP).finalize()
    with pytest.raises(leave_svc.LeaveError, match="September 2026"):
        leave_svc.cancel_leave(lv)
    assert LeaveBalance.objects.get(employee=e, leave_type=t).used_days == 1


def test_h18_switched_off_types_and_impossible_dates_are_refused():
    e = emp("H18", joined=date(2026, 6, 1))
    off = leave_type("Old", quota="0", is_active=False)
    on = leave_type("CL")
    r = call(hv.LeaveRequestListCreateView, "post", e.agent,
             {"leave_type": off.pk, "start_date": "2026-11-02", "end_date": "2026-11-02"})
    assert r.status_code == 400
    r = call(hv.LeaveRequestListCreateView, "post", e.agent,
             {"leave_type": on.pk, "start_date": "2020-01-01", "end_date": "2020-01-03"})
    assert r.status_code == 400  # before joining
    build_payslip(e, SEP).finalize()
    r = call(hv.LeaveRequestListCreateView, "post", e.agent,
             {"leave_type": on.pk, "start_date": "2026-09-14", "end_date": "2026-09-14"})
    assert r.status_code == 400  # finalized month


def test_h19_hr_can_list_everyones_balances(admin):
    e1, e2 = emp("H19A"), emp("H19B")
    t = leave_type()
    for e in (e1, e2):
        LeaveBalance.objects.create(employee=e, leave_type=t, year=2026, allocated_days=Decimal("12"))
    r = call(hv.LeaveBalanceListView, "get", admin)
    assert len(r.data) == 2 and {row["employee_code"] for row in r.data} == {"H19A", "H19B"}


def test_h20_balance_admin_refuses_nonsense(admin):
    e = emp("H20")
    t = leave_type()
    r = call(hv.LeaveBalanceManageView, "post", admin,
             {"employee": e.pk, "leave_type": t.pk, "year": 2026, "allocated_days": "-3"})
    assert r.status_code == 400
    r = call(hv.LeaveBalanceManageView, "post", admin,
             {"employee": e.pk, "leave_type": t.pk, "year": 1890, "allocated_days": "3"})
    assert r.status_code == 400
    bal = LeaveBalance.objects.create(employee=e, leave_type=t, year=2026,
                                      allocated_days=Decimal("12"), used_days=Decimal("4"))
    r = call(hv.LeaveBalanceManageView, "patch", admin, {"used_days": "20"}, pk=bal.pk)
    bal.refresh_from_db()
    assert bal.used_days == Decimal("4")
    r = call(hv.LeaveBalanceManageView, "patch", admin, {"allocated_days": "2"}, pk=bal.pk)
    assert r.status_code == 400


def test_h21_leave_types_validate_and_can_be_switched_back_on(admin):
    r = call(hv.LeaveTypeListCreateView, "post", admin, {"name": "Neg", "annual_quota_days": "-5"})
    assert r.status_code == 400
    t = leave_type("Sick", is_active=False)
    r = call(hv.LeaveTypeListCreateView, "post", admin, {"name": "sick", "annual_quota_days": "5"})
    assert r.status_code == 400 and "switched off" in str(r.data)
    r = call(hv.LeaveTypeListCreateView, "get", admin)
    assert r.data == []
    req = APIRequestFactory().get("/x/?include_inactive=1")
    force_authenticate(req, user=admin)
    req.has_feature = lambda k: True
    r = hv.LeaveTypeListCreateView.as_view()(req)
    assert [row["name"] for row in r.data] == ["Sick"]
    r = call(hv.LeaveTypeDetailView, "patch", admin, {"is_active": True}, pk=t.pk)
    assert r.status_code == 200 and r.data["is_active"] is True


def test_h22_bulk_allocation_pro_rates_joiners_and_carries_forward(admin):
    old = emp("H22A")
    new = emp("H22B", joined=date(2026, 10, 15))
    cl = leave_type("CL", quota="12", carry_forward=True)
    LeaveBalance.objects.create(employee=old, leave_type=cl, year=2025,
                                allocated_days=Decimal("12"), used_days=Decimal("9"))
    r = call(hv.BulkAllocateLeaveView, "post", admin, {"year": 2026})
    assert r.status_code == 200 and r.data["carried_forward"] == 1
    assert LeaveBalance.objects.get(employee=old, year=2026).allocated_days == Decimal("15")
    # Joined in October: 3 of 12 months.
    assert LeaveBalance.objects.get(employee=new, year=2026).allocated_days == Decimal("3")


# ============================================================
# Attendance
# ============================================================

def test_h23_a_check_in_without_check_out_is_closed_by_the_nightly_sync():
    e = emp("H23")
    yesterday = timezone.localdate() - timedelta(days=1)
    at = timezone.make_aware(datetime.combine(yesterday, datetime.min.time()) + timedelta(hours=10))
    row = mark_check_in(e, at=at)
    assert row.status == AttendanceStatus.PRESENT
    sync_attendance_for(e, yesterday)
    row.refresh_from_db()
    assert row.status in (AttendanceStatus.ABSENT, AttendanceStatus.WEEK_OFF, AttendanceStatus.HOLIDAY)
    assert row.worked_seconds == 0


def test_h25_hr_can_add_a_missing_day(admin):
    e = emp("H25")
    r = call(hv.AttendanceListView, "post", admin,
             {"employee": e.pk, "date": "2026-09-08", "worked_seconds": 7 * 3600})
    assert r.status_code == 201, r.data
    assert r.data["status"] == AttendanceStatus.PRESENT and r.data["source"] == AttendanceSource.ADMIN
    r = call(hv.AttendanceListView, "post", admin, {"employee": e.pk, "date": "2026-09-08"})
    assert r.status_code == 400
    r = call(hv.AttendanceListView, "post", e.agent, {"employee": e.pk, "date": "2026-09-09"})
    assert r.status_code == 403


def test_h26_a_correction_cannot_move_a_row_and_rederives_status(admin):
    e, e2 = emp("H26A"), emp("H26B")
    row = Attendance.objects.create(employee=e, date=date(2026, 9, 8), status=AttendanceStatus.ABSENT)
    r = call(hv.AttendanceDetailView, "patch", admin, {"employee": e2.pk}, pk=row.pk)
    assert r.status_code == 400
    r = call(hv.AttendanceDetailView, "patch", admin, {"worked_seconds": 30000}, pk=row.pk)
    assert r.status_code == 200
    row.refresh_from_db()
    assert row.employee == e and row.status == AttendanceStatus.PRESENT


def test_h27_sync_reports_rows_it_kept():
    e = emp("H27")
    day = date(2026, 9, 8)
    Attendance.objects.create(employee=e, date=day, status=AttendanceStatus.PRESENT,
                              source=AttendanceSource.ADMIN)
    stats = {}
    assert sync_attendance_for_date(day, stats) == 0
    assert stats["kept"] == 1


def test_h29_present_and_half_day_hours_come_from_the_policy(admin):
    e = emp("H29")
    r = call(hv.HrmsPolicyView, "patch", admin, {"full_day_hours": "8", "half_day_hours": "4"})
    assert r.status_code == 200, r.data
    r = call(hv.HrmsPolicyView, "patch", admin, {"half_day_hours": "9"})
    assert r.status_code == 400
    r = call(hv.AttendanceListView, "post", admin,
             {"employee": e.pk, "date": "2026-09-08", "worked_seconds": 7 * 3600})
    assert r.data["status"] == AttendanceStatus.HALF_DAY


# ============================================================
# Employees, expenses, incentives
# ============================================================

def test_h30_employee_details_are_validated(admin):
    e = emp("H30")
    other = Agent.objects.create(name="B", email="b@t.l", role="agent")
    base = {"agent": other.pk, "employee_code": "H30B", "date_of_joining": "2026-05-01"}
    for bad in ({"pan": "NOTAPAN"}, {"bank_ifsc": "XX"}, {"uan": "abc"},
                {"date_of_exit": "2026-01-01"}, {"bank_account_number": "12"}):
        r = call(hv.EmployeeListCreateView, "post", admin, {**base, **bad})
        assert r.status_code == 400, bad
    r = call(hv.EmployeeListCreateView, "post", admin,
             {**base, "pan": "abcde1234f", "bank_ifsc": "sbin0001234", "uan": "1234 5678 9012"})
    assert r.status_code == 201, r.data
    assert r.data["pan"] == "ABCDE1234F" and r.data["uan"] == "123456789012"

    r = call(hv.EmployeeDetailView, "patch", admin, {"reporting_to": e.pk}, pk=e.pk)
    assert r.status_code == 400
    b = Employee.objects.get(employee_code="H30B")
    call(hv.EmployeeDetailView, "patch", admin, {"reporting_to": e.pk}, pk=b.pk)
    r = call(hv.EmployeeDetailView, "patch", admin, {"reporting_to": b.pk}, pk=e.pk)
    assert r.status_code == 400  # a loop


def test_h31_expense_claims_are_validated(admin):
    e = emp("H31")
    r = call(hv.ExpenseClaimListCreateView, "post", e.agent,
             {"date": "2030-01-01", "category": "travel", "amount": "10"})
    assert r.status_code == 400
    r = call(hv.ExpenseClaimListCreateView, "post", e.agent,
             {"date": "2026-10-01", "category": "travel", "amount": "99999999.99"})
    assert r.status_code == 400
    policy = HrmsPolicy.current()
    policy.expense_receipt_above = Decimal("500")
    policy.save()
    r = call(hv.ExpenseClaimListCreateView, "post", e.agent,
             {"date": "2026-10-01", "category": "travel", "amount": "800"})
    assert r.status_code == 400 and "receipt" in str(r.data)
    r = call(hv.ExpenseClaimListCreateView, "post", e.agent,
             {"date": "2026-10-01", "category": "travel", "amount": "400"})
    assert r.status_code == 201


def test_h32_incentive_rules_are_validated(admin):
    for bad in ({"per_unit_amount": "-10"}, {"min_units": "-1"},
                {"applies_to_roles": ["astronaut"]},
                {"metric": "revenue", "per_unit_amount": "150"}):
        data = {"name": "R", "metric": "connected_calls", "per_unit_amount": "10", **bad}
        r = call(hv.IncentiveRuleListCreateView, "post", admin, data)
        assert r.status_code == 400, bad
    r = call(hv.IncentiveRuleListCreateView, "post", admin,
             {"name": "R", "metric": "connected_calls", "per_unit_amount": "10", "applies_to_roles": ["agent"]})
    assert r.status_code == 201


def test_h33_switching_a_rule_off_drops_its_unpaid_earnings(admin):
    e = emp("H33")
    rule = IncentiveRule.objects.create(name="X", metric="connected_calls", per_unit_amount=Decimal("10"))
    IncentiveEarning.objects.create(employee=e, rule=rule, period_month=SEP, units=3, amount=Decimal("30"))
    r = call(hv.IncentiveRuleDetailView, "patch", admin, {"is_active": False}, pk=rule.pk)
    assert r.status_code == 200
    assert not IncentiveEarning.objects.filter(rule=rule).exists()
    assert build_payslip(e, SEP).incentives_amount == 0


def test_h35_dashboard_counts_what_you_can_act_on():
    hr = emp("H35", role="hr")
    t = leave_type()
    request_leave(hr, t, date(2026, 11, 2), date(2026, 11, 2))
    gone = emp("H35X")
    gone.is_active = False
    gone.save()
    Attendance.objects.create(employee=gone, date=timezone.localdate(), status=AttendanceStatus.PRESENT)
    r = call(hv.HRMSDashboardView, "get", hr.agent)
    assert r.data["pending"]["leave"] == 0
    assert r.data["attendance_today"]["present"] == 0


def test_h36_dashboard_shows_reimbursements(admin):
    e = emp("H36")
    ExpenseClaim.objects.create(employee=e, date=date(2026, 9, 5), category="travel",
                                amount=Decimal("5000"), status=ApprovalStatus.APPROVED)
    build_payslip(e, SEP)
    req = APIRequestFactory().get("/x/?month=2026-09")
    force_authenticate(req, user=admin)
    req.has_feature = lambda k: True
    r = hv.HRMSDashboardView.as_view()(req)
    assert Decimal(r.data["payroll"]["reimbursements"]) == Decimal("5000")


def test_h38_employees_without_a_structure_are_listed_separately():
    emp("H38", struct_from=None)
    result = run_payroll(SEP)
    assert result["errors"] == []
    assert result["missing_structure"][0]["employee_code"] == "H38"
