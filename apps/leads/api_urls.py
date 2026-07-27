"""
TeleCRM Backend — apps/leads/api_urls.py

DRF API URL patterns for the leads app.
Mounted at: /api/v1/leads/  (in config/urls.py)
"""
from django.urls import path

from apps.leads.views import (
    LeadExportView,
    AvailableQueuesView,
    CallQueueDetailView,
    CallQueueListCreateView,
    CustomFieldListView,
    FollowUpCompleteView,
    FollowUpListCreateView,
    LeadActivityListView,
    LeadBulkAssignView,
    LeadDistributeView,
    LeadFlushView,
    LeadDashboardStatsView,
    LeadDetailView,
    LeadImportJobDetailView,
    LeadImportPreviewView,
    LeadImportView,
    LeadListCreateView,
    LeadNoteListCreateView,
    LeadPipelineView,
    LeadStatusUpdateView,
    LeadUnassignByAgentView,
    QueuePullNextView,
    QueueReleaseView,
)

urlpatterns = [
    # ---- Call Queues (defined before <int:pk>/ to avoid route clashes) ----
    path("queues/", CallQueueListCreateView.as_view(), name="api_queue_list"),
    path("queues/available/", AvailableQueuesView.as_view(), name="api_queue_available"),
    path("queues/release/", QueueReleaseView.as_view(), name="api_queue_release"),
    path("queues/<int:pk>/", CallQueueDetailView.as_view(), name="api_queue_detail"),
    path("queues/<int:pk>/pull/", QueuePullNextView.as_view(), name="api_queue_pull"),

    # ---- Lead CRUD -----------------------------------------
    path("", LeadListCreateView.as_view(), name="api_lead_list"),
    path("<int:pk>/", LeadDetailView.as_view(), name="api_lead_detail"),
    path("<int:pk>/status/", LeadStatusUpdateView.as_view(), name="api_lead_status"),

    # ---- Bulk operations -----------------------------------
    path("bulk-assign/", LeadBulkAssignView.as_view(), name="api_lead_bulk_assign"),
    path("distribute/", LeadDistributeView.as_view(), name="api_lead_distribute"),
    path("flush/", LeadFlushView.as_view(), name="api_lead_flush"),
    path("unassign-by-agent/", LeadUnassignByAgentView.as_view(), name="api_lead_unassign_by_agent"),

    # ---- Follow-ups ----------------------------------------
    path("<int:lead_id>/followups/", FollowUpListCreateView.as_view(), name="api_followup_list"),
    path("followups/<int:pk>/complete/", FollowUpCompleteView.as_view(), name="api_followup_complete"),

    # ---- Notes & Activity ----------------------------------
    path("<int:lead_id>/notes/", LeadNoteListCreateView.as_view(), name="api_lead_notes"),
    path("<int:lead_id>/activities/", LeadActivityListView.as_view(), name="api_lead_activities"),

    # ---- Import --------------------------------------------
    path("import/preview/", LeadImportPreviewView.as_view(), name="api_lead_import_preview"),
    path("import/", LeadImportView.as_view(), name="api_lead_import"),
    path("import/<uuid:pk>/", LeadImportJobDetailView.as_view(), name="api_lead_import_status"),

    # ---- Custom Fields -------------------------------------
    path("custom-fields/", CustomFieldListView.as_view(), name="api_custom_fields"),

    # ---- Export -------------------------------------------
    path("export/", LeadExportView.as_view(), name="api_lead_export"),

    # ---- Dashboard & Pipeline ------------------------------
    path("stats/", LeadDashboardStatsView.as_view(), name="api_lead_stats"),
    path("pipeline/", LeadPipelineView.as_view(), name="api_lead_pipeline"),
]
