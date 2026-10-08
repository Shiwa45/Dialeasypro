"""
Calls: outcomes in two groups (connected / not connected), and the new
default set for every tenant.

1. CallDisposition.category, is_system, sets_dnd. marks_connected stays,
   derived from category, for older app builds.
2. (0008) Every tenant's outcomes are upgraded in place.
3. CallLog.lead_label keeps the lead's name on the call; client_call_id
   makes a retried save return the call already saved.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0007_default_working_days"),
        ("calls", "0006_disposition_marks_connected"),
        ("leads", "0008_followup_is_auto"),
    ]

    operations = [
        migrations.AddField(
            model_name="calldisposition",
            name="category",
            field=models.CharField(
                choices=[
                    ("connected", "Connected (call answered)"),
                    ("not_connected", "Not connected (call not answered)"),
                ],
                db_index=True,
                default="connected",
                help_text="Connected (call answered) or not connected.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="calldisposition",
            name="is_system",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="calldisposition",
            name="sets_dnd",
            field=models.BooleanField(
                default=False,
                help_text="Mark the lead Do Not Disturb when a call is saved with this outcome.",
            ),
        ),
        migrations.AddField(
            model_name="calllog",
            name="client_call_id",
            field=models.CharField(
                blank=True, db_index=True, default="", max_length=64
            ),
        ),
        migrations.AddField(
            model_name="calllog",
            name="lead_label",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AlterField(
            model_name="calldisposition",
            name="lead_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("new", "New"),
                    ("attempted", "Attempted"),
                    ("contacted", "Contacted"),
                    ("interested", "Interested"),
                    ("not_interested", "Not Interested"),
                    ("follow_up", "Follow-up Scheduled"),
                    ("negotiation", "In Negotiation"),
                    ("converted", "Converted / Won"),
                    ("lost", "Lost"),
                    ("duplicate", "Duplicate"),
                    ("invalid", "Invalid / Junk"),
                ],
                default="",
                help_text="Move the lead to this status when a call is saved with this outcome. Blank = leave it.",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="calldisposition",
            name="marks_connected",
            field=models.BooleanField(
                blank=True,
                default=None,
                help_text="Derived from category — kept for older app builds.",
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="calllog",
            constraint=models.UniqueConstraint(
                condition=models.Q(("client_call_id", ""), _negated=True),
                fields=("agent", "client_call_id"),
                name="calllog_unique_client_call_id",
            ),
        ),
    ]
