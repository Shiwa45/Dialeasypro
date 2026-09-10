"""
TeleCRM Backend — apps/recruitment/api_urls.py
Mounted at: /api/v1/recruitment/
"""
from django.urls import path

from apps.recruitment.views import (
    ApplicationActivityView,
    ApplicationBulkMoveView,
    ApplicationDetailView,
    ApplicationListCreateView,
    ApplicationMoveView,
    ApplicationStatusView,
    CandidateDetailView,
    CandidateDuplicateCheckView,
    CandidateListCreateView,
    InterviewDetailView,
    InterviewFeedbackView,
    InterviewListCreateView,
    JobOpeningDetailView,
    JobOpeningListCreateView,
    JobOpeningStatusView,
    OfferConvertView,
    OfferDetailView,
    OfferListCreateView,
    OfferStatusView,
    PipelineStageDetailView,
    PipelineStageListCreateView,
    PipelineStageReorderView,
    RecruitmentDashboardView,
    SuggestEmployeeCodeView,
)

urlpatterns = [
    # Dashboard
    path("dashboard/", RecruitmentDashboardView.as_view(), name="api_ats_dashboard"),

    # Job openings
    path("openings/", JobOpeningListCreateView.as_view(), name="api_ats_openings"),
    path("openings/<int:pk>/", JobOpeningDetailView.as_view(), name="api_ats_opening_detail"),
    path("openings/<int:pk>/status/", JobOpeningStatusView.as_view(), name="api_ats_opening_status"),

    # Pipeline stages
    path("stages/", PipelineStageListCreateView.as_view(), name="api_ats_stages"),
    path("stages/reorder/", PipelineStageReorderView.as_view(), name="api_ats_stage_reorder"),
    path("stages/<int:pk>/", PipelineStageDetailView.as_view(), name="api_ats_stage_detail"),

    # Candidates
    path("candidates/", CandidateListCreateView.as_view(), name="api_ats_candidates"),
    path("candidates/check-duplicate/", CandidateDuplicateCheckView.as_view(),
         name="api_ats_candidate_dupe_check"),
    path("candidates/<int:pk>/", CandidateDetailView.as_view(), name="api_ats_candidate_detail"),

    # Applications
    path("applications/", ApplicationListCreateView.as_view(), name="api_ats_applications"),
    path("applications/bulk-move/", ApplicationBulkMoveView.as_view(), name="api_ats_bulk_move"),
    path("applications/<int:pk>/", ApplicationDetailView.as_view(), name="api_ats_application_detail"),
    path("applications/<int:pk>/move/", ApplicationMoveView.as_view(), name="api_ats_application_move"),
    path("applications/<int:pk>/status/", ApplicationStatusView.as_view(), name="api_ats_application_status"),
    path("applications/<int:pk>/activity/", ApplicationActivityView.as_view(), name="api_ats_application_activity"),

    # Interviews
    path("interviews/", InterviewListCreateView.as_view(), name="api_ats_interviews"),
    path("interviews/<int:pk>/", InterviewDetailView.as_view(), name="api_ats_interview_detail"),
    path("interviews/<int:pk>/feedback/", InterviewFeedbackView.as_view(), name="api_ats_interview_feedback"),

    # Offers
    path("offers/", OfferListCreateView.as_view(), name="api_ats_offers"),
    path("offers/<int:pk>/", OfferDetailView.as_view(), name="api_ats_offer_detail"),
    path("offers/<int:pk>/status/", OfferStatusView.as_view(), name="api_ats_offer_status"),
    path("offers/<int:pk>/convert-to-employee/", OfferConvertView.as_view(), name="api_ats_offer_convert"),
    path("suggest-employee-code/", SuggestEmployeeCodeView.as_view(), name="api_ats_suggest_code"),
]
