"""
TeleCRM Backend — apps/leads/models.py

Core CRM models. All live in TENANT schemas.

Lead           : A sales prospect. Central entity of the entire CRM.
FollowUp       : A scheduled callback or meeting for a lead.
LeadNote       : Free-text note attached to a lead (log of interactions).
CustomField    : Tenant-defined extra fields on leads (up to plan limit).
CustomFieldValue: Value store for custom fields per lead.
LeadImportJob  : Tracks CSV/Excel import operations with row-level results.
LeadActivity   : Immutable activity feed for each lead (calls, messages, status changes).
"""
import uuid
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.constants import (
    AgentRole,
    CallDirection,
    FollowUpType,
    LeadPriority,
    LeadSource,
    LeadStatus,
)
from apps.core.models import SoftDeleteModel, TimeStampedModel, TimeStampedUUIDModel


# ============================================================
# Lead
# ============================================================

class Lead(SoftDeleteModel, TimeStampedModel):
    """
    A sales prospect / customer inquiry.

    Key design decisions:
    - Phone is the primary identifier (Indian B2C sales — mobile-first)
    - Soft-deleted (is_deleted flag) so history is preserved
    - Assigned to one agent but can be reassigned
    - Pipeline stage tracked via status field
    - Custom fields via LeadCustomFieldValue (EAV pattern, bounded by plan)
    """

    # ---- Identity -----------------------------------------
    name = models.CharField(max_length=200, db_index=True)
    phone = models.CharField(
        max_length=15,
        db_index=True,
        help_text="Primary contact. +91XXXXXXXXXX format stored internally.",
    )
    alternate_phone = models.CharField(max_length=15, blank=True, default="")
    email = models.EmailField(blank=True, default="", db_index=True)

    # ---- Address ------------------------------------------
    city = models.CharField(max_length=100, blank=True, default="", db_index=True)
    state = models.CharField(max_length=100, blank=True, default="")
    pincode = models.CharField(max_length=6, blank=True, default="")
    address = models.TextField(blank=True, default="")

    # ---- Classification -----------------------------------
    source = models.CharField(
        max_length=50,
        choices=LeadSource.CHOICES,
        default=LeadSource.MANUAL,
        db_index=True,
    )
    status = models.CharField(
        max_length=30,
        choices=LeadStatus.CHOICES,
        default=LeadStatus.NEW,
        db_index=True,
    )
    priority = models.CharField(
        max_length=10,
        choices=LeadPriority.CHOICES,
        default=LeadPriority.WARM,
        db_index=True,
    )

    # ---- Sales Qualification --------------------------------
    budget = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text="Budget in INR (e.g., property budget for real estate).",
    )
    requirement = models.TextField(
        blank=True, default="",
        help_text="What the lead is looking for (BHK type, location, etc.).",
    )
    score = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        help_text="Lead quality score 0-100 (auto-calculated or manual).",
    )

    # ---- Assignment ----------------------------------------
    assigned_to = models.ForeignKey(
        "authentication.Agent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_leads",
        db_index=True,
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    # Tracks the team lead/manager who owns this territory
    territory_manager = models.ForeignKey(
        "authentication.Agent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="territory_leads",
    )

    # ---- Pipeline -----------------------------------------
    pipeline_stage = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Visual kanban column position (1=leftmost/new, 10=won/lost).",
    )
    expected_close_date = models.DateField(null=True, blank=True)
    deal_value = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Expected deal value in INR.",
    )

    # ---- Source Metadata -----------------------------------
    # Stores raw data from lead sources (IndiaMART, Meta Ads, etc.)
    source_meta = models.JSONField(
        default=dict, blank=True,
        help_text="Raw data from the lead source (webhook payload, ad data, etc.).",
    )
    source_lead_id = models.CharField(
        max_length=200, blank=True, default="",
        db_index=True,
        help_text="External lead ID from the source platform.",
    )

    # ---- Ad Campaign Attribution ---------------------------
    # Which ad campaign / ad this lead came from (Meta, Google, etc.).
    campaign_name = models.CharField(
        max_length=300, blank=True, default="", db_index=True,
        help_text="Ad campaign name the lead came from (e.g. Meta/Google campaign).",
    )
    ad_name = models.CharField(
        max_length=300, blank=True, default="",
        help_text="Specific ad / ad set name within the campaign.",
    )

    # ---- Follow-up -----------------------------------------
    next_followup_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text="Next scheduled follow-up datetime (denormalized for fast querying).",
    )
    last_contacted_at = models.DateTimeField(null=True, blank=True)
    contact_count = models.PositiveIntegerField(
        default=0,
        help_text="Total number of contact attempts (calls + messages).",
    )

    # ---- TRAI DND -------------------------------------------
    is_dnd = models.BooleanField(
        default=False,
        help_text="True if number is in TRAI Do-Not-Disturb registry.",
    )

    # ---- Import Tracking -----------------------------------
    import_job = models.ForeignKey(
        "LeadImportJob",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="leads",
    )

    # ---- Tags ---------------------------------------------
    tags = models.JSONField(
        default=list, blank=True,
        help_text='List of tag strings. E.g. ["premium", "referral", "hot"]',
    )

    # ---- Calling Queue: work-state & exclusive lock --------
    # These power the industry-grade queue system: a lead is "worked" the
    # first time a disposition is saved or its status leaves NEW, so it can
    # never re-appear as a fresh/new lead. The lock fields guarantee a lead
    # is only ever handed to ONE agent at a time (no double-dialing).
    has_been_worked = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True once the lead has been dialed/dispositioned at least "
                  "once. A worked lead is never treated as a new lead again.",
    )
    last_dialed_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text="Last time this lead was dialed from a queue (redial cooldown).",
    )
    locked_by = models.ForeignKey(
        "authentication.Agent",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="locked_leads",
        help_text="Agent who currently has this lead checked out from a queue. "
                  "Prevents another agent from pulling the same lead.",
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    lock_expires_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text="When the queue lock auto-expires and the lead becomes "
                  "available to pull again.",
    )
    locked_queue = models.ForeignKey(
        "CallQueue",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="locked_leads",
    )

    class Meta:
        verbose_name = "Lead"
        verbose_name_plural = "Leads"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "assigned_to"]),
            models.Index(fields=["source", "created_at"]),
            models.Index(fields=["next_followup_at", "assigned_to"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["is_deleted", "status"]),
            # Queue eligibility lookups.
            models.Index(fields=["assigned_to", "has_been_worked", "status"]),
            models.Index(fields=["lock_expires_at"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.phone}) [{self.get_status_display()}]"

    def save(self, *args, **kwargs):
        # Normalize choice fields to lowercase so they always match the
        # lowercase constants used in filters, permissions, and the mobile
        # auto-dialer queues (status=new, priority=hot, etc.).
        if self.status:
            self.status = self.status.lower()
        if self.priority:
            self.priority = self.priority.lower()
        if self.source:
            self.source = self.source.lower()
        super().save(*args, **kwargs)

    # ---- Properties ----------------------------------------

    @property
    def display_phone(self) -> str:
        """Mask phone for display to agents (privacy). Admins see full number."""
        from apps.core.utils import mask_phone_number
        return mask_phone_number(self.phone)

    @property
    def is_hot(self) -> bool:
        return self.priority == LeadPriority.HOT or self.score >= 80

    @property
    def days_since_last_contact(self) -> int | None:
        if not self.last_contacted_at:
            return None
        return (timezone.now() - self.last_contacted_at).days

    @property
    def followup_overdue(self) -> bool:
        if not self.next_followup_at:
            return False
        return timezone.now() > self.next_followup_at

    @property
    def is_locked(self) -> bool:
        """True if the lead is currently checked out (lock not expired)."""
        if not self.locked_by_id or not self.lock_expires_at:
            return False
        return timezone.now() < self.lock_expires_at

    # ---- Methods -------------------------------------------

    def mark_worked(self, *, dialed: bool = False):
        """
        Mark the lead as having been worked at least once.
        Idempotent — once worked, always worked (never a 'new' lead again).
        """
        fields = []
        if not self.has_been_worked:
            self.has_been_worked = True
            fields.append("has_been_worked")
        if dialed:
            self.last_dialed_at = timezone.now()
            fields.append("last_dialed_at")
        if fields:
            self.save(update_fields=fields)

    def release_lock(self):
        """Clear the queue checkout lock on this lead."""
        self.locked_by = None
        self.locked_at = None
        self.lock_expires_at = None
        self.locked_queue = None
        self.save(update_fields=[
            "locked_by", "locked_at", "lock_expires_at", "locked_queue",
        ])

    def assign_to(self, agent, assigned_by=None):
        """Assign lead to an agent and log the activity."""
        old_agent = self.assigned_to
        self.assigned_to = agent
        self.assigned_at = timezone.now()
        self.save(update_fields=["assigned_to", "assigned_at"])
        LeadActivity.objects.create(
            lead=self,
            activity_type="assigned",
            description=(
                f"Lead assigned to {agent.name}"
                + (f" by {assigned_by.name}" if assigned_by else "")
            ),
            performed_by=assigned_by or agent,
            meta={"old_agent": str(old_agent), "new_agent": agent.name},
        )

    def update_status(self, new_status: str, agent=None, note: str = ""):
        """Change lead status and log the transition."""
        old_status = self.status
        self.status = new_status
        # Any status change away from NEW permanently marks the lead as worked
        # so it can never be served again from a 'new leads' queue.
        update_fields = ["status"]
        if new_status != LeadStatus.NEW and not self.has_been_worked:
            self.has_been_worked = True
            update_fields.append("has_been_worked")
        self.save(update_fields=update_fields)
        LeadActivity.objects.create(
            lead=self,
            activity_type="status_change",
            description=(
                f"Status: {old_status} → {new_status}"
                + (f". {note}" if note else "")
            ),
            performed_by=agent,
            meta={"old_status": old_status, "new_status": new_status},
        )

    def log_contact(self, contact_type: str = "call"):
        """Record that the lead was contacted."""
        self.last_contacted_at = timezone.now()
        self.contact_count += 1
        self.save(update_fields=["last_contacted_at", "contact_count"])


# ============================================================
# Call Queue (industry-grade calling queue system)
# ============================================================

class CallQueue(TimeStampedModel):
    """
    An admin-defined calling queue. Agents pull leads one at a time from a
    queue; the system guarantees a lead is only handed to one agent at a
    time and never repeated.

    A queue is essentially a saved set of filter criteria + an ordering +
    a roster of agents allowed to work it.
    """

    ORDER_PRIORITY = "priority"
    ORDER_OLDEST = "oldest"
    ORDER_NEWEST = "newest"
    ORDER_SCORE = "score"
    ORDER_FOLLOWUP = "followup_due"
    ORDER_CHOICES = [
        (ORDER_PRIORITY, "Highest priority first"),
        (ORDER_OLDEST, "Oldest leads first"),
        (ORDER_NEWEST, "Newest leads first"),
        (ORDER_SCORE, "Highest score first"),
        (ORDER_FOLLOWUP, "Follow-up due first"),
    ]

    MODE_MANUAL = "manual"      # Agents pull leads on demand
    MODE_AUTO = "auto"          # Power-dialer: serve continuously
    MODE_CHOICES = [
        (MODE_MANUAL, "Manual pull"),
        (MODE_AUTO, "Auto / power-dialer"),
    ]

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)

    # ---- Filter criteria (all optional; empty list = no constraint) ----
    filter_statuses = models.JSONField(
        default=list, blank=True,
        help_text='Lead statuses this queue serves, e.g. ["new", "contacted"].',
    )
    filter_priorities = models.JSONField(
        default=list, blank=True,
        help_text='Priorities to include, e.g. ["hot", "warm"].',
    )
    filter_sources = models.JSONField(
        default=list, blank=True,
        help_text="Lead sources to include.",
    )
    filter_tags = models.JSONField(
        default=list, blank=True,
        help_text="Only leads having ANY of these tags.",
    )
    only_unworked = models.BooleanField(
        default=False,
        help_text="If true, only serve leads that have never been worked "
                  "(fresh leads). Guarantees worked leads are never repeated "
                  "as new.",
    )
    only_followup_due = models.BooleanField(
        default=False,
        help_text="If true, only serve leads whose follow-up is due/overdue.",
    )
    exclude_dnd = models.BooleanField(
        default=True,
        help_text="Skip leads on the TRAI DND registry.",
    )

    # ---- Behaviour -----------------------------------------
    order_by = models.CharField(
        max_length=20, choices=ORDER_CHOICES, default=ORDER_PRIORITY,
    )
    mode = models.CharField(
        max_length=10, choices=MODE_CHOICES, default=MODE_MANUAL,
    )
    redial_cooldown_hours = models.PositiveIntegerField(
        default=24,
        help_text="A lead dialed from a queue won't be served again until "
                  "this many hours have passed.",
    )
    lock_ttl_minutes = models.PositiveIntegerField(
        default=30,
        help_text="How long a pulled lead stays locked to an agent before it "
                  "auto-releases back to the queue.",
    )

    created_by = models.ForeignKey(
        "authentication.Agent",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="created_queues",
    )

    class Meta:
        verbose_name = "Call Queue"
        verbose_name_plural = "Call Queues"
        ordering = ["name"]

    def __str__(self):
        return self.name

    # ---- Eligibility query ---------------------------------

    def eligible_leads(self, agent):
        """
        Return the queryset of leads currently eligible to be served from this
        queue to the given agent — applying every integrity rule:

          * only leads ASSIGNED to this agent (no cross-agent leakage),
          * not soft-deleted,
          * matching the queue's status/priority/source/tag filters,
          * not currently locked by ANOTHER agent (or lock expired),
          * past the redial cooldown,
          * (optionally) only unworked leads,
          * (optionally) only follow-up-due leads,
          * (optionally) excluding DND numbers,
        ordered per the queue's order_by.
        """
        from django.db.models import Q
        from apps.core.constants import LeadStatus

        qs = Lead.objects.filter(is_deleted=False, assigned_to=agent)

        # Never serve leads in terminal states — regardless of queue config.
        qs = qs.exclude(status__in=LeadStatus.FINAL_STATUSES)

        if self.filter_statuses:
            qs = qs.filter(status__in=[s.lower() for s in self.filter_statuses])
        if self.filter_priorities:
            qs = qs.filter(priority__in=[p.lower() for p in self.filter_priorities])
        if self.filter_sources:
            qs = qs.filter(source__in=[s.lower() for s in self.filter_sources])
        if self.filter_tags:
            # JSONField list — match leads whose tags contain ANY listed tag.
            tag_q = Q()
            for tag in self.filter_tags:
                tag_q |= Q(tags__contains=tag)
            qs = qs.filter(tag_q)
        if self.only_unworked:
            qs = qs.filter(has_been_worked=False)
        if self.only_followup_due:
            qs = qs.filter(
                next_followup_at__isnull=False,
                next_followup_at__lte=timezone.now(),
            )
        if self.exclude_dnd:
            qs = qs.filter(is_dnd=False)

        now = timezone.now()

        # Exclude every lead that is currently locked (lock not yet expired),
        # regardless of who holds it. This guarantees "pull next" always returns
        # a fresh, distinct lead and the same lead is never handed out twice —
        # neither to another agent nor repeatedly to the same agent.
        qs = qs.exclude(locked_by__isnull=False, lock_expires_at__gt=now)

        # Redial cooldown.
        if self.redial_cooldown_hours:
            from datetime import timedelta
            cutoff = now - timedelta(hours=self.redial_cooldown_hours)
            qs = qs.filter(
                Q(last_dialed_at__isnull=True) | Q(last_dialed_at__lt=cutoff)
            )

        return self._apply_ordering(qs)

    def _apply_ordering(self, qs):
        if self.order_by == self.ORDER_OLDEST:
            return qs.order_by("created_at")
        if self.order_by == self.ORDER_NEWEST:
            return qs.order_by("-created_at")
        if self.order_by == self.ORDER_SCORE:
            return qs.order_by("-score", "created_at")
        if self.order_by == self.ORDER_FOLLOWUP:
            return qs.order_by("next_followup_at")
        # Default: priority rank (hot > warm > cold), then score, then oldest.
        from django.db.models import Case, When, IntegerField, Value
        return qs.annotate(
            _prio_rank=Case(
                When(priority=LeadPriority.HOT, then=Value(3)),
                When(priority=LeadPriority.WARM, then=Value(2)),
                When(priority=LeadPriority.COLD, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        ).order_by("-_prio_rank", "-score", "created_at")


class CallQueueMembership(models.Model):
    """Roster: which agents are allowed to work a given queue."""

    queue = models.ForeignKey(
        CallQueue, on_delete=models.CASCADE, related_name="memberships"
    )
    agent = models.ForeignKey(
        "authentication.Agent",
        on_delete=models.CASCADE,
        related_name="queue_memberships",
    )
    added_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("queue", "agent")
        verbose_name = "Call Queue Membership"
        verbose_name_plural = "Call Queue Memberships"

    def __str__(self):
        return f"{self.agent.name} → {self.queue.name}"


# ============================================================
# FollowUp
# ============================================================

class FollowUp(TimeStampedModel):
    """
    A scheduled follow-up action for a lead.
    Can be a callback, WhatsApp, email, physical visit, etc.
    """

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="followups")
    assigned_to = models.ForeignKey(
        "authentication.Agent",
        on_delete=models.CASCADE,
        related_name="followups",
    )

    followup_type = models.CharField(
        max_length=20,
        choices=FollowUpType.CHOICES,
        default=FollowUpType.CALL,
    )
    scheduled_at = models.DateTimeField(db_index=True)
    notes = models.TextField(blank=True, default="")

    # Status
    is_completed = models.BooleanField(default=False, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_notes = models.TextField(blank=True, default="")

    # Reminder
    reminder_sent = models.BooleanField(default=False)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Follow-up"
        verbose_name_plural = "Follow-ups"
        ordering = ["scheduled_at"]
        indexes = [
            models.Index(fields=["scheduled_at", "is_completed", "assigned_to"]),
        ]

    def __str__(self):
        return (
            f"[{self.get_followup_type_display()}] "
            f"{self.lead.name} @ {self.scheduled_at.strftime('%d %b %H:%M')}"
        )

    def complete(self, notes: str = "", agent=None):
        """Mark follow-up as completed."""
        self.is_completed = True
        self.completed_at = timezone.now()
        self.completion_notes = notes
        self.save(update_fields=["is_completed", "completed_at", "completion_notes"])

        # Update lead's next_followup_at to the next pending follow-up
        next_fu = FollowUp.objects.filter(
            lead=self.lead, is_completed=False, scheduled_at__gt=timezone.now()
        ).order_by("scheduled_at").first()
        self.lead.next_followup_at = next_fu.scheduled_at if next_fu else None
        self.lead.save(update_fields=["next_followup_at"])

        # Log activity
        LeadActivity.objects.create(
            lead=self.lead,
            activity_type="followup_completed",
            description=f"Follow-up ({self.get_followup_type_display()}) completed. {notes}",
            performed_by=agent,
        )


# ============================================================
# LeadNote
# ============================================================

class LeadNote(TimeStampedModel):
    """
    A note or comment attached to a lead.
    Records of agent interactions, observations, customer feedback.
    """

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="notes")
    agent = models.ForeignKey(
        "authentication.Agent",
        on_delete=models.SET_NULL,
        null=True,
        related_name="lead_notes",
    )
    content = models.TextField()
    is_pinned = models.BooleanField(default=False)

    # Attach files to notes (call recordings, photos, documents)
    attachment = models.FileField(upload_to="lead_attachments/", blank=True, null=True)

    class Meta:
        verbose_name = "Lead Note"
        verbose_name_plural = "Lead Notes"
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return f"Note on {self.lead.name} by {self.agent.name if self.agent else 'system'}"


# ============================================================
# LeadActivity (Immutable Feed)
# ============================================================

class LeadActivity(models.Model):
    """
    Immutable audit trail of everything that happened to a lead.
    Append-only — never update or delete entries.

    Types: call, whatsapp, email, sms, status_change, assigned,
           note_added, followup_created, followup_completed, imported
    """

    ACTIVITY_TYPES = [
        ("call", "Call"),
        ("whatsapp", "WhatsApp"),
        ("email", "Email"),
        ("sms", "SMS"),
        ("status_change", "Status Change"),
        ("assigned", "Assigned"),
        ("note_added", "Note Added"),
        ("followup_created", "Follow-up Created"),
        ("followup_completed", "Follow-up Completed"),
        ("imported", "Imported"),
        ("score_update", "Score Updated"),
        ("other", "Other"),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="activities")
    activity_type = models.CharField(max_length=30, choices=ACTIVITY_TYPES, db_index=True)
    description = models.TextField()
    performed_by = models.ForeignKey(
        "authentication.Agent",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="lead_activities",
    )
    meta = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Lead Activity"
        verbose_name_plural = "Lead Activities"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"[{self.activity_type}] {self.lead.name} — {self.timestamp:%d %b %H:%M}"


# ============================================================
# Custom Fields (tenant-defined extra fields on leads)
# ============================================================

class CustomField(TimeStampedModel):
    """
    Tenant-defined custom field for the Lead model.
    Rendered as extra input in the lead form.
    Limited by plan (max_custom_fields).
    """

    FIELD_TYPES = [
        ("text", "Short Text"),
        ("textarea", "Long Text"),
        ("number", "Number"),
        ("date", "Date"),
        ("dropdown", "Dropdown"),
        ("checkbox", "Checkbox (Yes/No)"),
        ("phone", "Phone Number"),
        ("url", "URL"),
    ]

    name = models.CharField(max_length=100, help_text="Label shown in the form.")
    field_key = models.SlugField(
        max_length=50, unique=True,
        help_text="Internal key used in API. Auto-generated from name.",
    )
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, default="text")
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    # For dropdown fields — store options as JSON list
    options = models.JSONField(
        default=list, blank=True,
        help_text='For dropdown fields: ["Option A", "Option B"]',
    )
    placeholder = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        verbose_name = "Custom Field"
        verbose_name_plural = "Custom Fields"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_field_type_display()})"

    def save(self, *args, **kwargs):
        if not self.field_key:
            from django.utils.text import slugify
            self.field_key = slugify(self.name).replace("-", "_")
        super().save(*args, **kwargs)


