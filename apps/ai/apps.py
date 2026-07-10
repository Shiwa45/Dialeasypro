"""
TeleCRM Backend — apps/ai/apps.py
"""
from django.apps import AppConfig


class AIConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    verbose_name = "AI Suite"
