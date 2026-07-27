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
            "is_online", "last_active_at", "created_at",
        ]
        read_only_fields = ["id", "email", "role", "is_tenant_admin", "created_at"]

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

    def validate_role(self, value):
        # Only admins can create admins (enforced in view permissions)
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


class AgentUpdateSerializer(serializers.ModelSerializer):
    """Update agent details (no password change here — separate endpoint)."""

    class Meta:
        model = Agent
        fields = [
            "name", "phone", "employee_id", "role", "is_active",
            "timezone", "shift_start", "shift_end", "working_days",
        ]

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


class TeamSerializer(serializers.ModelSerializer):
    """Team serializer with member count."""

    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Team
        fields = ["id", "name", "description", "is_active", "member_count", "created_at"]
        read_only_fields = ["id", "created_at"]
