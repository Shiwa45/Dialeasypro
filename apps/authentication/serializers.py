"""
TeleCRM Backend — apps/authentication/serializers.py

DRF serializers for Agent authentication and management APIs.
"""
from django.utils import timezone
from rest_framework import serializers

from apps.authentication.models import Agent, AgentTeam, Team
from apps.core.constants import AgentRole


class AgentLoginSerializer(serializers.Serializer):
    """Validates agent login credentials."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)

    def validate_email(self, value):
        return value.lower().strip()


class AgentProfileSerializer(serializers.ModelSerializer):
    """Agent profile — returned on login and GET /api/v1/auth/me/"""

    is_online = serializers.BooleanField(read_only=True)
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    profile_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Agent
        fields = [
            "id", "email", "name", "phone", "employee_id",
            "role", "role_display", "is_tenant_admin",
            "profile_photo_url", "timezone", "language_preference",
            "is_online", "last_active_at", "last_login", "total_login_count", "created_at",
        ]
        read_only_fields = [
            "id", "email", "role", "is_tenant_admin", "created_at", "last_login", "total_login_count",
        ]

    def get_profile_photo_url(self, obj):
        if obj.profile_photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.profile_photo.url)
        return None


class AgentSerializer(serializers.ModelSerializer):
    """
    Full Agent serializer for admin/manager views.
    Includes team membership info.
    """

    role_display = serializers.CharField(source="get_role_display", read_only=True)
    teams = serializers.SerializerMethodField()
    is_online = serializers.BooleanField(read_only=True)

    class Meta:
        model = Agent
        fields = [
            "id", "email", "name", "phone", "employee_id",
            "role", "role_display", "is_tenant_admin", "is_active",
            "timezone", "shift_start", "shift_end", "working_days",
            "teams", "is_online", "last_login", "last_active_at",
            "total_login_count", "created_at",
        ]
        read_only_fields = ["id", "created_at", "last_login", "total_login_count"]

    def get_teams(self, obj):
        memberships = obj.team_memberships.select_related("team").all()
        return [
            {
                "team_id": m.team_id,
                "team_name": m.team.name,
                "is_team_lead": m.is_team_lead,
            }
            for m in memberships
        ]


class AgentCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new agent.
    Requires password — hashed before saving.
    """

    password = serializers.CharField(
        write_only=True, min_length=8,
        style={"input_type": "password"},
    )
    confirm_password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )

    class Meta:
        model = Agent
        fields = [
            "email", "name", "phone", "employee_id", "role",
            "timezone", "shift_start", "shift_end", "working_days",
            "password", "confirm_password",
        ]

    def validate_email(self, value):
        if Agent.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "An agent with this email already exists."
            )
        return value.lower()

    def validate_phone(self, value):
        if value:
            from apps.core.utils import normalize_indian_phone
            normalized = normalize_indian_phone(value)
            if not normalized:
                raise serializers.ValidationError("Invalid Indian mobile number.")
            return normalized
        return value

    def validate_working_days(self, value):
        return _clean_working_days(value)

    def validate_role(self, value):
        # Only admins can create admins (enforced in view permissions)
        check_role_in_plan(value, self.context.get("request"))
        return value

    def validate(self, data):
        if data.get("password") != data.get("confirm_password"):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        password = validated_data.pop("password")

        agent = Agent(**validated_data)
        agent.set_password(password)
        agent.must_change_password = True
        agent.save()
        return agent


def _clean_working_days(value):
    """[0=Mon .. 6=Sun], de-duplicated and sorted; empty → Monday–Saturday."""
    from apps.authentication.models import DEFAULT_WORKING_DAYS

    if value in (None, ""):
        return list(DEFAULT_WORKING_DAYS)
    if not isinstance(value, (list, tuple)):
        raise serializers.ValidationError("Use a list of day numbers, 0 = Monday … 6 = Sunday.")
    days = set()
    for d in value:
        try:
            d = int(d)
        except (TypeError, ValueError):
            raise serializers.ValidationError(f"{d!r} is not a day number.")
        if not 0 <= d <= 6:
            raise serializers.ValidationError("Day numbers run from 0 (Monday) to 6 (Sunday).")
        days.add(d)
    return sorted(days) or list(DEFAULT_WORKING_DAYS)


def check_role_in_plan(role, request):
    """
    Refuse a role the tenant's plan doesn't include.

    The Recruiter role only means something with the Recruitment module: a
    recruiter on a tenant without it could sign in to nothing at all (login
    refuses them — see web_access.refusal_for). So it can't be handed out.
    """
    if role != AgentRole.RECRUITER:
        return
    from apps.authentication.web_access import feature_checker, recruitment_in_plan

    if not recruitment_in_plan(feature_checker(request)):
        raise serializers.ValidationError(
            "The Recruiter role needs the Recruitment module on your plan."
        )


def check_admin_removal(actor, target, *, deactivating=False, new_role=None):
    """
    Refuse a change that would lock the tenant out of its own admin screens.

    Nothing stopped an admin deactivating their own account, or the tenant's
    only admin being deactivated or demoted — leaving nobody who could manage
    agents, billing or integrations, and a support ticket to get back in.
    Raises ValidationError; returns nothing when the change is fine.
    """
    if deactivating and actor is not None and actor.pk == target.pk:
        raise serializers.ValidationError(
            {"is_active": "You can't deactivate your own account."}
        )

    losing_admin = deactivating or (new_role is not None and new_role != AgentRole.ADMIN)
    if not (losing_admin and target.is_active and target.role == AgentRole.ADMIN):
        return

    other_admins = Agent.objects.filter(
        role=AgentRole.ADMIN, is_active=True
    ).exclude(pk=target.pk)
    if not other_admins.exists():
        field = "is_active" if deactivating else "role"
        raise serializers.ValidationError(
            {field: "This is the only admin. Make someone else an admin first."}
        )


