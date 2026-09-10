"""
TeleCRM Backend — apps/recruitment/models.py

Recruitment (ATS) add-on module. All models live in the TENANT schema.

Design notes
------------
* A Candidate is a PERSON and exists once, independent of any role. An
  Application is that person against one JobOpening. Modelling the two
  separately is what lets someone be considered for a second role without
  re-typing their details, and is what makes "have we seen this person
  before?" answerable at all.
* PipelineStage is data, not an enum: every company names its stages
  differently. ApplicationStatus stays a hard enum precisely because
  reporting must not depend on what someone called a stage.
* InterviewFeedback is one row PER INTERVIEWER, not per interview. A panel
  where three people file separate verdicts is the normal case, and folding
  them into one row loses the disagreement — which is usually the signal.
* Offer → Employee is the bridge to HRMS (services/onboarding.py). Without it
  the two modules are two products sharing a login.
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.hrms.constants import EmploymentType
from apps.recruitment.constants import (
    ActivityKind,
    ApplicationStatus,
    CandidateSource,
    InterviewMode,
    InterviewStatus,
    OfferStatus,
    OpeningStatus,
    Recommendation,
)


# ============================================================
# Job openings
# ============================================================

class JobOpening(TimeStampedModel):
    title = models.CharField(max_length=150)
    code = models.CharField(
        max_length=30, unique=True, db_index=True,
        help_text="Short reference, e.g. ENG-2026-04.",
    )
    department = models.CharField(max_length=100, blank=True, default="")
    location = models.CharField(max_length=120, blank=True, default="")
    employment_type = models.CharField(
        max_length=20, choices=EmploymentType.CHOICES, default=EmploymentType.FULL_TIME,
    )
    openings = models.PositiveIntegerField(
        default=1, help_text="How many people are being hired for this role.",
    )

    min_experience_years = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("0.0"))
    max_experience_years = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True,
    )
    # A salary band is commercially sensitive, which is why ATS_VIEW is a
    # narrower capability than the rest of the CRM.
    salary_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    description = models.TextField(blank=True, default="", help_text="Job description.")
    hiring_manager = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="job_openings",
    )

    status = models.CharField(
        max_length=15, choices=OpeningStatus.CHOICES, default=OpeningStatus.DRAFT, db_index=True,
    )
    opened_on = models.DateField(null=True, blank=True)
    closed_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "department"], name="ats_open_status_dept_idx")]

    def __str__(self):
        return f"{self.code} — {self.title}"

    @property
    def hired_count(self) -> int:
        return self.applications.filter(status=ApplicationStatus.HIRED).count()

    @property
    def is_filled(self) -> bool:
        return self.hired_count >= self.openings


# ============================================================
# Pipeline
# ============================================================

class PipelineStage(TimeStampedModel):
    """
    A named step candidates move through. Configurable per tenant, because
    every company names these differently and hardcoding one company's names
    is how an ATS stops fitting the second company that uses it.
    """

    name = models.CharField(max_length=60, unique=True)
    order = models.PositiveIntegerField(default=0, db_index=True)
    is_terminal = models.BooleanField(
        default=False,
        help_text="Nobody moves out of a terminal stage (Hired, Rejected).",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


# ============================================================
# Candidates
# ============================================================

class Candidate(TimeStampedModel):
    """A person. Exists once, independent of the roles they apply for."""

    name = models.CharField(max_length=150, db_index=True)
    email = models.EmailField(blank=True, default="", db_index=True)
    phone = models.CharField(max_length=20, blank=True, default="", db_index=True)

    source = models.CharField(
        max_length=20, choices=CandidateSource.CHOICES, default=CandidateSource.OTHER,
    )
    referred_by = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="referred_candidates",
    )

    current_company = models.CharField(max_length=150, blank=True, default="")
    current_designation = models.CharField(max_length=150, blank=True, default="")
    total_experience_years = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("0.0"))
    current_ctc = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expected_ctc = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notice_period_days = models.PositiveIntegerField(default=0)

    location = models.CharField(max_length=120, blank=True, default="")
    skills = models.JSONField(default=list, blank=True, help_text="List of skill strings.")
    resume = models.FileField(upload_to="recruitment/resumes/", null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["email", "phone"], name="ats_cand_contact_idx")]

    def __str__(self):
        return self.name


# ============================================================
# Applications
# ============================================================

class Application(TimeStampedModel):
    """One candidate against one opening."""

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="applications")
    opening = models.ForeignKey(JobOpening, on_delete=models.CASCADE, related_name="applications")
    stage = models.ForeignKey(
        PipelineStage, on_delete=models.PROTECT, related_name="applications",
    )
    status = models.CharField(
        max_length=15, choices=ApplicationStatus.CHOICES,
        default=ApplicationStatus.ACTIVE, db_index=True,
    )

    owner = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="owned_applications",
        help_text="The recruiter driving this application.",
    )
    applied_on = models.DateField(default=timezone.localdate)
    rating = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Recruiter's own 1-5 rating.",
    )
    rejection_reason = models.CharField(max_length=300, blank=True, default="")
    stage_changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        # The same person cannot be applied to the same role twice. Without
        # this a double-click on "Apply" silently creates a duplicate pipeline
        # entry, and the panel ends up interviewing the same person twice.
        unique_together = ("candidate", "opening")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["opening", "status"], name="ats_app_open_status_idx")]

    def __str__(self):
        return f"{self.candidate.name} → {self.opening.code}"

    @property
    def days_in_stage(self) -> int:
        return (timezone.now() - self.stage_changed_at).days


class ApplicationActivity(TimeStampedModel):
    """
    Append-only audit trail for one application.

    Never updated or deleted — "who moved this candidate to Rejected, and
    when?" is a question that gets asked months later, usually when somebody
    disputes the outcome.
    """

    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="activities",
    )
    kind = models.CharField(max_length=20, choices=ActivityKind.CHOICES)
    summary = models.CharField(max_length=300)
    detail = models.TextField(blank=True, default="")
    actor = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.application_id} {self.kind}"


# ============================================================
# Interviews
# ============================================================

class Interview(TimeStampedModel):
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="interviews",
    )
    round_number = models.PositiveSmallIntegerField(default=1)
    title = models.CharField(max_length=120, blank=True, default="", help_text="e.g. Technical Round 1")
    scheduled_at = models.DateTimeField(db_index=True)
    duration_minutes = models.PositiveSmallIntegerField(default=45)
    mode = models.CharField(max_length=10, choices=InterviewMode.CHOICES, default=InterviewMode.VIDEO)
    location_or_link = models.CharField(max_length=300, blank=True, default="")

    interviewers = models.ManyToManyField(
        "authentication.Agent", related_name="interviews", blank=True,
    )
    status = models.CharField(
        max_length=15, choices=InterviewStatus.CHOICES,
        default=InterviewStatus.SCHEDULED, db_index=True,
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-scheduled_at"]
        indexes = [models.Index(fields=["status", "scheduled_at"], name="ats_int_status_time_idx")]

    def __str__(self):
        return f"{self.application} R{self.round_number}"

    @property
    def average_score(self) -> float | None:
        """Mean of the panel's recommendations, 1-5. None until someone files."""
        scores = [
            Recommendation.SCORES.get(f.recommendation, 0)
            for f in self.feedback.all()
            if f.recommendation
        ]
        return round(sum(scores) / len(scores), 2) if scores else None


