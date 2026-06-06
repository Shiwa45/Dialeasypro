"""
TeleCRM Backend — config/celery.py

Celery application configuration.
All async tasks and scheduled jobs are configured here.

Queues:
  default       → General tasks
  notifications → Emails, SMS, WhatsApp, push notifications
  bulk_ops      → Bulk WhatsApp/email campaigns
  integrations  → Lead source webhook processing (IndiaMART, Meta, etc.)
  call_uploads  → Call recording upload & transcription
"""
import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging, task_failure, task_prerun, task_success

# Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("telecrm")

# Load config from Django settings, namespace avoids conflicts
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all INSTALLED_APPS
app.autodiscover_tasks()

# ============================================================
# Celery Beat Periodic Task Schedule
# All times are UTC. India is UTC+5:30.
# 9 AM IST  = 3:30 AM UTC
# 8 PM IST  = 2:30 PM UTC
# 8:30 AM IST = 3:00 AM UTC
# 2 AM IST  = 8:30 PM UTC (previous day)
# 1 AM IST  = 7:30 PM UTC (previous day)
# ============================================================

app.conf.beat_schedule = {
    # ---- Trial Management ----------------------------------
    # Check trial expirations daily at 9 AM IST (3:30 AM UTC)
    "check-trial-expirations": {
        "task": "apps.plans.tasks.check_trial_expirations",
        "schedule": crontab(hour=3, minute=30),
        "options": {"queue": "default"},
    },

    # ---- Usage Stats ---------------------------------------
    # Sync lead/agent counts for all tenants daily at 1 AM IST (7:30 PM UTC prev day)
    "sync-tenant-usage-stats": {
        "task": "apps.tenants.tasks.sync_all_tenant_usage_stats",
        "schedule": crontab(hour=19, minute=30),
        "options": {"queue": "default"},
    },

    # ---- Agent Performance Summaries -----------------------
    # Trigger per-tenant daily performance summary at 8 PM IST (2:30 PM UTC)
    "send-daily-performance-summaries": {
        "task": "apps.authentication.tasks.dispatch_performance_summaries",
        "schedule": crontab(hour=14, minute=30),
        "options": {"queue": "notifications"},
    },

    # ---- Phase 3: Communications ------------------------------
    # Process scheduled bulk campaigns (check every 5 minutes)
    "launch-scheduled-campaigns": {
        "task": "apps.communications.tasks.launch_scheduled_campaigns",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "bulk_ops"},
    },

    # ---- Lead Scoring (nightly) ----------------------------
    "recalculate-lead-scores": {
        "task": "apps.leads.tasks.dispatch_lead_score_recalculation",
        "schedule": crontab(hour=0, minute=30),  # 6 AM IST
        "options": {"queue": "default"},
    },

    # ---- Follow-up Reminders (every 10 min) ----------------
    "dispatch-followup-reminders": {
        "task": "apps.authentication.tasks.dispatch_followup_reminders",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "notifications"},
    },

    # ---- Housekeeping --------------------------------------
    # Clean up expired login sessions every Sunday at 2 AM IST (8:30 PM UTC Sat)
    "cleanup-expired-sessions": {
        "task": "apps.authentication.tasks.cleanup_expired_sessions",
        "schedule": crontab(hour=20, minute=30, day_of_week="saturday"),
        "options": {"queue": "default"},
    },
    # Clean up expired JWT blacklist tokens weekly (Sunday 3 AM IST)
    "cleanup-expired-jwt-blacklist": {
        "task": "apps.authentication.tasks.cleanup_expired_jwt_blacklist",
        "schedule": crontab(hour=21, minute=30, day_of_week="saturday"),
        "options": {"queue": "default"},
    },
}

# ============================================================
# Task routing — send tasks to appropriate queues
# ============================================================
app.conf.task_routes = {
    "apps.authentication.tasks.send_agent_welcome_email": {"queue": "notifications"},
    "apps.authentication.tasks.send_daily_performance_summary": {"queue": "notifications"},
    "apps.authentication.tasks.send_followup_reminders": {"queue": "notifications"},
    "apps.tenants.tasks.send_tenant_welcome_email": {"queue": "notifications"},
    "apps.tenants.tasks.send_trial_expiry_warning": {"queue": "notifications"},
    "apps.plans.tasks.check_trial_expirations": {"queue": "default"},
    "apps.tenants.tasks.sync_all_tenant_usage_stats": {"queue": "default"},
}

# ============================================================
# Signal handlers for task monitoring
# ============================================================

@task_prerun.connect
def task_prerun_handler(task_id, task, args, kwargs, **_):
    """Log task start for monitoring."""
    import logging
    logger = logging.getLogger("celery.task")
    logger.debug(f"[Celery] START {task.name} | id={task_id}")


@task_failure.connect
def task_failure_handler(task_id, exception, traceback, einfo, **_):
    """Alert on task failure (hook for Sentry/Datadog in production)."""
    import logging
    logger = logging.getLogger("celery.task")
    logger.error(f"[Celery] FAILED id={task_id} | error={exception}")


@setup_logging.connect
def config_loggers(*args, **kwargs):
    """Let Django's logging config handle Celery logs too."""
    from logging.config import dictConfig
    from django.conf import settings
    if hasattr(settings, "LOGGING"):
        dictConfig(settings.LOGGING)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Health-check task — verifies Celery is running."""
    return f"Celery is healthy! Request: {self.request!r}"
