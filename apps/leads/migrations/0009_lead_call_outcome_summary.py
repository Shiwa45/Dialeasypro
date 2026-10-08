"""
Leads: a summary of each lead's calls, and the Invalid status.

New fields last_disposition, last_call_connected, last_connected_at,
dial_attempts, connected_calls — filled from call history by 0010.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calls", "0007_disposition_groups"),
        ("leads", "0008_followup_is_auto"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="connected_calls",
            field=models.PositiveIntegerField(
                default=0, help_text="Calls that were answered."
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="dial_attempts",
            field=models.PositiveIntegerField(
                default=0, help_text="Calls made to this lead."
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="last_call_connected",
            field=models.BooleanField(
                blank=True,
                help_text="Whether the most recent call was answered.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="last_connected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="lead",
            name="last_disposition",
            field=models.ForeignKey(
                blank=True,
                help_text="Outcome of the most recent call that has one.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="calls.calldisposition",
            ),
        ),
        migrations.AlterField(
            model_name="lead",
            name="contact_count",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Answered calls. Unanswered dials are in dial_attempts.",
            ),
        ),
        migrations.AlterField(
            model_name="lead",
            name="status",
            field=models.CharField(
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
                db_index=True,
                default="new",
                max_length=30,
            ),
        ),
    ]
