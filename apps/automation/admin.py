"""TeleCRM Backend — apps/automation/admin.py"""
from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.automation.models import Workflow, WorkflowRun


@admin.register(Workflow)
class WorkflowAdmin(ModelAdmin):
    list_display = ["name", "trigger", "is_active", "runs_count", "last_run_at"]
    list_filter = ["trigger", "is_active"]
    search_fields = ["name"]


@admin.register(WorkflowRun)
class WorkflowRunAdmin(ModelAdmin):
    list_display = ["workflow", "lead", "status", "current_step", "has_errors", "created_at"]
    list_filter = ["status", "has_errors"]
    readonly_fields = ["log", "context"]
