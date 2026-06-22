import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("offline", "Offline"), ("available", "Available"), ("on_call", "On Call"), ("wrap_up", "Wrap-up"), ("break", "Break")], db_index=True, default="offline", max_length=20)),
                ("since", models.DateTimeField(default=django.utils.timezone.now, help_text="When the current status began (for live duration display).")),
                ("last_seen", models.DateTimeField(db_index=True, default=django.utils.timezone.now, help_text="Last heartbeat — used to flip stale sessions to offline.")),
                ("session_started_at", models.DateTimeField(blank=True, null=True, help_text="When the current auto-dial session began (null when offline).")),
                ("current_call_id", models.PositiveIntegerField(blank=True, null=True)),
                ("current_lead_id", models.PositiveIntegerField(blank=True, null=True)),
                ("break_reason", models.CharField(blank=True, default="", max_length=100)),
                ("agent", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="work_status", to="authentication.agent")),
            ],
            options={
                "verbose_name": "Agent Status",
                "verbose_name_plural": "Agent Statuses",
            },
        ),
        migrations.CreateModel(
            name="AgentStatusLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("offline", "Offline"), ("available", "Available"), ("on_call", "On Call"), ("wrap_up", "Wrap-up"), ("break", "Break")], db_index=True, max_length=20)),
                ("started_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("duration_seconds", models.PositiveIntegerField(default=0)),
                ("break_reason", models.CharField(blank=True, default="", max_length=100)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="status_logs", to="authentication.agent")),
            ],
            options={
                "verbose_name": "Agent Status Log",
                "verbose_name_plural": "Agent Status Logs",
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="agentstatuslog",
            index=models.Index(fields=["agent", "started_at"], name="auth_agentstatuslog_agent_started_idx"),
        ),
    ]
