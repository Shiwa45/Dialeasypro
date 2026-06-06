"""
TeleCRM Backend — apps/core/apps.py
Django AppConfig — connects signals on startup.
"""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        """Import signals so Django connects them on startup."""
        try:
            import apps.core.signals  # noqa: F401
        except ImportError:
            pass
