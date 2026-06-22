"""
TeleCRM Backend — apps/authentication/models.py

Per-tenant models (live in EACH tenant's PostgreSQL schema).

Agent            : The CRM user. Custom AbstractBaseUser — completely separate
                   from Django's auth.User. Role-based, no Django permissions.
AgentLoginSession: Tracks active sessions for the agent monitoring dashboard.
Team             : Groups of agents managed by a manager.
AgentTeam        : M2M with metadata (team lead flag, join date).

These models are in TENANT_APPS — one table per tenant schema.
"""
import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from apps.core.constants import AgentRole, AgentWorkStatus
from apps.core.models import TimeStampedModel
from apps.core.storage import get_profile_photo_upload_path


# ============================================================
# Agent Manager
# ============================================================

class AgentManager(BaseUserManager):
    """Custom manager for the Agent model."""

    def create_agent(self, email, name, password=None, **extra_fields):
        """Create a regular agent."""
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        agent = self.model(email=email, name=name, **extra_fields)
        agent.set_password(password)
        agent.save(using=self._db)
        return agent

    def create_tenant_admin(self, email, name, password=None, **extra_fields):
        """Create a tenant admin agent."""
        extra_fields.setdefault("role", AgentRole.ADMIN)
        extra_fields.setdefault("is_tenant_admin", True)
        return self.create_agent(email, name, password, **extra_fields)

    def active(self):
        return self.get_queryset().filter(is_active=True)

    def admins(self):
        return self.get_queryset().filter(role=AgentRole.ADMIN, is_active=True)

    def managers_and_above(self):
        return self.get_queryset().filter(
            role__in=[AgentRole.ADMIN, AgentRole.MANAGER], is_active=True
        )


# ============================================================
# Agent Model
# ============================================================

class Agent(AbstractBaseUser, TimeStampedModel):
    """
    The CRM agent/user model.
    Lives in each tenant's PostgreSQL schema — completely isolated.

    Authentication: email + password → JWT tokens
    Authorization: role-based (see AgentRole in constants.py)

    This model does NOT extend PermissionsMixin — we use our own
    role-based permission system instead of Django's group/permission system.
    """

    # ---- Identity -----------------------------------------
    email = models.EmailField(
        unique=True,
        db_index=True,
        help_text="Login email. Must be unique within this tenant.",
    )
    name = models.CharField(max_length=150)
    phone = models.CharField(
        max_length=15,
        blank=True,
        default="",
        validators=[
            RegexValidator(
                r"^\+91[6-9]\d{9}$",
                "Enter a valid Indian mobile number (+91XXXXXXXXXX).",
            )
        ],
    )
    employee_id = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Company employee ID (optional, for internal reference).",
    )

    # ---- Profile ------------------------------------------
    profile_photo = models.ImageField(
        upload_to=get_profile_photo_upload_path,
        blank=True,
        null=True,
    )

    # ---- Role & Permissions --------------------------------
    role = models.CharField(
        max_length=20,
        choices=AgentRole.CHOICES,
        default=AgentRole.AGENT,
        db_index=True,
    )
    is_tenant_admin = models.BooleanField(
        default=False,
        help_text="Designates this agent as the primary tenant administrator.",
    )

    # ---- Status --------------------------------------------
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Deactivate to block login without deleting the agent.",
    )
    must_change_password = models.BooleanField(
        default=False,
        help_text="Force password change on next login (set on account creation).",
    )

    # ---- Locale -------------------------------------------
    timezone = models.CharField(max_length=50, default="Asia/Kolkata")
    language_preference = models.CharField(
        max_length=5,
        choices=[("en", "English"), ("hi", "Hindi")],
        default="en",
    )

    # ---- Shift Schedule ------------------------------------
    shift_start = models.TimeField(
        null=True, blank=True,
        help_text="Shift start time (for availability display in monitoring).",
    )
    shift_end = models.TimeField(
        null=True, blank=True,
        help_text="Shift end time.",
    )
    working_days = models.JSONField(
        default=list,
        blank=True,
        help_text="List of working day numbers: 0=Mon, 1=Tue, ..., 6=Sun. "
                  "E.g., [0,1,2,3,4] for Monday–Friday.",
    )

    # ---- Call Settings ------------------------------------
    fcm_token = models.TextField(
        blank=True,
        default="",
        help_text="Firebase Cloud Messaging token for push notifications.",
    )

    # ---- Login Tracking (for monitoring dashboard) ---------
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    total_login_count = models.PositiveIntegerField(default=0)
    last_active_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Last time the agent made an API request.",
    )

    # AbstractBaseUser required fields
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = AgentManager()

    class Meta:
        verbose_name = "Agent"
        verbose_name_plural = "Agents"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        self.role = self.role.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} <{self.email}> [{self.get_role_display()}]"

    def get_username(self):
        return self.email

    def get_full_name(self):
        return self.name

    def get_short_name(self):
        return self.name.split()[0] if self.name else self.email

    # ---- Role helpers -------------------------------------

    @property
    def is_admin(self) -> bool:
        return self.role == AgentRole.ADMIN

    @property
    def is_manager(self) -> bool:
        return self.role in [AgentRole.MANAGER, AgentRole.ADMIN]

    @property
    def role_level(self) -> int:
        """Numeric role level for hierarchy comparisons."""
        return AgentRole.HIERARCHY.get(self.role, 0)

    def can_manage(self, other_agent) -> bool:
        """Returns True if this agent can manage the other agent."""
        return self.role_level > other_agent.role_level

    def update_last_active(self):
        """Called on each API request to track agent activity."""
        self.last_active_at = timezone.now()
        self.save(update_fields=["last_active_at"])

    @property
    def is_online(self) -> bool:
        """Agent is 'online' if active in the last 5 minutes."""
        if not self.last_active_at:
            return False
        from datetime import timedelta
        return (timezone.now() - self.last_active_at) < timedelta(minutes=5)


