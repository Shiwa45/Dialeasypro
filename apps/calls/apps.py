"""
TeleCRM Backend — apps/calls/apps.py
"""
from django.apps import AppConfig


class CallsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.calls"
    verbose_name = "Calls"

    def ready(self):
        import apps.calls.signals  # noqa: F401
