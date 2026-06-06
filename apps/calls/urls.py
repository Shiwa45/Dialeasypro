"""
TeleCRM Backend — apps/calls/urls.py
MVT URL patterns for tenant admin call management.
Mounted at: /crm/calls/ (via config/urls.py)
"""
from django.urls import path
from apps.calls.mvt_views import (
    CallListMVTView,
    CallDetailMVTView,
    CallStatsMVTView,
    ManualCallLogMVTView,
)

urlpatterns = [
    path("", CallListMVTView.as_view(), name="call_list"),
    path("<uuid:pk>/", CallDetailMVTView.as_view(), name="call_detail"),
    path("log/", ManualCallLogMVTView.as_view(), name="call_log_manual"),
    path("stats/", CallStatsMVTView.as_view(), name="call_stats"),
]
