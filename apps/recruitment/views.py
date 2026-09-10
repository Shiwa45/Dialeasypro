"""
TeleCRM Backend — apps/recruitment/views.py

Recruitment (ATS) API. Every endpoint is plan-gated on an ATS feature key
(ModuleKey.RECRUITMENT) and role-gated on an `ats.*` capability.

Note the capability split: ATS_INTERVIEW is deliberately WIDER than ATS_VIEW.
A senior agent often takes the technical round, and needs to file a scorecard
without being able to see salary bands or offers.
"""
import logging

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import HasFeatureAccess, IsAuthenticatedAgent
from apps.core.capabilities import Cap
from apps.core.constants import FeatureKey
from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import HasCapability
from apps.recruitment.constants import (
    ApplicationStatus,
    InterviewStatus,
    OfferStatus,
    OpeningStatus,
)
from apps.recruitment.models import (
    Application,
    Candidate,
    Interview,
    InterviewFeedback,
    JobOpening,
    Offer,
    PipelineStage,
)
from apps.recruitment.serializers import (
    ApplicationActivitySerializer,
    ApplicationSerializer,
    CandidateSerializer,
    InterviewFeedbackSerializer,
    InterviewSerializer,
    JobOpeningSerializer,
    OfferSerializer,
    PipelineStageSerializer,
)
from apps.recruitment.services import onboarding as onboarding_svc
from apps.recruitment.services import pipeline as pipeline_svc

logger = logging.getLogger(__name__)


def _bad(message, code="invalid", http=400):
    return Response({"error": code, "message": message}, status=http)


# ============================================================
# Job openings
# ============================================================

class JobOpeningListCreateView(generics.ListCreateAPIView):
    serializer_class = JobOpeningSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_JOB_OPENINGS
    required_capability = Cap.ATS_VIEW
    capability_by_method = {"POST": Cap.ATS_MANAGE}
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = JobOpening.objects.select_related("hiring_manager").annotate(
            app_count=Count("applications", distinct=True),
        )
        p = self.request.query_params
        if status_filter := p.get("status"):
            qs = qs.filter(status=status_filter)
        if department := p.get("department"):
            qs = qs.filter(department=department)
        if q := p.get("q"):
            qs = qs.filter(Q(title__icontains=q) | Q(code__icontains=q))
        # Meta.ordering does not survive the annotate() above: Django drops it
        # rather than let it join the GROUP BY, leaving the queryset unordered.
        # Paginating an unordered queryset lets Postgres return rows in any
        # order it likes, so a role can appear on two pages or on none.
        return qs.order_by("-created_at", "-id")


class JobOpeningDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = JobOpeningSerializer
    queryset = JobOpening.objects.select_related("hiring_manager")
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_JOB_OPENINGS
    required_capability = Cap.ATS_VIEW
    capability_by_method = {
        "PATCH": Cap.ATS_MANAGE, "PUT": Cap.ATS_MANAGE, "DELETE": Cap.ATS_MANAGE,
    }

    def destroy(self, request, *args, **kwargs):
        """
        Closing, not deleting, once anyone has applied.

        Deleting would cascade through every application, interview and
        scorecard filed against the role — months of a panel's work, gone
        because someone tidied up a stale opening.
        """
        opening = self.get_object()
        if opening.applications.exists():
            opening.status = OpeningStatus.CLOSED
            opening.closed_on = opening.closed_on or timezone.localdate()
            opening.save(update_fields=["status", "closed_on", "updated_at"])
            return Response(JobOpeningSerializer(opening).data)
        return super().destroy(request, *args, **kwargs)


class JobOpeningStatusView(APIView):
    """POST /openings/{id}/status/ {"status": "open"} — publish, hold or close."""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_JOB_OPENINGS
    required_capability = Cap.ATS_MANAGE

    def post(self, request, pk):
        opening = JobOpening.objects.filter(pk=pk).first()
        if opening is None:
            return _bad("Job opening not found.", "not_found", 404)

        new_status = (request.data.get("status") or "").strip()
        if new_status not in {c[0] for c in OpeningStatus.CHOICES}:
            return _bad(f"Unknown status '{new_status}'.")

        opening.status = new_status
        if new_status == OpeningStatus.OPEN and not opening.opened_on:
            opening.opened_on = timezone.localdate()
        if new_status == OpeningStatus.CLOSED:
            opening.closed_on = timezone.localdate()
        opening.save(update_fields=["status", "opened_on", "closed_on", "updated_at"])
        return Response(JobOpeningSerializer(opening).data)


