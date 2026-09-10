"""
TeleCRM Backend — apps/recruitment/admin.py
"""
from django.contrib import admin

from apps.recruitment.models import (
    Application,
    ApplicationActivity,
    Candidate,
    Interview,
    InterviewFeedback,
    JobOpening,
    Offer,
    PipelineStage,
)


@admin.register(JobOpening)
class JobOpeningAdmin(admin.ModelAdmin):
    list_display = ["code", "title", "department", "status", "openings", "hired_count", "opened_on"]
    list_filter = ["status", "department", "employment_type"]
    search_fields = ["code", "title", "department"]


@admin.register(PipelineStage)
class PipelineStageAdmin(admin.ModelAdmin):
    list_display = ["name", "order", "is_terminal", "is_active"]
    list_editable = ["order", "is_terminal", "is_active"]


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "phone", "current_company", "total_experience_years", "source", "is_active"]
    list_filter = ["source", "is_active"]
    search_fields = ["name", "email", "phone", "current_company"]


class ApplicationActivityInline(admin.TabularInline):
    model = ApplicationActivity
    extra = 0
    readonly_fields = ["kind", "summary", "detail", "actor", "created_at"]
    can_delete = False


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["candidate", "opening", "stage", "status", "owner", "applied_on"]
    list_filter = ["status", "stage", "opening"]
    search_fields = ["candidate__name", "opening__code"]
    inlines = [ApplicationActivityInline]


class InterviewFeedbackInline(admin.TabularInline):
    model = InterviewFeedback
    extra = 0


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ["application", "round_number", "scheduled_at", "mode", "status"]
    list_filter = ["status", "mode"]
    inlines = [InterviewFeedbackInline]


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ["application", "annual_ctc", "joining_date", "status", "converted_employee"]
    list_filter = ["status", "employment_type"]
