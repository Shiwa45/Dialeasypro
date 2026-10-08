"""
TeleCRM Backend — apps/calls/models.py

Per-tenant models for call management.

CallLog         : Record of every outbound/inbound call made through the CRM.
CallDisposition : Outcome configuration (customisable outcome options).
CallRecording   : Metadata + S3 link for recorded calls.

Indian context:
- Telecom integrations: Exotel, MCUBE, Knowlarity, Ozonetel
- Call direction: outbound (agent dials) / inbound (lead calls)
- Click-to-call: agent clicks in CRM → integration dials both numbers
"""
import uuid

from django.db import models
from django.utils import timezone

from apps.core.constants import CallDirection, DispositionCategory, LeadStatus
from apps.core.models import TimeStampedModel, TimeStampedUUIDModel


class CallDisposition(TimeStampedModel):
    """
    Configurable call outcome options (per tenant).
    Examples: Connected, Not Reachable, Busy, Switched Off, Wrong Number, Callback Requested
    Tenants can add custom dispositions.
    """

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=50, unique=True)
    is_positive = models.BooleanField(
        default=False,
        help_text="True for positive outcomes (Connected, Interested, etc.)",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    # Auto-set next follow-up when this disposition is selected
    auto_followup_hours = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="If set, auto-schedule a follow-up this many hours after call.",
    )
    # What a call with this outcome makes of the lead. Without it an outcome
    # never touched the lead: "Connected – Interested" left the lead at
    # Attempted, so filtering Leads by Interested found none of them.
    lead_status = models.CharField(
        max_length=20, blank=True, default="", choices=LeadStatus.CHOICES,
        help_text="Move the lead to this status when a call is saved with this outcome. Blank = leave it.",
    )
    # Which group the outcome belongs to. The agent only sees the outcomes of
    # the group matching the call status (answered or not), and the server
    # refuses a mismatch. This replaces marks_connected, which let an outcome
    # OVERWRITE the call status: a 0-second unanswered call given
    # "Connected – Interested" was stored as connected.
    category = models.CharField(
        max_length=20, choices=DispositionCategory.CHOICES,
        default=DispositionCategory.CONNECTED, db_index=True,
        help_text="Connected (call answered) or not connected.",
    )
    # Kept in step with `category` for app builds that still read it.
    # Never used to change a call's status any more.
    marks_connected = models.BooleanField(
        null=True, blank=True, default=None,
        help_text="Derived from category — kept for older app builds.",
    )
    # A seeded default: its slug and group are fixed (other parts of the
    # product refer to them) and it can be switched off but not deleted.
    is_system = models.BooleanField(default=False)
    # "Asked not to call": the lead is marked DND and leaves the queues.
    sets_dnd = models.BooleanField(
        default=False, help_text="Mark the lead Do Not Disturb when a call is saved with this outcome.",
    )

    class Meta:
        verbose_name = "Call Disposition"
        verbose_name_plural = "Call Dispositions"
        ordering = ["sort_order", "name"]

    def save(self, *args, **kwargs):
        self.marks_connected = self.category == DispositionCategory.CONNECTED
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = list(set(update_fields) | {"marks_connected"})
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class CallLog(TimeStampedModel):
    """
    A record of a single call (outbound or inbound).
    Created automatically when a call is initiated via click-to-call,
    or manually when agent logs a call they made outside the CRM.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ---- Participants --------------------------------------
    agent = models.ForeignKey(
        "authentication.Agent",
        on_delete=models.SET_NULL,
        null=True,
        related_name="calls",
    )
    lead = models.ForeignKey(
        "leads.Lead",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="calls",
        help_text="Associated lead. Null for calls not linked to a lead.",
    )

    # ---- Call Details -------------------------------------
    direction = models.CharField(
        max_length=10,
        choices=CallDirection.CHOICES,
        default=CallDirection.OUTBOUND,
        db_index=True,
    )
    phone_number = models.CharField(
        max_length=15,
        help_text="The external number dialled/received.",
    )
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # ---- Duration & Outcome --------------------------------
    # Duration in seconds (0 if not connected)
    duration_seconds = models.PositiveIntegerField(default=0)
    is_connected = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if the call was actually answered.",
    )

    disposition = models.ForeignKey(
        CallDisposition,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="calls",
    )
    notes = models.TextField(blank=True, default="")

    # The lead's name when the call was made. Deleting a lead clears the
    # link, and the call history then said nothing about who was called.
    lead_label = models.CharField(max_length=200, blank=True, default="")

    # Sent by the app/web with each logged call. A retry after a lost
    # response returns the call already saved instead of saving it twice.
    client_call_id = models.CharField(max_length=64, blank=True, default="", db_index=True)

    # ---- Integration Metadata ----------------------------
    # Telecom provider (Exotel, MCUBE, etc.) call ID
    provider = models.CharField(
        max_length=30,
        blank=True,
        default="",
        choices=[
            ("exotel", "Exotel"),
            ("mcube", "MCUBE"),
            ("knowlarity", "Knowlarity"),
            ("ozonetel", "Ozonetel"),
            ("manual", "Manual Entry"),
            ("other", "Other"),
        ],
    )
    provider_call_id = models.CharField(
        max_length=200, blank=True, default="",
        db_index=True,
        help_text="Call SID / ID from the telecom provider.",
    )
    provider_meta = models.JSONField(
        default=dict, blank=True,
        help_text="Raw webhook payload from the provider.",
    )

    # ---- Cost Tracking ------------------------------------
    call_cost_paise = models.PositiveIntegerField(
        default=0,
        help_text="Call cost in Indian paise (1 rupee = 100 paise). Set by provider webhook.",
    )

    class Meta:
        verbose_name = "Call Log"
        verbose_name_plural = "Call Logs"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["agent", "started_at"]),
            models.Index(fields=["lead", "started_at"]),
            models.Index(fields=["started_at", "direction"]),
            models.Index(fields=["is_connected", "started_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["agent", "client_call_id"],
                condition=~models.Q(client_call_id=""),
                name="calllog_unique_client_call_id",
            ),
        ]

    def save(self, *args, **kwargs):
        self.apply_outcome_rules()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = list(set(update_fields) | {"duration_seconds", "lead_label"})
        super().save(*args, **kwargs)

    def apply_outcome_rules(self):
        """
        Keep `duration_seconds` consistent with the call, and remember the
        lead's name on the call.

        1. is_connected is never changed here: it is what the phone or the
           provider reported (an outcome used to overwrite it).
        2. A connected call reported with no duration gets one from its own
           timestamps — the dialer often sends start and end but duration 0,
           which made every talk-time figure in the product read ~0.

        An unanswered call keeps whatever duration it was given (a provider's
        ring time); talk-time figures count connected calls only.
        """
        # The call status is a fact from the phone or the provider; the
        # outcome no longer overwrites it (see CallDisposition.category).
        if self.lead_id and not self.lead_label:
            lead = getattr(self, "lead", None)
            if lead is not None:
                self.lead_label = (lead.name or "")[:200]

        if not self.is_connected:
            return
        if not self.duration_seconds and self.ended_at:
            begin = self.connected_at or self.started_at
            if begin and self.ended_at > begin:
                self.duration_seconds = int((self.ended_at - begin).total_seconds())

    def __str__(self):
        direction = "→" if self.direction == CallDirection.OUTBOUND else "←"
        duration = f"{self.duration_seconds}s" if self.is_connected else "no answer"
        return (
            f"[{direction}] {self.agent.name if self.agent else '?'} "
            f"→ {self.phone_number} | {duration} | {self.started_at:%d %b %H:%M}"
        )

    @property
    def duration_display(self) -> str:
        """Human-readable call duration."""
        if not self.duration_seconds:
            return "—"
        minutes, seconds = divmod(self.duration_seconds, 60)
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    @property
    def call_cost_rupees(self) -> float:
        return self.call_cost_paise / 100

    def mark_connected(self, connected_at=None):
        self.is_connected = True
        self.connected_at = connected_at or timezone.now()
        self.save(update_fields=["is_connected", "connected_at"])

    def mark_ended(self, ended_at=None, duration_seconds: int = None):
        self.ended_at = ended_at or timezone.now()
        if duration_seconds is not None:
            self.duration_seconds = duration_seconds
        elif self.connected_at:
            self.duration_seconds = int((self.ended_at - self.connected_at).total_seconds())
        self.save(update_fields=["ended_at", "duration_seconds"])


class CallRecording(models.Model):
    """
    Audio recording metadata for a call.
    The actual file is stored in S3 via PrivateMediaStorage.
    URL generated as a presigned S3 URL (valid 1 hour).
    """

    call = models.OneToOneField(
        CallLog, on_delete=models.CASCADE, related_name="recording"
    )
    file = models.FileField(
        upload_to="call_recordings/%Y/%m/",
        null=True, blank=True,
        help_text="Optional local/S3 copy. Primary storage is Cloudinary (cloud_url).",
    )
    # ---- Cloudinary (primary storage for app-captured recordings) ----
    cloud_url = models.URLField(
        max_length=600, blank=True, default="",
        help_text="Cloudinary secure URL of the recording audio.",
    )
    cloud_public_id = models.CharField(
        max_length=300, blank=True, default="",
        help_text="Cloudinary public_id (for deletion / re-upload).",
    )
    # ---- Source matching metadata (from the on-device recorder) ----
    source_filename = models.CharField(
        max_length=400, blank=True, default="",
        help_text="Original filename of the OEM call-recording file on the device.",
    )
    matched_by = models.CharField(
        max_length=20, blank=True, default="",
        choices=[
            ("filename_number", "Phone number in filename"),
            ("timestamp", "Timestamp + duration window"),
            ("manual", "Manual upload"),
        ],
        help_text="How the device file was matched to this call.",
    )
    file_size_bytes = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    format = models.CharField(max_length=10, default="mp3", choices=[
        ("mp3", "MP3"), ("wav", "WAV"), ("ogg", "OGG"), ("m4a", "M4A"), ("amr", "AMR"),
    ])
    # Transcription — produced by apps.ai.tasks.transcribe_call
    transcript = models.TextField(blank=True, default="")
    transcript_status = models.CharField(
        max_length=20,
        choices=[("pending", "Pending"), ("processing", "Processing"),
                 ("done", "Done"), ("failed", "Failed")],
        default="pending",
        db_index=True,
    )
    transcript_language = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Language auto-detected by the speech-to-text provider.",
    )
    transcript_provider = models.CharField(
        max_length=60, blank=True, default="",
        help_text="Speech-to-text model that produced the transcript.",
    )
    transcript_error = models.TextField(blank=True, default="")
    transcribed_at = models.DateTimeField(null=True, blank=True)

    uploaded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Call Recording"
        verbose_name_plural = "Call Recordings"

    def __str__(self):
        return f"Recording: {self.call}"

    def get_presigned_url(self, expiry_seconds: int = 3600) -> str:
        """
        Playback URL. Cloudinary URL takes priority (app-captured recordings);
        falls back to an S3 presigned URL for legacy/local files.
        """
        if self.cloud_url:
            return self.cloud_url
        if self.file:
            from apps.core.storage import get_presigned_url as _get_url
            return _get_url(str(self.file), expiry_seconds=expiry_seconds)
        return ""
