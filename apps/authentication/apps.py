"""
TeleCRM Backend — apps/authentication/apps.py
Django AppConfig — connects signals on startup.
"""
from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.authentication"
    verbose_name = "Authentication"

    def ready(self):
        """Import signals so Django connects them on startup."""
        try:
            import apps.authentication.signals  # noqa: F401
        except ImportError:
            pass
