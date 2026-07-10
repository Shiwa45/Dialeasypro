"""
TeleCRM Backend — apps/erp/apps.py
"""
from django.apps import AppConfig


class ERPConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.erp"
    verbose_name = "ERP — Sales Ops"
