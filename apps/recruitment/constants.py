"""
TeleCRM Backend — apps/recruitment/constants.py

Enumerations for the Recruitment (ATS) add-on module.
"""


class OpeningStatus:
    DRAFT = "draft"
    OPEN = "open"
    ON_HOLD = "on_hold"
    CLOSED = "closed"

    CHOICES = [
        (DRAFT, "Draft"),
        (OPEN, "Open"),
        (ON_HOLD, "On Hold"),
        (CLOSED, "Closed"),
    ]

    # Statuses a candidate can still be applied against.
    ACCEPTING = [OPEN]


class ApplicationStatus:
    """
    Where an application sits, independent of which pipeline stage it is on.

    Stage is configurable per tenant; status is not, because reporting
    ("how many are still live?") must not depend on how someone named their
    stages.
    """

    ACTIVE = "active"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    ON_HOLD = "on_hold"

    CHOICES = [
        (ACTIVE, "Active"),
        (HIRED, "Hired"),
        (REJECTED, "Rejected"),
        (WITHDRAWN, "Withdrawn"),
        (ON_HOLD, "On Hold"),
    ]

    OPEN_STATUSES = [ACTIVE, ON_HOLD]
    CLOSED_STATUSES = [HIRED, REJECTED, WITHDRAWN]


class CandidateSource:
    REFERRAL = "referral"
    JOB_BOARD = "job_board"
    LINKEDIN = "linkedin"
    CAREERS_PAGE = "careers_page"
    AGENCY = "agency"
    WALK_IN = "walk_in"
    OTHER = "other"

    CHOICES = [
        (REFERRAL, "Referral"),
        (JOB_BOARD, "Job Board (Naukri/Indeed)"),
        (LINKEDIN, "LinkedIn"),
        (CAREERS_PAGE, "Careers Page"),
        (AGENCY, "Recruitment Agency"),
        (WALK_IN, "Walk-in"),
        (OTHER, "Other"),
    ]


class InterviewMode:
    PHONE = "phone"
    VIDEO = "video"
    ONSITE = "onsite"

    CHOICES = [(PHONE, "Phone"), (VIDEO, "Video"), (ONSITE, "On-site")]


class InterviewStatus:
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"

    CHOICES = [
        (SCHEDULED, "Scheduled"),
        (COMPLETED, "Completed"),
        (CANCELLED, "Cancelled"),
        (NO_SHOW, "No Show"),
    ]


class Recommendation:
    """An interviewer's verdict. Ordered worst → best for averaging."""

    STRONG_NO = "strong_no"
    NO = "no"
    MAYBE = "maybe"
    YES = "yes"
    STRONG_YES = "strong_yes"

    CHOICES = [
        (STRONG_NO, "Strong No"),
        (NO, "No"),
        (MAYBE, "Maybe"),
        (YES, "Yes"),
        (STRONG_YES, "Strong Yes"),
    ]

    # Numeric weights so a panel's verdicts can be averaged into one number.
    SCORES = {STRONG_NO: 1, NO: 2, MAYBE: 3, YES: 4, STRONG_YES: 5}


class OfferStatus:
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    REVOKED = "revoked"

    CHOICES = [
        (DRAFT, "Draft"),
        (SENT, "Sent"),
        (ACCEPTED, "Accepted"),
        (DECLINED, "Declined"),
        (REVOKED, "Revoked"),
    ]


class ActivityKind:
    """What an ApplicationActivity row records."""

    CREATED = "created"
    STAGE_CHANGE = "stage_change"
    STATUS_CHANGE = "status_change"
    NOTE = "note"
    INTERVIEW = "interview"
    FEEDBACK = "feedback"
    OFFER = "offer"

    CHOICES = [
        (CREATED, "Created"),
        (STAGE_CHANGE, "Stage Change"),
        (STATUS_CHANGE, "Status Change"),
        (NOTE, "Note"),
        (INTERVIEW, "Interview"),
        (FEEDBACK, "Feedback"),
        (OFFER, "Offer"),
    ]


# Seeded for a new tenant by seed_pipeline(). Order matters — it is the order
# a candidate walks. `is_terminal` marks a stage nobody moves out of.
DEFAULT_STAGES = [
    {"name": "Applied",     "order": 1, "is_terminal": False},
    {"name": "Screening",   "order": 2, "is_terminal": False},
    {"name": "Interview",   "order": 3, "is_terminal": False},
    {"name": "Offer",       "order": 4, "is_terminal": False},
    {"name": "Hired",       "order": 5, "is_terminal": True},
    {"name": "Rejected",    "order": 6, "is_terminal": True},
]
