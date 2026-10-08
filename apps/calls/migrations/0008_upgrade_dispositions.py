"""
Calls: upgrade every tenant's call outcomes to the grouped default set.

A separate migration from the schema change (0007) so the indexes 0007 adds
are built before any rows change — PostgreSQL refuses to build an index on a
table with pending trigger events in the same transaction.

* The old defaults are renamed in place (their calls keep the link), new
  ones are added, and outcomes a tenant made get a group
  (apps/calls/disposition_defaults.py).
* Calls remember the lead's name (lead_label).
"""
from django.db import migrations
from django.db.models import OuterRef, Subquery


def forwards(apps, schema_editor):
    from apps.calls.disposition_defaults import upgrade_dispositions

    CallDisposition = apps.get_model("calls", "CallDisposition")
    # Only a tenant that already has outcomes is upgraded here; a brand-new
    # schema is seeded when the tenant is created (tenants/signals.py).
    if CallDisposition.objects.exists():
        upgrade_dispositions(CallDisposition)

    CallLog = apps.get_model("calls", "CallLog")
    Lead = apps.get_model("leads", "Lead")
    CallLog.objects.filter(lead__isnull=False, lead_label="").update(
        lead_label=Subquery(Lead.objects.filter(pk=OuterRef("lead_id")).values("name")[:1])
    )



class Migration(migrations.Migration):

    dependencies = [
        ("calls", "0007_disposition_groups"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
