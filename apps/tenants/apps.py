"""
TeleCRM Backend — apps/tenants/apps.py
Django AppConfig — connects signals on startup.
"""
from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenants"
    verbose_name = "Tenants"

    def ready(self):
        """Import signals so Django connects them on startup."""
        try:
            import apps.tenants.signals  # noqa: F401
        except ImportError:
            pass
