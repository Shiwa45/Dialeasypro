"""
Working days default to Monday–Saturday, and agents with none set get that.

An empty `working_days` used to mean every day was a working day, so HRMS
marked every Sunday absent and payroll took a day's pay for it. Existing
dialer-derived attendance rows for days that are now week-offs are corrected
too (admin corrections are left alone).
"""
from django.db import migrations, models

import apps.authentication.models

MON_SAT = [0, 1, 2, 3, 4, 5]


def forwards(apps, schema_editor):
    Agent = apps.get_model("authentication", "Agent")
    for agent in Agent.objects.only("id", "working_days"):
        if not agent.working_days:
            Agent.objects.filter(pk=agent.pk).update(working_days=MON_SAT)

    try:
        Attendance = apps.get_model("hrms", "Attendance")
    except LookupError:
        return
    rows = Attendance.objects.filter(status="absent", source="auto").select_related("employee__agent")
    for row in rows.iterator():
        days = row.employee.agent.working_days or MON_SAT
        if row.date.weekday() not in days:
            Attendance.objects.filter(pk=row.pk).update(status="week_off")


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0006_agent_role_recruiter"),
        ("hrms", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="agent",
            name="working_days",
            field=models.JSONField(
                blank=True,
                default=apps.authentication.models.default_working_days,
                help_text="List of working day numbers: 0=Mon, 1=Tue, ..., 6=Sun. E.g., [0,1,2,3,4] for Monday–Friday. Defaults to Monday–Saturday.",
            ),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
