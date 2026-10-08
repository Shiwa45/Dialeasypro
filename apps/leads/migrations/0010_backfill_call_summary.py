"""
Leads: fill the call summary from call history.

1. dial_attempts, connected_calls, last_connected_at, last_disposition,
   last_call_connected from the lead's calls.
2. contact_count now counts ANSWERED calls (it went up on every unanswered
   dial too); recomputed from the calls.
3. A lead with an answered call that is still at Attempted ("never
   reached") moves to Contacted.
4. Leads with several open automatic follow-ups keep only the latest one.

Separate from 0009 so its indexes are built before rows change.
"""
from django.db import migrations
from django.db.models import Count, Max, OuterRef, Q, Subquery


def backfill(apps, schema_editor):
    Lead = apps.get_model("leads", "Lead")
    CallLog = apps.get_model("calls", "CallLog")
    FollowUp = apps.get_model("leads", "FollowUp")

    stats = (
        CallLog.objects.filter(lead__isnull=False)
        .order_by()
        .values("lead_id")
        .annotate(
            dials=Count("id"),
            connected=Count("id", filter=Q(is_connected=True)),
            last_dial=Max("started_at"),
            last_connected=Max("started_at", filter=Q(is_connected=True)),
        )
    )
    latest_outcome = (
        CallLog.objects.filter(lead=OuterRef("pk"), disposition__isnull=False)
        .order_by("-started_at").values("disposition_id")[:1]
    )
    latest_connected = (
        CallLog.objects.filter(lead=OuterRef("pk")).order_by("-started_at").values("is_connected")[:1]
    )
    for row in stats.iterator():
        lead = Lead.objects.filter(pk=row["lead_id"]).only(
            "pk", "status", "last_contacted_at", "last_dialed_at",
        ).first()
        if lead is None:
            continue
        updates = {
            "dial_attempts": row["dials"],
            "connected_calls": row["connected"],
            "contact_count": row["connected"],
            "last_connected_at": row["last_connected"],
        }
        if row["last_dial"] and (not lead.last_dialed_at or row["last_dial"] > lead.last_dialed_at):
            updates["last_dialed_at"] = row["last_dial"]
        if row["last_connected"] and (
            not lead.last_contacted_at or row["last_connected"] > lead.last_contacted_at
        ):
            updates["last_contacted_at"] = row["last_connected"]
        if row["connected"] and lead.status == "attempted":
            updates["status"] = "contacted"
        Lead.objects.filter(pk=lead.pk).update(**updates)

    Lead.objects.filter(calls__isnull=False).distinct().update(
        last_disposition_id=Subquery(latest_outcome),
        last_call_connected=Subquery(latest_connected),
    )

    # One open automatic follow-up per lead: keep the latest.
    dupes = (
        FollowUp.objects.filter(is_auto=True, is_completed=False)
        .order_by().values("lead_id").annotate(n=Count("id")).filter(n__gt=1)
    )
    for row in dupes:
        open_auto = list(
            FollowUp.objects.filter(lead_id=row["lead_id"], is_auto=True, is_completed=False)
            .order_by("-created_at").values_list("pk", flat=True)
        )
        FollowUp.objects.filter(pk__in=open_auto[1:]).update(
            is_completed=True, completion_notes="Replaced by a newer automatic follow-up.",
        )



class Migration(migrations.Migration):

    dependencies = [
        ("leads", "0009_lead_call_outcome_summary"),
        ("calls", "0008_upgrade_dispositions"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
