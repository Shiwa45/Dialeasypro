"""
Give every owner account the admin role.

Agent.save() now keeps is_tenant_admin and role in step; this puts existing
rows right once. Idempotent; nothing to reverse.
"""
from django.db import migrations


def owners_are_admins(apps, schema_editor):
    Agent = apps.get_model("authentication", "Agent")
    Agent.objects.filter(is_tenant_admin=True).exclude(role="admin").update(role="admin")


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0004_notification"),
    ]

    operations = [
        migrations.RunPython(owners_are_admins, migrations.RunPython.noop),
    ]