class CustomFieldValue(models.Model):
    """
    Stores the value of a CustomField for a specific Lead.
    EAV (Entity-Attribute-Value) pattern — bounded to plan limit.
    """

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="custom_field_values")
    field = models.ForeignKey(CustomField, on_delete=models.CASCADE, related_name="values")
    value = models.TextField(blank=True, default="")

    class Meta:
        unique_together = ("lead", "field")
        verbose_name = "Custom Field Value"

    def __str__(self):
        return f"{self.field.name}: {self.value[:50]}"


# ============================================================
# Lead Import Job
# ============================================================

class LeadImportJob(TimeStampedUUIDModel):
    """
    Tracks a CSV/Excel import operation.
    Stores per-row results so the user can see errors and download a failure report.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("partial", "Partial Success"),
    ]

    imported_by = models.ForeignKey(
        "authentication.Agent",
        on_delete=models.SET_NULL,
        null=True,
        related_name="import_jobs",
    )
    file = models.FileField(upload_to="lead_imports/")
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)

    # Column mapping (user maps CSV columns to Lead fields)
    column_mapping = models.JSONField(
        default=dict,
        help_text='e.g. {"A": "name", "B": "phone", "C": "city"}',
    )
    # Import options
    duplicate_action = models.CharField(
        max_length=20,
        choices=[
            ("skip", "Skip duplicates"),
            ("update", "Update existing"),
            ("create_new", "Create new (allow duplicates)"),
        ],
        default="skip",
    )
    default_assigned_to = models.ForeignKey(
        "authentication.Agent",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="default_import_assignments",
    )
    default_source = models.CharField(
        max_length=50, choices=LeadSource.CHOICES, default=LeadSource.MANUAL
    )

    # Results
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    successful_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    duplicate_rows = models.PositiveIntegerField(default=0)

    # Store row-level errors (list of {row, field, error})
    row_errors = models.JSONField(default=list, blank=True)

    # When import completed
    completed_at = models.DateTimeField(null=True, blank=True)

    # Celery task ID for progress tracking
    celery_task_id = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        verbose_name = "Lead Import Job"
        verbose_name_plural = "Lead Import Jobs"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Import: {self.original_filename} "
            f"[{self.get_status_display()}] "
            f"({self.successful_rows}/{self.total_rows} ok)"
        )

    @property
    def progress_percent(self) -> int:
        if not self.total_rows:
            return 0
        return int((self.processed_rows / self.total_rows) * 100)

    def mark_completed(self):
        self.status = (
            "completed" if self.failed_rows == 0
            else "partial" if self.successful_rows > 0
            else "failed"
        )
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at"])
