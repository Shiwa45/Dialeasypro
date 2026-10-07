"""
Give existing call outcomes a lead status, and bring leads in line with them.

Until 0004 a call outcome never changed the lead: leads an agent had called
and marked "Interested" stayed at Attempted or Contacted, so the Leads
screen's Interested filter showed none of them.

1. Outcomes whose name or slug plainly means Interested, Not interested or
   Call back get that lead status. Tenants name their own outcomes, so this
   reads the words rather than a fixed slug list; anything ambiguous is left
   blank for an admin to set in Settings → Call Dispositions.
2. A lead still at New, Attempted or Contacted — never moved on by hand —
   takes the status of its most recent call outcome. Leads someone has
   already set further along are left alone.
"""
import re

from django.db import migrations
from django.db.models import OuterRef, Subquery

EARLY = ["new", "attempted", "contacted"]


def guess_status(slug, name):
    words = re.sub(r"[^a-z]+", " ", f"{slug} {name}".lower())
    words = f" {' '.join(words.split())} "
    if re.search(r" (not|no|non) interest", words) or " notinterested " in words:
        return "not_interested"
    if " interested " in words or " interest " in words:
        return "interested"
    if re.search(r" (call ?back|callback|call later|follow ?up|followup) ", words):
        return "follow_up"
    return ""


def forwards(apps, schema_editor):
    CallDisposition = apps.get_model("calls", "CallDisposition")
    CallLog = apps.get_model("calls", "CallLog")
    Lead = apps.get_model("leads", "Lead")

    for d in CallDisposition.objects.filter(lead_status=""):
        status = guess_status(d.slug, d.name)
        if status:
            CallDisposition.objects.filter(pk=d.pk).update(lead_status=status)

    latest = (
        CallLog.objects.filter(lead_id=OuterRef("pk"), disposition__isnull=False)
        .order_by("-started_at", "-pk")
        .values("disposition__lead_status")[:1]
    )
    leads = (
        Lead.objects.filter(is_deleted=False, status__in=EARLY)
        .annotate(outcome_status=Subquery(latest))
        .exclude(outcome_status__isnull=True)
        .exclude(outcome_status="")
    )
    for lead_id, status in leads.values_list("pk", "outcome_status").iterator():
        Lead.objects.filter(pk=lead_id, status__in=EARLY).exclude(status=status).update(
            status=status, has_been_worked=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("calls", "0004_disposition_lead_status"),
        ("leads", "0008_followup_is_auto"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
