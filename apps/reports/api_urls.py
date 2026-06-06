"""TeleCRM Backend — apps/reports/api_urls.py"""
from django.urls import path
from apps.reports.views import (
    AgentPerformanceReportView, LeadSourceReportView,
    CallAnalyticsReportView, ConversionFunnelView, DailyActivityView,
)

urlpatterns = [
    path("agent-performance/", AgentPerformanceReportView.as_view(), name="api_report_agent"),
    path("lead-sources/", LeadSourceReportView.as_view(), name="api_report_sources"),
    path("call-analytics/", CallAnalyticsReportView.as_view(), name="api_report_calls"),
    path("conversion-funnel/", ConversionFunnelView.as_view(), name="api_report_funnel"),
    path("daily-activity/", DailyActivityView.as_view(), name="api_report_daily"),
]