class AgentUpdateSerializer(serializers.ModelSerializer):
    """Update agent details (no password change here — separate endpoint)."""

    class Meta:
        model = Agent
        # email is editable: the edit form always showed it as an input, but it
        # was missing here, so a changed email was silently dropped.
        fields = [
            "name", "email", "phone", "employee_id", "role", "is_active",
            "timezone", "shift_start", "shift_end", "working_days",
        ]

    def validate_email(self, value):
        value = (value or "").strip().lower()
        clash = Agent.objects.filter(email__iexact=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("Another agent already signs in with this email.")
        return value

    def validate_working_days(self, value):
        return _clean_working_days(value)

    def validate_phone(self, value):
        if value:
            from apps.core.utils import normalize_indian_phone
            normalized = normalize_indian_phone(value)
            if not normalized:
                raise serializers.ValidationError("Invalid Indian mobile number.")
            return normalized
        return value

    def validate_is_active(self, value):
        # Deactivating (True -> False) is fine here. Reactivating (False ->
        # True) must go through AgentReactivateAPIView instead, since that's
        # the only path that re-checks the plan's max_agents limit — a plain
        # PATCH would let a tenant silently exceed what they're paying for.
        if value and self.instance and not self.instance.is_active:
            raise serializers.ValidationError(
                "Use the reactivate action to restore this agent's access."
            )
        return value

    def validate_role(self, value):
        """
        Nobody may grant a role at or above their own.

        The permission on this endpoint checks the actor against the agent's
        CURRENT role only, and `role` accepted anything — so a manager could
        PATCH an agent to "admin", and IsTenantAdmin grants on role alone. A
        manager could mint tenant admins. Only an admin may hand out admin or
        manager; a manager may assign roles below manager.
        """
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if value == getattr(self.instance, "role", None):
            return value
        # No request means no actor to check the change against — refuse
        # rather than wave it through. (This is how /auth/me/ used to let an
        # agent promote themselves.)
        if actor is None:
            raise serializers.ValidationError("Role can't be changed here.")
        check_role_in_plan(value, request)

        if actor.role != AgentRole.ADMIN:
            actor_level = AgentRole.HIERARCHY.get(actor.role, 0)
            if AgentRole.HIERARCHY.get(value, 0) >= actor_level:
                raise serializers.ValidationError(
                    "You can only assign roles below your own."
                )
        return value

    def validate(self, data):
        if self.instance is not None:
            request = self.context.get("request")
            check_admin_removal(
                getattr(request, "user", None),
                self.instance,
                deactivating=data.get("is_active") is False and self.instance.is_active,
                new_role=data.get("role"),
            )
        return data


class AgentSelfUpdateSerializer(serializers.ModelSerializer):
    """
    What a person may change on their OWN profile (PATCH /auth/me/).

    Deliberately not AgentUpdateSerializer: role, is_active, employee_id and
    shift settings are the admin's to decide, not the agent's.
    """

    class Meta:
        model = Agent
        fields = ["name", "phone", "timezone", "language_preference"]

    def validate_phone(self, value):
        if value:
            from apps.core.utils import normalize_indian_phone
            normalized = normalize_indian_phone(value)
            if not normalized:
                raise serializers.ValidationError("Invalid Indian mobile number.")
            return normalized
        return value


class PasswordChangeSerializer(serializers.Serializer):
    """Change agent's own password."""

    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data


class AdminSetPasswordSerializer(serializers.Serializer):
    """
    Admin sets/resets another agent's password — no old password required.
    Used by POST /api/v1/auth/agents/{id}/set-password/ (tenant admin only).
    """

    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)
    require_change_on_login = serializers.BooleanField(
        default=False,
        help_text="Force the agent to change this password on their next login.",
    )

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data


class TeamMemberSerializer(serializers.ModelSerializer):
    """One agent's place in a team."""

    agent_id = serializers.IntegerField(source="agent.id", read_only=True)
    name = serializers.CharField(source="agent.name", read_only=True)
    email = serializers.EmailField(source="agent.email", read_only=True)
    role = serializers.CharField(source="agent.role", read_only=True)
    is_active = serializers.BooleanField(source="agent.is_active", read_only=True)

    class Meta:
        model = AgentTeam
        fields = ["agent_id", "name", "email", "role", "is_active", "is_team_lead", "joined_at"]
        read_only_fields = fields


class TeamSerializer(serializers.ModelSerializer):
    """
    A team, with who is in it.

    Membership is not decoration: a manager only sees agents who share a team
    with them, a senior agent sees their teammates' leads, and a team lead
    sees their team's leads. The members are therefore part of the team, not
    a separate thing to go and look up.
    """

    member_count = serializers.SerializerMethodField()
    members = TeamMemberSerializer(source="memberships", many=True, read_only=True)

    class Meta:
        model = Team
        fields = [
            "id", "name", "description", "is_active",
            "member_count", "members", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_member_count(self, obj) -> int:
        # The annotation when the list view provides one, else counted here so
        # the detail endpoint does not answer with a missing field.
        annotated = getattr(obj, "member_count_annotated", None)
        if annotated is not None:
            return annotated
        return obj.memberships.filter(agent__is_active=True).count()

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Give the team a name.")
        clash = Team.objects.filter(name__iexact=name)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(f'"{name}" already exists.')
        return name


class TeamMemberWriteSerializer(serializers.Serializer):
    """Adding an agent to a team."""

    agent_id = serializers.IntegerField()
    is_team_lead = serializers.BooleanField(required=False, default=False)

    def validate_agent_id(self, value):
        if not Agent.objects.filter(pk=value).exists():
            raise serializers.ValidationError("No such agent.")
        return value
