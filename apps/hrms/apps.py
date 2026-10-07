"""
TeleCRM Backend — apps/hrms/apps.py
"""
from django.apps import AppConfig


class HRMSConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.hrms"
    verbose_name = "HRMS"

    def ready(self):
        from apps.hrms import signals  # noqa: F401 — connects the receivers