# ============================================================
# Agent Login Session
# ============================================================

class AgentLoginSession(TimeStampedModel):
    """
    Tracks individual login sessions for agents.
    Used in the monitoring dashboard to show active sessions.
    """

    agent = models.ForeignKey(
        Agent, on_delete=models.CASCADE, related_name="login_sessions"
    )
    login_time = models.DateTimeField(default=timezone.now)
    logout_time = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    device_type = models.CharField(
        max_length=20,
        choices=[("mobile", "Mobile App"), ("web", "Web Browser"), ("api", "API")],
        default="mobile",
    )
    is_active = models.BooleanField(
        default=True, db_index=True,
        help_text="Active session (not yet logged out).",
    )
    # JWT jti claim — used to invalidate a specific session
    jwt_jti = models.CharField(max_length=100, blank=True, default="", db_index=True)

    class Meta:
        verbose_name = "Login Session"
        verbose_name_plural = "Login Sessions"
        ordering = ["-login_time"]

    def __str__(self):
        return f"{self.agent.name} — {self.login_time.strftime('%Y-%m-%d %H:%M')}"

    def logout(self):
        self.is_active = False
        self.logout_time = timezone.now()
        self.save(update_fields=["is_active", "logout_time"])


# ============================================================
# Team & AgentTeam
# ============================================================

class Team(TimeStampedModel):
    """A team of agents managed by one or more managers."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Team"
        verbose_name_plural = "Teams"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def member_count(self) -> int:
        return self.memberships.filter(agent__is_active=True).count()


class AgentTeam(models.Model):
    """M2M relationship between Agent and Team, with extra metadata."""

    agent = models.ForeignKey(
        Agent, on_delete=models.CASCADE, related_name="team_memberships"
    )
    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="memberships"
    )
    is_team_lead = models.BooleanField(
        default=False,
        help_text="Team leads can view their team members' leads.",
    )
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("agent", "team")
        verbose_name = "Agent Team Membership"
        verbose_name_plural = "Agent Team Memberships"

    def __str__(self):
        role = "Lead" if self.is_team_lead else "Member"
        return f"{self.agent.name} → {self.team.name} [{role}]"


# ============================================================
# Live Agent Monitoring — Status & Time Tracking
# ============================================================

class AgentStatus(TimeStampedModel):
    """
    Current live work status for an agent (one row per agent).

    Presence is tied to an auto-dial session. The mobile app reports
    transitions (available → on_call → wrap_up, plus manual break) and a
    periodic heartbeat. `since` marks when the current status began so the UI
    can show a live-ticking timer; `last_seen` drives stale → offline detection.
    """

    agent = models.OneToOneField(
        Agent, on_delete=models.CASCADE, related_name="work_status"
    )
    status = models.CharField(
        max_length=20,
        choices=AgentWorkStatus.CHOICES,
        default=AgentWorkStatus.OFFLINE,
        db_index=True,
    )
    since = models.DateTimeField(
        default=timezone.now,
        help_text="When the current status began (for live duration display).",
    )
    last_seen = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="Last heartbeat — used to flip stale sessions to offline.",
    )
    session_started_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the current auto-dial session began (null when offline).",
    )
    current_call_id = models.PositiveIntegerField(null=True, blank=True)
    current_lead_id = models.PositiveIntegerField(null=True, blank=True)
    break_reason = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        verbose_name = "Agent Status"
        verbose_name_plural = "Agent Statuses"

    def __str__(self):
        return f"{self.agent.name}: {self.status}"

    @property
    def is_online(self) -> bool:
        return self.status in AgentWorkStatus.ONLINE_STATUSES


class AgentStatusLog(models.Model):
    """
    Append-only log of every status interval, for time accounting and history.

    Each transition closes the open row (sets ended_at + duration_seconds) and
    opens a new one. Daily totals (talk/wrap/break/available) are summed from
    these rows plus the currently-open interval.
    """

    agent = models.ForeignKey(
        Agent, on_delete=models.CASCADE, related_name="status_logs"
    )
    status = models.CharField(max_length=20, choices=AgentWorkStatus.CHOICES, db_index=True)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    break_reason = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        verbose_name = "Agent Status Log"
        verbose_name_plural = "Agent Status Logs"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["agent", "started_at"], name="auth_agentstatuslog_agent_started_idx"),
        ]

    def __str__(self):
        return f"{self.agent_id} {self.status} @ {self.started_at:%Y-%m-%d %H:%M}"

    def close(self, at=None):
        """Close this interval, computing its duration."""
        at = at or timezone.now()
        self.ended_at = at
        self.duration_seconds = max(0, int((at - self.started_at).total_seconds()))
        self.save(update_fields=["ended_at", "duration_seconds"])