# ============================================================
# Pipeline stages
# ============================================================

class PipelineStageListCreateView(generics.ListCreateAPIView):
    serializer_class = PipelineStageSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_JOB_OPENINGS
    required_capability = Cap.ATS_VIEW
    capability_by_method = {"POST": Cap.ATS_MANAGE}
    pagination_class = None

    def get_queryset(self):
        # A tenant that bought the module mid-subscription has no stages and
        # no way to create an application without them, so seed on first read.
        pipeline_svc.seed_pipeline()
        return PipelineStage.objects.annotate(app_count=Count("applications"))


class PipelineStageDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PipelineStageSerializer
    queryset = PipelineStage.objects.all()
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_JOB_OPENINGS
    required_capability = Cap.ATS_MANAGE

    def perform_destroy(self, instance):
        """Deactivate — applications reference the stage with PROTECT."""
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class PipelineStageReorderView(APIView):
    """POST /stages/reorder/ {"order": [3, 1, 2]} — ids in their new order."""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_JOB_OPENINGS
    required_capability = Cap.ATS_MANAGE

    def post(self, request):
        ids = request.data.get("order") or []
        if not isinstance(ids, list) or not ids:
            return _bad("Send `order` as a list of stage ids.")
        stages = {s.pk: s for s in PipelineStage.objects.filter(pk__in=ids)}
        updated = []
        for index, stage_id in enumerate(ids, start=1):
            stage = stages.get(stage_id)
            if stage and stage.order != index:
                stage.order = index
                updated.append(stage)
        PipelineStage.objects.bulk_update(updated, ["order"])
        return Response(PipelineStageSerializer(
            PipelineStage.objects.all(), many=True,
        ).data)


# ============================================================
# Candidates
# ============================================================

class CandidateListCreateView(generics.ListCreateAPIView):
    serializer_class = CandidateSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_CANDIDATES
    required_capability = Cap.ATS_VIEW
    capability_by_method = {"POST": Cap.ATS_MANAGE}
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Candidate.objects.select_related("referred_by").annotate(
            app_count=Count("applications", distinct=True),
        )
        p = self.request.query_params
        if source := p.get("source"):
            qs = qs.filter(source=source)
        if p.get("active") in ("true", "false"):
            qs = qs.filter(is_active=p["active"] == "true")
        if q := p.get("q"):
            qs = qs.filter(
                Q(name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q)
                | Q(current_company__icontains=q)
            )
        return qs


class CandidateDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CandidateSerializer
    queryset = Candidate.objects.select_related("referred_by")
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_CANDIDATES
    required_capability = Cap.ATS_VIEW
    capability_by_method = {
        "PATCH": Cap.ATS_MANAGE, "PUT": Cap.ATS_MANAGE, "DELETE": Cap.ATS_MANAGE,
    }

    def perform_destroy(self, instance):
        """Archive rather than delete — applications and scorecards hang off this."""
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class CandidateDuplicateCheckView(APIView):
    """
    GET /candidates/check-duplicate/?email=&phone=

    Warns, never blocks: people apply twice from a personal and a work
    address, and a shared family phone number is a real thing.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_CANDIDATES
    required_capability = Cap.ATS_VIEW

    def get(self, request):
        matches = pipeline_svc.find_duplicates(
            email=request.query_params.get("email", ""),
            phone=request.query_params.get("phone", ""),
            exclude_id=request.query_params.get("exclude") or None,
        )
        return Response({
            "count": matches.count(),
            "matches": CandidateSerializer(matches[:5], many=True).data,
        })


# ============================================================
# Applications
# ============================================================

class ApplicationListCreateView(generics.ListCreateAPIView):
    serializer_class = ApplicationSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_CANDIDATES
    required_capability = Cap.ATS_VIEW
    capability_by_method = {"POST": Cap.ATS_MANAGE}
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Application.objects.select_related(
            "candidate", "opening", "stage", "owner",
        ).prefetch_related("interviews")
        p = self.request.query_params
        if opening := p.get("opening"):
            qs = qs.filter(opening_id=opening)
        if candidate := p.get("candidate"):
            qs = qs.filter(candidate_id=candidate)
        if stage := p.get("stage"):
            qs = qs.filter(stage_id=stage)
        if status_filter := p.get("status"):
            qs = qs.filter(status=status_filter)
        if p.get("open") == "true":
            qs = qs.filter(status__in=ApplicationStatus.OPEN_STATUSES)
        return qs

    def create(self, request, *args, **kwargs):
        candidate = Candidate.objects.filter(pk=request.data.get("candidate")).first()
        opening = JobOpening.objects.filter(pk=request.data.get("opening")).first()
        if candidate is None or opening is None:
            return _bad("Pick both a candidate and a job opening.")
        try:
            application = pipeline_svc.create_application(
                candidate=candidate, opening=opening, actor=request.user,
            )
        except ValueError as exc:
            return _bad(str(exc), "invalid_application")
        return Response(ApplicationSerializer(application).data, status=status.HTTP_201_CREATED)


class ApplicationDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ApplicationSerializer
    queryset = Application.objects.select_related("candidate", "opening", "stage", "owner")
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_CANDIDATES
    required_capability = Cap.ATS_VIEW
    capability_by_method = {"PATCH": Cap.ATS_MANAGE, "PUT": Cap.ATS_MANAGE}


class ApplicationMoveView(APIView):
    """POST /applications/{id}/move/ {"stage": 3, "note": "..."}"""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_CANDIDATES
    required_capability = Cap.ATS_MANAGE

    def post(self, request, pk):
        application = Application.objects.filter(pk=pk).select_related("stage").first()
        if application is None:
            return _bad("Application not found.", "not_found", 404)
        stage = PipelineStage.objects.filter(pk=request.data.get("stage")).first()
        if stage is None:
            return _bad("Pick a stage to move to.")
        try:
            application = pipeline_svc.move_stage(
                application, stage, actor=request.user, note=request.data.get("note", ""),
            )
        except ValueError as exc:
            return _bad(str(exc), "invalid_transition")
        return Response(ApplicationSerializer(application).data)


class ApplicationBulkMoveView(APIView):
    """
    POST /applications/bulk-move/ {"applications": [1,2,3], "stage": 4}

    Screening a batch of twenty CVs one row at a time is what makes a
    recruiter stop using the pipeline and go back to a spreadsheet.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_CANDIDATES
    required_capability = Cap.ATS_MANAGE

    def post(self, request):
        ids = request.data.get("applications") or []
        stage = PipelineStage.objects.filter(pk=request.data.get("stage")).first()
        if not ids or stage is None:
            return _bad("Send `applications` (a list of ids) and a `stage`.")

        moved, errors = 0, []
        note = request.data.get("note", "")
        for application in Application.objects.filter(pk__in=ids).select_related("stage"):
            try:
                pipeline_svc.move_stage(application, stage, actor=request.user, note=note)
                moved += 1
            except ValueError as exc:
                errors.append({"application": application.pk, "message": str(exc)})
        # 207 when some moved and some didn't — the client shows exactly which.
        return Response(
            {"moved": moved, "errors": errors, "stage": stage.name},
            status=207 if errors and moved else 200,
        )


class ApplicationStatusView(APIView):
    """POST /applications/{id}/status/ {"status": "withdrawn", "note": "..."}"""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_CANDIDATES
    required_capability = Cap.ATS_MANAGE

    def post(self, request, pk):
        application = Application.objects.filter(pk=pk).first()
        if application is None:
            return _bad("Application not found.", "not_found", 404)
        try:
            application = pipeline_svc.set_status(
                application, (request.data.get("status") or "").strip(),
                actor=request.user, note=request.data.get("note", ""),
            )
        except ValueError as exc:
            return _bad(str(exc), "invalid_status")
        return Response(ApplicationSerializer(application).data)


