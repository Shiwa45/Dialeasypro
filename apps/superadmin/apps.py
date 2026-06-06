"""
TeleCRM Backend — apps/superadmin/apps.py
Django AppConfig — connects signals on startup.
"""
from django.apps import AppConfig


class SuperadminConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.superadmin"
    verbose_name = "Super Admin"

    def ready(self):
        """Import signals so Django connects them on startup."""
        try:
            import apps.superadmin.signals  # noqa: F401
        except ImportError:
            pass
