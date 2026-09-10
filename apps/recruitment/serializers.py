"""
TeleCRM Backend — apps/recruitment/serializers.py
"""
from rest_framework import serializers

from apps.recruitment.constants import Recommendation
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


class JobOpeningSerializer(serializers.ModelSerializer):
    hiring_manager_name = serializers.CharField(
        source="hiring_manager.name", read_only=True, default=None,
    )
    hired_count = serializers.IntegerField(read_only=True)
    is_filled = serializers.BooleanField(read_only=True)
    application_count = serializers.SerializerMethodField()

    class Meta:
        model = JobOpening
        fields = [
            "id", "title", "code", "department", "location", "employment_type",
            "openings", "min_experience_years", "max_experience_years",
            "salary_min", "salary_max", "description",
            "hiring_manager", "hiring_manager_name",
            "status", "opened_on", "closed_on",
            "hired_count", "is_filled", "application_count", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_application_count(self, obj) -> int:
        # Annotated by the view where it matters; fall back for single reads.
        return getattr(obj, "app_count", None) or obj.applications.count()


class PipelineStageSerializer(serializers.ModelSerializer):
    application_count = serializers.SerializerMethodField()

    class Meta:
        model = PipelineStage
        fields = ["id", "name", "order", "is_terminal", "is_active", "application_count"]

    def get_application_count(self, obj) -> int:
        return getattr(obj, "app_count", None) or obj.applications.count()


class CandidateSerializer(serializers.ModelSerializer):
    referred_by_name = serializers.CharField(source="referred_by.name", read_only=True, default=None)
    application_count = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = [
            "id", "name", "email", "phone", "source", "referred_by", "referred_by_name",
            "current_company", "current_designation", "total_experience_years",
            "current_ctc", "expected_ctc", "notice_period_days", "location",
            "skills", "resume", "notes", "is_active",
            "application_count", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_application_count(self, obj) -> int:
        return getattr(obj, "app_count", None) or obj.applications.count()

    def validate(self, data):
        # A candidate with neither an email nor a phone can never be contacted
        # and can never be deduplicated against — refuse it at the door.
        email = data.get("email", getattr(self.instance, "email", ""))
        phone = data.get("phone", getattr(self.instance, "phone", ""))
        if not (email or "").strip() and not (phone or "").strip():
            raise serializers.ValidationError(
                {"email": "Give at least an email address or a phone number."}
            )
        return data


class ApplicationActivitySerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.name", read_only=True, default=None)

    class Meta:
        model = ApplicationActivity
        fields = ["id", "kind", "summary", "detail", "actor", "actor_name", "created_at"]
        read_only_fields = fields


class ApplicationSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source="candidate.name", read_only=True)
    candidate_email = serializers.CharField(source="candidate.email", read_only=True)
    candidate_phone = serializers.CharField(source="candidate.phone", read_only=True)
    candidate_experience = serializers.DecimalField(
        source="candidate.total_experience_years", max_digits=4, decimal_places=1, read_only=True,
    )
    opening_title = serializers.CharField(source="opening.title", read_only=True)
    opening_code = serializers.CharField(source="opening.code", read_only=True)
    stage_name = serializers.CharField(source="stage.name", read_only=True)
    stage_order = serializers.IntegerField(source="stage.order", read_only=True)
    owner_name = serializers.CharField(source="owner.name", read_only=True, default=None)
    days_in_stage = serializers.IntegerField(read_only=True)
    interview_count = serializers.SerializerMethodField()
    has_offer = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            "id", "candidate", "candidate_name", "candidate_email", "candidate_phone",
            "candidate_experience", "opening", "opening_title", "opening_code",
            "stage", "stage_name", "stage_order", "status", "owner", "owner_name",
            "applied_on", "rating", "rejection_reason", "stage_changed_at",
            "days_in_stage", "interview_count", "has_offer", "created_at",
        ]
        # Stage and status move through services/pipeline.py so that no path
        # can change them without writing an activity row.
        read_only_fields = [
            "id", "stage", "status", "stage_changed_at", "rejection_reason", "created_at",
        ]

    def get_interview_count(self, obj) -> int:
        return obj.interviews.count()

    def get_has_offer(self, obj) -> bool:
        return hasattr(obj, "offer")


class InterviewFeedbackSerializer(serializers.ModelSerializer):
    interviewer_name = serializers.CharField(source="interviewer.name", read_only=True)
    score = serializers.SerializerMethodField()

    class Meta:
        model = InterviewFeedback
        fields = [
            "id", "interview", "interviewer", "interviewer_name", "recommendation",
            "score", "scores", "strengths", "concerns", "comments", "created_at",
        ]
        read_only_fields = ["id", "interview", "interviewer", "created_at"]

    def get_score(self, obj) -> int:
        return Recommendation.SCORES.get(obj.recommendation, 0)


class InterviewSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source="application.candidate.name", read_only=True)
    opening_title = serializers.CharField(source="application.opening.title", read_only=True)
    interviewer_names = serializers.SerializerMethodField()
    feedback = InterviewFeedbackSerializer(many=True, read_only=True)
    average_score = serializers.FloatField(read_only=True)
    feedback_pending = serializers.SerializerMethodField()

    class Meta:
        model = Interview
        fields = [
            "id", "application", "candidate_name", "opening_title", "round_number",
            "title", "scheduled_at", "duration_minutes", "mode", "location_or_link",
            "interviewers", "interviewer_names", "status", "notes",
            "feedback", "average_score", "feedback_pending", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_interviewer_names(self, obj) -> list[str]:
        return [a.name for a in obj.interviewers.all()]

    def get_feedback_pending(self, obj) -> int:
        """Interviewers who haven't filed yet — the number worth chasing."""
        return max(0, obj.interviewers.count() - obj.feedback.count())


class OfferSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source="application.candidate.name", read_only=True)
    candidate_email = serializers.CharField(source="application.candidate.email", read_only=True)
    opening_title = serializers.CharField(source="application.opening.title", read_only=True)
    reporting_to_name = serializers.CharField(
        source="reporting_to.agent.name", read_only=True, default=None,
    )
    converted_employee_code = serializers.CharField(
        source="converted_employee.employee_code", read_only=True, default=None,
    )

    class Meta:
        model = Offer
        fields = [
            "id", "application", "candidate_name", "candidate_email", "opening_title",
            "annual_ctc", "fixed_component", "variable_component", "joining_bonus",
            "designation", "department", "employment_type",
            "reporting_to", "reporting_to_name",
            "joining_date", "valid_until", "offer_letter", "notes",
            "status", "sent_at", "responded_at",
            "converted_employee", "converted_employee_code", "created_at",
        ]
        read_only_fields = [
            "id", "status", "sent_at", "responded_at", "converted_employee", "created_at",
        ]

    def validate(self, data):
        fixed = data.get("fixed_component") or 0
        variable = data.get("variable_component") or 0
        ctc = data.get("annual_ctc")
        # Not fatal — plenty of offers quote a CTC that includes benefits the
        # split doesn't itemise — but a split LARGER than the CTC is always a
        # typo, and catching it here beats catching it in an offer letter.
        if ctc and (fixed + variable) > ctc:
            raise serializers.ValidationError({
                "fixed_component":
                    "Fixed plus variable is more than the annual CTC. Check the split."
            })
        return data
