"""
TeleCRM Backend — apps/hrms/signals.py

Keep DRAFT payslips in step with attendance.

A draft payslip is a snapshot taken when payroll was run. Attendance kept
changing afterwards — the nightly dialer sync, admin corrections, approved
leave — and the draft never noticed: October's draft said 31/31 paid days
with five absences sitting in Attendance. Any change to an attendance row now
rebuilds that month's draft for that employee. Finalized and paid payslips
are never touched (build_payslip refuses to).
"""
import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.hrms.models import Attendance

logger = logging.getLogger(__name__)


def _refresh_draft(employee_id, day):
    from apps.hrms.constants import PayslipStatus
    from apps.hrms.models import Employee, Payslip
    from apps.hrms.services.payroll import build_payslip
    from apps.hrms.services.incentives import month_start

    month = month_start(day)
    if not Payslip.objects.filter(
        employee_id=employee_id, period_month=month, status=PayslipStatus.DRAFT,
    ).exists():
        return
    employee = Employee.objects.filter(pk=employee_id).first()
    if employee is None:
        return
    try:
        build_payslip(employee, month)
    except Exception as exc:  # noqa: BLE001 — a stale draft beats a failed attendance save
        logger.warning("[HRMS] Could not refresh draft payslip for %s %s: %s", employee_id, month, exc)


@receiver(post_save, sender=Attendance)
@receiver(post_delete, sender=Attendance)
def attendance_changed(sender, instance, **kwargs):
    employee_id, day = instance.employee_id, instance.date
    transaction.on_commit(lambda: _refresh_draft(employee_id, day))
