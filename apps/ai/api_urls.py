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
    CallTranscribeView,
    CallTranscriptView,
    InsightListView,
)

urlpatterns = [
    path("calls/<uuid:pk>/transcript/", CallTranscriptView.as_view(), name="api_ai_transcript"),
    path("calls/<uuid:pk>/transcribe/", CallTranscribeView.as_view(), name="api_ai_transcribe"),
    path("calls/<uuid:pk>/insight/", CallInsightView.as_view(), name="api_ai_insight"),
    path("calls/<uuid:pk>/analyse/", CallAnalyseView.as_view(), name="api_ai_analyse"),

    path("insights/", InsightListView.as_view(), name="api_ai_insights"),
    path("backfill/", BackfillView.as_view(), name="api_ai_backfill"),
    path("usage/", AIUsageView.as_view(), name="api_ai_usage"),
]
