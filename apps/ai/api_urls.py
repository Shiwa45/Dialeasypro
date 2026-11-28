"""
TeleCRM Backend — apps/ai/api_urls.py
Mounted at: /api/v1/ai/
"""
from django.urls import path

from apps.ai.views import (
    AIUsageView,
    BackfillView,
    CallAnalyseView,
    CallInsightView,
    CallSummariseView,
    CallTranscribeView,
    CallTranscriptView,
    InsightListView,
    RecordedCallListView,
)

urlpatterns = [
    path("calls/<uuid:pk>/transcript/", CallTranscriptView.as_view(), name="api_ai_transcript"),
    path("calls/<uuid:pk>/transcribe/", CallTranscribeView.as_view(), name="api_ai_transcribe"),
    path("calls/<uuid:pk>/insight/", CallInsightView.as_view(), name="api_ai_insight"),
    path("calls/<uuid:pk>/analyse/", CallAnalyseView.as_view(), name="api_ai_analyse"),
    path("calls/<uuid:pk>/summarise/", CallSummariseView.as_view(), name="api_ai_summarise"),
    path("calls/", RecordedCallListView.as_view(), name="api_ai_recorded_calls"),

    path("insights/", InsightListView.as_view(), name="api_ai_insights"),
    path("backfill/", BackfillView.as_view(), name="api_ai_backfill"),
    path("usage/", AIUsageView.as_view(), name="api_ai_usage"),
]
