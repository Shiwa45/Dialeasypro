"""
TeleCRM Backend — apps/recruitment/services/pipeline.py

Stage movement and the activity trail that records it.

Every mutation to an Application goes through here rather than through the
serializer, so that no code path can move a candidate without leaving an
audit row behind. "Who rejected this person, and when?" gets asked months
later, usually by someone disputing the outcome.
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.recruitment.constants import (
    DEFAULT_STAGES,
    ActivityKind,
    ApplicationStatus,
    OpeningStatus,
)
from apps.recruitment.models import (
    Application,
    ApplicationActivity,
    Candidate,
    PipelineStage,
)

logger = logging.getLogger(__name__)


def seed_pipeline() -> int:
    """
    Create the default stages if a tenant has none.

    Called lazily the first time a stage is needed, because a tenant that
    buys the module mid-subscription never runs a fresh migration and would
    otherwise land on an empty pipeline with no way to create an application.
    """
    if PipelineStage.objects.exists():
        return 0
    PipelineStage.objects.bulk_create([PipelineStage(**s) for s in DEFAULT_STAGES])
    return len(DEFAULT_STAGES)


def first_stage() -> PipelineStage:
    """The stage a new application lands on. Seeds defaults if needed."""
    seed_pipeline()
    stage = PipelineStage.objects.filter(is_active=True, is_terminal=False).order_by("order").first()
    if stage is None:
        # Every stage was marked terminal or deactivated — recoverable, but
        # applications must still land somewhere.
        stage = PipelineStage.objects.order_by("order").first()
    if stage is None:
        raise ValueError("No pipeline stages are configured.")
    return stage


def log(application, kind, summary, *, actor=None, detail=""):
    """Append one row to an application's trail."""
    return ApplicationActivity.objects.create(
        application=application, kind=kind, summary=summary, detail=detail, actor=actor,
    )


def find_duplicates(*, email: str = "", phone: str = "", exclude_id=None):
    """
    Candidates who look like the same person.

    Matched on email OR phone, not both: people apply twice from a personal
    and a work address, and the phone catches that. Returns a queryset so the
    caller can decide whether to warn or block — this never blocks, because a
    shared family phone number is a real thing and a hard block on it would
    lose a genuine applicant.
    """
    qs = Candidate.objects.none()
    if email:
        qs = Candidate.objects.filter(email__iexact=email.strip())
    if phone:
        digits = "".join(c for c in phone if c.isdigit())[-10:]
        if digits:
            by_phone = Candidate.objects.filter(phone__endswith=digits)
            qs = by_phone if not email else (qs | by_phone)
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)
    return qs.distinct()


@transaction.atomic
def create_application(*, candidate, opening, actor=None, owner=None) -> Application:
    """Put a candidate into an opening's pipeline at the first stage."""
    if opening.status not in OpeningStatus.ACCEPTING:
        raise ValueError(
            f"{opening.code} is {opening.get_status_display().lower()} and is not accepting applications."
        )
    if Application.objects.filter(candidate=candidate, opening=opening).exists():
        raise ValueError(f"{candidate.name} has already been applied to {opening.code}.")

    application = Application.objects.create(
        candidate=candidate,
        opening=opening,
        stage=first_stage(),
        owner=owner or actor,
    )
    log(application, ActivityKind.CREATED,
        f"Applied to {opening.code} — {opening.title}", actor=actor)
    return application


@transaction.atomic
def move_stage(application: Application, stage: PipelineStage, *, actor=None, note: str = "") -> Application:
    """
    Move an application to another stage.

    Moving INTO a terminal stage also closes the application's status, so the
    two can never disagree — a candidate sitting in "Rejected" while still
    counted as active is the classic ATS reporting bug.
    """
    if application.status in ApplicationStatus.CLOSED_STATUSES:
        raise ValueError(
            f"This application is {application.get_status_display().lower()} and cannot be moved."
        )
    if application.stage_id == stage.pk:
        return application

    previous = application.stage
    application.stage = stage
    application.stage_changed_at = timezone.now()

    if stage.is_terminal:
        lowered = stage.name.strip().lower()
        if "hire" in lowered or "select" in lowered:
            application.status = ApplicationStatus.HIRED
        elif "reject" in lowered or "declin" in lowered:
            application.status = ApplicationStatus.REJECTED
        if note and application.status == ApplicationStatus.REJECTED:
            application.rejection_reason = note[:300]

    application.save(update_fields=["stage", "stage_changed_at", "status", "rejection_reason", "updated_at"])
    log(application, ActivityKind.STAGE_CHANGE,
        f"{previous.name} → {stage.name}", actor=actor, detail=note)
    return application


@transaction.atomic
def set_status(application: Application, status: str, *, actor=None, note: str = "") -> Application:
    """Withdraw, hold or reject an application without moving its stage."""
    valid = {c[0] for c in ApplicationStatus.CHOICES}
    if status not in valid:
        raise ValueError(f"Unknown status '{status}'.")

    previous = application.get_status_display()
    application.status = status
    if status == ApplicationStatus.REJECTED and note:
        application.rejection_reason = note[:300]
    application.save(update_fields=["status", "rejection_reason", "updated_at"])
    log(application, ActivityKind.STATUS_CHANGE,
        f"{previous} → {application.get_status_display()}", actor=actor, detail=note)
    return application
