"""
TeleCRM Backend — apps/calls/api_urls.py
Mounted at: /api/v1/calls/
"""
from django.urls import path
from apps.calls.views import (
    CallLogListCreateView, CallLogDetailView,
    ClickToCallView, CallDispositionListView, CallDispositionDetailView,
    CallProviderWebhookView, CallStatsView,
    CallRecordingUploadView,
)

urlpatterns = [
    path("", CallLogListCreateView.as_view(), name="api_call_list"),
    path("click-to-call/", ClickToCallView.as_view(), name="api_click_to_call"),
    path("dispositions/", CallDispositionListView.as_view(), name="api_call_dispositions"),
    path("dispositions/<int:pk>/", CallDispositionDetailView.as_view(), name="api_call_disposition_detail"),
    path("stats/", CallStatsView.as_view(), name="api_call_stats"),
    path("webhook/<str:provider>/", CallProviderWebhookView.as_view(), name="api_call_webhook"),
    path("<uuid:pk>/recording/", CallRecordingUploadView.as_view(), name="api_call_recording_upload"),
    path("<uuid:pk>/", CallLogDetailView.as_view(), name="api_call_detail"),
]