class InterviewFeedback(TimeStampedModel):
    """
    One interviewer's verdict on one interview.

    Per-interviewer rather than per-interview: a panel where three people file
    separately is the normal case, and folding them into one row loses the
    disagreement — which is usually the signal worth reading.
    """

    interview = models.ForeignKey(Interview, on_delete=models.CASCADE, related_name="feedback")
    interviewer = models.ForeignKey(
        "authentication.Agent", on_delete=models.CASCADE, related_name="interview_feedback",
    )
    recommendation = models.CharField(max_length=15, choices=Recommendation.CHOICES)
    scores = models.JSONField(
        default=dict, blank=True,
        help_text='Per-criterion scores, e.g. {"communication": 4, "technical": 3}.',
    )
    strengths = models.TextField(blank=True, default="")
    concerns = models.TextField(blank=True, default="")
    comments = models.TextField(blank=True, default="")

    class Meta:
        unique_together = ("interview", "interviewer")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.interview_id} by {self.interviewer_id}: {self.recommendation}"


# ============================================================
# Offers
# ============================================================

class Offer(TimeStampedModel):
    application = models.OneToOneField(
        Application, on_delete=models.CASCADE, related_name="offer",
    )

    annual_ctc = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))],
    )
    # Mirrors hrms.SalaryStructure so accepting an offer can seed one without
    # anybody retyping the numbers into payroll.
    fixed_component = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    variable_component = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    joining_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    designation = models.CharField(max_length=150, blank=True, default="")
    department = models.CharField(max_length=100, blank=True, default="")
    employment_type = models.CharField(
        max_length=20, choices=EmploymentType.CHOICES, default=EmploymentType.FULL_TIME,
    )
    reporting_to = models.ForeignKey(
        "hrms.Employee", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    joining_date = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    offer_letter = models.FileField(upload_to="recruitment/offers/", null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    status = models.CharField(
        max_length=15, choices=OfferStatus.CHOICES, default=OfferStatus.DRAFT, db_index=True,
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    # Set once the hire is converted into an HRMS employee. Its presence is
    # what makes conversion idempotent — a second click returns the same row
    # instead of creating a duplicate employee.
    converted_employee = models.ForeignKey(
        "hrms.Employee", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="source_offer",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Offer to {self.application.candidate.name} ({self.status})"