class ApplicationActivityView(APIView):
    """GET the trail; POST a note onto it."""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_CANDIDATES
    required_capability = Cap.ATS_VIEW
    capability_by_method = {"POST": Cap.ATS_INTERVIEW}

    def get(self, request, pk):
        application = Application.objects.filter(pk=pk).first()
        if application is None:
            return _bad("Application not found.", "not_found", 404)
        return Response(ApplicationActivitySerializer(
            application.activities.select_related("actor"), many=True,
        ).data)

    def post(self, request, pk):
        from apps.recruitment.constants import ActivityKind

        application = Application.objects.filter(pk=pk).first()
        if application is None:
            return _bad("Application not found.", "not_found", 404)
        note = (request.data.get("note") or "").strip()
        if not note:
            return _bad("Write something in the note.")
        activity = pipeline_svc.log(
            application, ActivityKind.NOTE, note[:300], actor=request.user,
            detail=note if len(note) > 300 else "",
        )
        return Response(ApplicationActivitySerializer(activity).data, status=201)


# ============================================================
# Interviews
# ============================================================

class InterviewListCreateView(generics.ListCreateAPIView):
    serializer_class = InterviewSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_INTERVIEWS
    required_capability = Cap.ATS_INTERVIEW
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Interview.objects.select_related(
            "application__candidate", "application__opening",
        ).prefetch_related("interviewers", "feedback__interviewer")
        p = self.request.query_params
        if application := p.get("application"):
            qs = qs.filter(application_id=application)
        if status_filter := p.get("status"):
            qs = qs.filter(status=status_filter)
        if p.get("mine") == "true":
            qs = qs.filter(interviewers=self.request.user)
        if date_from := p.get("date_from"):
            qs = qs.filter(scheduled_at__date__gte=date_from)
        if date_to := p.get("date_to"):
            qs = qs.filter(scheduled_at__date__lte=date_to)
        return qs.distinct()

    def perform_create(self, serializer):
        interview = serializer.save()
        from apps.recruitment.constants import ActivityKind

        pipeline_svc.log(
            interview.application, ActivityKind.INTERVIEW,
            f"Round {interview.round_number} scheduled for "
            f"{interview.scheduled_at:%d %b %Y, %H:%M}",
            actor=self.request.user,
        )


class InterviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = InterviewSerializer
    queryset = Interview.objects.select_related(
        "application__candidate",
    ).prefetch_related("interviewers", "feedback__interviewer")
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_INTERVIEWS
    required_capability = Cap.ATS_INTERVIEW

    def perform_destroy(self, instance):
        """Cancel, keeping any feedback already filed against it."""
        instance.status = InterviewStatus.CANCELLED
        instance.save(update_fields=["status", "updated_at"])


