"""
Calls: only Busy, Call back later and Voicemail book a follow-up automatically.

Every outcome with auto_followup_hours booked one — Interested, Ringing,
Switched off, Not reachable… — so nearly every lead called got a follow-up.
Among the built-in outcomes only Busy, Call back later and Voicemail keep
one (their default hours if none was set); the rest are cleared. Outcomes a
tenant added themselves keep their own setting. Follow-ups already booked are
left as they are.
"""
from django.db import migrations

DEFAULT_HOURS = {"busy": 1, "callback": 4, "voicemail": 24}


def forwards(apps, schema_editor):
    CallDisposition = apps.get_model("calls", "CallDisposition")
    CallDisposition.objects.filter(is_system=True).exclude(slug__in=list(DEFAULT_HOURS)).exclude(
        auto_followup_hours=None,
    ).update(auto_followup_hours=None)
    for slug, hours in DEFAULT_HOURS.items():
        CallDisposition.objects.filter(is_system=True, slug=slug, auto_followup_hours=None).update(
            auto_followup_hours=hours,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("calls", "0008_upgrade_dispositions"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
