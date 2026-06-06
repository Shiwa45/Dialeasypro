"""
TeleCRM Backend — apps/leads/urls.py

MVT URL patterns for the tenant admin leads section.
These get included into apps/authentication/urls.py under the
'tenant_admin' namespace, so all lead URLs are prefixed /crm/leads/
"""
from django.urls import path

from apps.leads.mvt_views import (
    FollowUpCreateMVTView,
    LeadCreateMVTView,
    LeadDetailMVTView,
    LeadImportMVTView,
    LeadImportStatusMVTView,
    LeadKanbanMVTView,
    LeadListMVTView,
    LeadNoteCreateMVTView,
    LeadStatusUpdateMVTView,
    LeadUpdateMVTView,
)

# These are namespaced under tenant_admin (included in authentication/urls.py)
urlpatterns = [
    # Lead list & pipeline views
    path("", LeadListMVTView.as_view(), name="lead_list"),
    path("kanban/", LeadKanbanMVTView.as_view(), name="lead_kanban"),

    # Lead CRUD
    path("add/", LeadCreateMVTView.as_view(), name="lead_create"),
    path("<int:pk>/", LeadDetailMVTView.as_view(), name="lead_detail"),
    path("<int:pk>/edit/", LeadUpdateMVTView.as_view(), name="lead_update"),

    # HTMX partials
    path("<int:pk>/status/", LeadStatusUpdateMVTView.as_view(), name="lead_status_update"),
    path("<int:lead_id>/followup/add/", FollowUpCreateMVTView.as_view(), name="lead_followup_add"),
    path("<int:lead_id>/note/add/", LeadNoteCreateMVTView.as_view(), name="lead_note_add"),

    # Import
    path("import/", LeadImportMVTView.as_view(), name="lead_import"),
    path("import/<uuid:pk>/", LeadImportStatusMVTView.as_view(), name="lead_import_status"),
]