class InterviewFeedbackView(APIView):
    """
    POST /interviews/{id}/feedback/ — file YOUR scorecard for this interview.

    One row per interviewer, upserted on (interview, interviewer): filing
    twice edits your own verdict rather than adding a second one, and nobody
    can overwrite a colleague's.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_INTERVIEWS
    required_capability = Cap.ATS_INTERVIEW

    def post(self, request, pk):
        from apps.recruitment.constants import ActivityKind

        interview = Interview.objects.filter(pk=pk).first()
        if interview is None:
            return _bad("Interview not found.", "not_found", 404)

        serializer = InterviewFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        feedback, created = InterviewFeedback.objects.update_or_create(
            interview=interview,
            interviewer=request.user,
            defaults={
                "recommendation": serializer.validated_data["recommendation"],
                "scores": serializer.validated_data.get("scores", {}),
                "strengths": serializer.validated_data.get("strengths", ""),
                "concerns": serializer.validated_data.get("concerns", ""),
                "comments": serializer.validated_data.get("comments", ""),
            },
        )

        # First scorecard on a scheduled interview means it actually happened.
        if created and interview.status == InterviewStatus.SCHEDULED:
            interview.status = InterviewStatus.COMPLETED
            interview.save(update_fields=["status", "updated_at"])

        pipeline_svc.log(
            interview.application, ActivityKind.FEEDBACK,
            f"{request.user.name}: {feedback.get_recommendation_display()} "
            f"(round {interview.round_number})",
            actor=request.user, detail=feedback.comments,
        )
        return Response(InterviewFeedbackSerializer(feedback).data,
                        status=201 if created else 200)


# ============================================================
# Offers
# ============================================================

class OfferListCreateView(generics.ListCreateAPIView):
    serializer_class = OfferSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_OFFERS
    required_capability = Cap.ATS_OFFER
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Offer.objects.select_related(
            "application__candidate", "application__opening",
            "reporting_to__agent", "converted_employee",
        )
        if status_filter := self.request.query_params.get("status"):
            qs = qs.filter(status=status_filter)
        return qs

    def perform_create(self, serializer):
        offer = serializer.save(created_by=self.request.user)
        from apps.recruitment.constants import ActivityKind

        pipeline_svc.log(
            offer.application, ActivityKind.OFFER,
            f"Offer drafted — ₹{offer.annual_ctc} CTC, joining {offer.joining_date}",
            actor=self.request.user,
        )


class OfferDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = OfferSerializer
    queryset = Offer.objects.select_related("application__candidate", "converted_employee")
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_OFFERS
    required_capability = Cap.ATS_OFFER

    def update(self, request, *args, **kwargs):
        offer = self.get_object()
        if offer.status not in (OfferStatus.DRAFT, OfferStatus.SENT):
            return _bad(
                f"An offer that has been {offer.get_status_display().lower()} cannot be edited.",
                "not_editable",
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        offer = self.get_object()
        if offer.status != OfferStatus.DRAFT:
            return _bad("Only a draft offer can be deleted. Revoke a sent offer instead.",
                        "not_deletable")
        return super().destroy(request, *args, **kwargs)


class OfferStatusView(APIView):
    """POST /offers/{id}/status/ {"status": "sent"|"accepted"|"declined"|"revoked"}"""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_OFFERS
    required_capability = Cap.ATS_OFFER

    ALLOWED = {
        OfferStatus.DRAFT: [OfferStatus.SENT],
        OfferStatus.SENT: [OfferStatus.ACCEPTED, OfferStatus.DECLINED, OfferStatus.REVOKED],
        OfferStatus.ACCEPTED: [OfferStatus.REVOKED],
        OfferStatus.DECLINED: [],
        OfferStatus.REVOKED: [],
    }

    def post(self, request, pk):
        from apps.recruitment.constants import ActivityKind

        offer = Offer.objects.filter(pk=pk).select_related("application").first()
        if offer is None:
            return _bad("Offer not found.", "not_found", 404)

        new_status = (request.data.get("status") or "").strip()
        if new_status not in self.ALLOWED.get(offer.status, []):
            return _bad(
                f"Cannot go from {offer.get_status_display().lower()} to '{new_status}'.",
                "invalid_transition",
            )

        offer.status = new_status
        if new_status == OfferStatus.SENT:
            offer.sent_at = timezone.now()
        if new_status in (OfferStatus.ACCEPTED, OfferStatus.DECLINED):
            offer.responded_at = timezone.now()
        offer.save(update_fields=["status", "sent_at", "responded_at", "updated_at"])

        # An accepted offer means the application is a hire; a declined one is
        # not automatically a rejection — the candidate may be re-offered, and
        # forcing REJECTED here would close a pipeline somebody is still working.
        if new_status == OfferStatus.ACCEPTED:
            pipeline_svc.set_status(
                offer.application, ApplicationStatus.HIRED, actor=request.user,
                note="Offer accepted",
            )

        pipeline_svc.log(
            offer.application, ActivityKind.OFFER,
            f"Offer {offer.get_status_display().lower()}",
            actor=request.user,
        )
        return Response(OfferSerializer(offer).data)


class OfferConvertView(APIView):
    """
    POST /offers/{id}/convert-to-employee/

    The Recruitment → HRMS bridge. Idempotent: a second click returns the
    employee created by the first.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_OFFERS
    required_capability = Cap.ATS_OFFER

    def post(self, request, pk):
        from apps.hrms.serializers import EmployeeSerializer

        offer = Offer.objects.filter(pk=pk).select_related("application__candidate").first()
        if offer is None:
            return _bad("Offer not found.", "not_found", 404)
        try:
            employee = onboarding_svc.convert_to_employee(
                offer, actor=request.user,
                employee_code=request.data.get("employee_code", ""),
            )
        except ValueError as exc:
            return _bad(str(exc), "cannot_convert")
        return Response({
            "employee": EmployeeSerializer(employee).data,
            "offer": OfferSerializer(offer).data,
        }, status=status.HTTP_201_CREATED)


