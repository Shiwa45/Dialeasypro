"""
Repair Lead.next_followup_at on existing data.

The field used to be recomputed from FUTURE follow-ups only, so every lead
whose overdue follow-up had been "cleared" by another save — including every
lead whose overdue reminder had been sent — is sitting with the wrong value.
The code is fixed (Lead.refresh_next_followup); this puts the existing rows
right once: each lead gets the earliest follow-up it still owes, or NULL.

One UPDATE per tenant schema, with a correlated subquery. Idempotent, so it is
safe to run again; there is nothing to reverse.
"""
from django.db import migrations
from django.db.models import OuterRef, Subquery


def repair(apps, schema_editor):
    Lead = apps.get_model("leads", "Lead")
    FollowUp = apps.get_model("leads", "FollowUp")

    earliest_owed = (
        FollowUp.objects.filter(lead=OuterRef("pk"), is_completed=False)
        .order_by("scheduled_at")
        .values("scheduled_at")[:1]
    )
    Lead.objects.update(next_followup_at=Subquery(earliest_owed))


class Migration(migrations.Migration):

    dependencies = [
        ("leads", "0006_batch_number_from_pk"),
    ]

    operations = [
        migrations.RunPython(repair, migrations.RunPython.noop),
    ]
