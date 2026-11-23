"""TeleCRM Backend — apps/automation/api_urls.py"""
from django.urls import path

from apps.automation.views import (
    WorkflowDetailView, WorkflowDuplicateView, WorkflowListCreateView, WorkflowOptionsView,
    WorkflowRunCancelView, WorkflowRunListView, WorkflowRunNowView, WorkflowToggleView,
)

urlpatterns = [
    path("workflows/", WorkflowListCreateView.as_view(), name="api_workflows"),
    path("workflows/<int:pk>/", WorkflowDetailView.as_view(), name="api_workflow_detail"),
    path("workflows/<int:pk>/toggle/", WorkflowToggleView.as_view(), name="api_workflow_toggle"),
    path("workflows/<int:pk>/duplicate/", WorkflowDuplicateView.as_view(), name="api_workflow_duplicate"),
    path("workflows/<int:pk>/run/", WorkflowRunNowView.as_view(), name="api_workflow_run_now"),
    path("runs/", WorkflowRunListView.as_view(), name="api_workflow_runs"),
    path("runs/<int:pk>/cancel/", WorkflowRunCancelView.as_view(), name="api_workflow_run_cancel"),
    path("options/", WorkflowOptionsView.as_view(), name="api_workflow_options"),
]