class SuggestEmployeeCodeView(APIView):
    """GET /suggest-employee-code/ — next free code, so HR isn't guessing."""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_OFFERS
    required_capability = Cap.ATS_OFFER

    def get(self, request):
        return Response({"employee_code": onboarding_svc.suggest_employee_code()})


# ============================================================
# Dashboard
# ============================================================

class RecruitmentDashboardView(APIView):
    """GET /recruitment/dashboard/ — pipeline health at a glance."""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ATS_JOB_OPENINGS
    required_capability = Cap.ATS_VIEW

    def get(self, request):
        from datetime import timedelta

        pipeline_svc.seed_pipeline()
        today = timezone.localdate()
        now = timezone.now()

        openings = JobOpening.objects.filter(status=OpeningStatus.OPEN)
        open_apps = Application.objects.filter(status__in=ApplicationStatus.OPEN_STATUSES)

        by_stage = list(
            PipelineStage.objects.filter(is_active=True)
            .annotate(count=Count(
                "applications",
                filter=Q(applications__status__in=ApplicationStatus.OPEN_STATUSES),
            ))
            .order_by("order")
            .values("id", "name", "count", "is_terminal")
        )

        upcoming = Interview.objects.filter(
            status=InterviewStatus.SCHEDULED,
            scheduled_at__gte=now,
            scheduled_at__lte=now + timedelta(days=7),
        ).count()

        # Interviews that happened but whose panel hasn't filed. This is the
        # number that actually stalls a pipeline — a candidate waiting on a
        # scorecard nobody wrote.
        awaiting_feedback = 0
        for interview in Interview.objects.filter(
            status=InterviewStatus.COMPLETED,
        ).prefetch_related("interviewers", "feedback")[:500]:
            if interview.interviewers.count() > interview.feedback.count():
                awaiting_feedback += 1

        # Time to hire, measured over the last 90 days of actual hires.
        hires = Application.objects.filter(
            status=ApplicationStatus.HIRED,
            updated_at__gte=now - timedelta(days=90),
        ).values_list("applied_on", "updated_at")
        spans = [(u.date() - a).days for a, u in hires if a and u]
        avg_time_to_hire = round(sum(spans) / len(spans)) if spans else None

        return Response({
            "openings": {
                "open": openings.count(),
                "positions": sum(o.openings for o in openings),
                "on_hold": JobOpening.objects.filter(status=OpeningStatus.ON_HOLD).count(),
                "closed": JobOpening.objects.filter(status=OpeningStatus.CLOSED).count(),
            },
            "candidates": {
                "total": Candidate.objects.filter(is_active=True).count(),
                "applications_open": open_apps.count(),
                "applied_this_month": Application.objects.filter(
                    applied_on__gte=today.replace(day=1),
                ).count(),
            },
            "by_stage": by_stage,
            "interviews": {
                "upcoming_7_days": upcoming,
                "awaiting_feedback": awaiting_feedback,
            },
            "offers": {
                "sent": Offer.objects.filter(status=OfferStatus.SENT).count(),
                "accepted": Offer.objects.filter(status=OfferStatus.ACCEPTED).count(),
                "pending_conversion": Offer.objects.filter(
                    status=OfferStatus.ACCEPTED, converted_employee__isnull=True,
                ).count(),
            },
            "avg_time_to_hire_days": avg_time_to_hire,
        })
