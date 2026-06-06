"""
TeleCRM Backend — apps/plans/apps.py
Django AppConfig — connects signals on startup.
"""
from django.apps import AppConfig


class PlansConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.plans"
    verbose_name = "Plans"

    def ready(self):
        """Import signals so Django connects them on startup."""
        try:
            import apps.plans.signals  # noqa: F401
        except ImportError:
            pass
