"""
Calls: let a call outcome decide whether the call was answered, and repair
call history that contradicted itself.

1. CallDisposition.marks_connected (True / False / None).
2. Existing outcomes get a value from their slug or name: the "Connected – …"
   family and Wrong Number mean answered; Not Reachable, Busy, Switched Off,
   Voicemail, No Answer mean not answered; anything else stays None.
3. Call history is brought in line: a call whose outcome now decides takes
   that answer, and a connected call
   stored with 0 s takes its duration from its own timestamps or recording.
"""
import re

from django.db import migrations, models

ANSWERED = re.compile(r"\b(connected|answered|interested|callback|call back|purchased|wrong number|wrong_number|wrong)\b")
NOT_ANSWERED = re.compile(
    r"\b(not reachable|not_reachable|unreachable|busy|switched off|switched_off|switch off|"
    r"voicemail|voice mail|no answer|no_answer|not answered|not connected|ringing|rnr)\b"
)


def guess(slug, name):
    text = f" {slug.replace('_', ' ').replace('-', ' ')} {name} ".lower()
    if NOT_ANSWERED.search(text):
        return False
    if ANSWERED.search(text):
        return True
    return None


def forwards(apps, schema_editor):
    CallDisposition = apps.get_model("calls", "CallDisposition")
    CallLog = apps.get_model("calls", "CallLog")
    CallRecording = apps.get_model("calls", "CallRecording")

    for d in CallDisposition.objects.filter(marks_connected__isnull=True):
        value = guess(d.slug or "", d.name or "")
        if value is not None:
            CallDisposition.objects.filter(pk=d.pk).update(marks_connected=value)

    for d in CallDisposition.objects.exclude(marks_connected__isnull=True):
        CallLog.objects.filter(disposition=d).exclude(is_connected=d.marks_connected).update(
            is_connected=d.marks_connected
        )

    recording_lengths = dict(
        CallRecording.objects.filter(duration_seconds__gt=0).values_list("call_id", "duration_seconds")
    )
    for call in CallLog.objects.filter(is_connected=True, duration_seconds=0).only(
        "id", "started_at", "connected_at", "ended_at"
    ).iterator():
        seconds = recording_lengths.get(call.id, 0)
        if not seconds and call.ended_at:
            begin = call.connected_at or call.started_at
            if begin and call.ended_at > begin:
                seconds = int((call.ended_at - begin).total_seconds())
        if seconds:
            CallLog.objects.filter(pk=call.pk).update(duration_seconds=seconds)


class Migration(migrations.Migration):

    dependencies = [
        ("calls", "0005_backfill_outcome_lead_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="calldisposition",
            name="marks_connected",
            field=models.BooleanField(
                blank=True, default=None, null=True,
                help_text="Answered (True), not answered (False), or let the dialer decide (empty).",
            ),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
