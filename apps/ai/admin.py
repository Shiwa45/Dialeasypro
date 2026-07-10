"""
TeleCRM Backend — apps/ai/admin.py

Insights are model output, not data anyone should hand-edit. The admin is a
read-only viewer plus a "re-analyse" action.
"""
from django.contrib import admin, messages
from django.db import connection
from unfold.admin import ModelAdmin

from apps.ai.models import CallInsight
from apps.ai.tasks import analyse_call


@admin.register(CallInsight)
class CallInsightAdmin(ModelAdmin):
    list_display = [
        "call", "sentiment", "sentiment_score", "status",
        "suggested_disposition", "generated_at",
    ]
    list_filter = ["status", "sentiment", "generated_at"]
    search_fields = ["call__phone_number", "summary", "next_action"]
    raw_id_fields = ["call", "suggested_disposition"]
    actions = ["requeue_analysis"]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields if f.name != "id"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Re-analyse selected calls")
    def requeue_analysis(self, request, queryset):
        schema = connection.schema_name
        for call_id in queryset.values_list("call_id", flat=True):
            analyse_call.delay(schema, str(call_id))
        self.message_user(
            request, f"Queued {queryset.count()} call(s) for re-analysis.",
            messages.SUCCESS,
        )
