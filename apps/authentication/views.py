"""
TeleCRM Backend — apps/authentication/views.py

Two view sets in one file:

A) DRF API Views (for Flutter mobile app)
   - AgentLoginAPIView         POST /api/v1/auth/login/
   - AgentRefreshTokenAPIView  POST /api/v1/auth/refresh/
   - AgentLogoutAPIView        POST /api/v1/auth/logout/
   - AgentProfileAPIView       GET/PATCH /api/v1/auth/me/
   - AgentPasswordChangeAPIView POST /api/v1/auth/change-password/
   - AgentListAPIView          GET /api/v1/auth/agents/
   - AgentDetailAPIView        GET/PATCH/DELETE /api/v1/auth/agents/{id}/
   - TeamListAPIView           GET/POST /api/v1/auth/teams/

B) MVT Views (for web browser tenant admin dashboard)
   - TenantAdminLoginView      GET/POST /crm/login/
   - TenantAdminLogoutView     POST /crm/logout/
   - TenantAdminDashboardView  GET /crm/
   - AgentListView             GET /crm/agents/
   - AgentCreateView           GET/POST /crm/agents/create/
   - AgentUpdateView           GET/POST /crm/agents/{id}/edit/
   - AgentDeleteView           POST /crm/agents/{id}/delete/
   - ProfileView               GET/POST /crm/profile/
"""
import logging

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework import generics, status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.models import Agent, AgentLoginSession, Team
from apps.authentication.permissions import (
    CanManageAgent,
    HasFeatureAccess,
    IsActiveAgent,
    IsAuthenticatedAgent,
    IsManagerOrAdmin,
    IsTenantAdmin,
    role_required,
    tenant_admin_required,
)
from apps.authentication.serializers import (
    AdminSetPasswordSerializer,
    AgentCreateSerializer,
    AgentLoginSerializer,
    AgentProfileSerializer,
    AgentSerializer,
    AgentUpdateSerializer,
    PasswordChangeSerializer,
    TeamSerializer,
)
from apps.authentication.tokens import (
    blacklist_refresh_token,
    generate_tokens_for_agent,
)
from apps.core.constants import AgentRole, FeatureKey
from apps.core.exceptions import InvalidCredentialsException, PlanLimitExceededException
from apps.core.pagination import StandardResultsSetPagination
from apps.superadmin.models import AuditLog
from apps.core.constants import AuditAction

logger = logging.getLogger(__name__)


# ============================================================
# A) DRF API VIEWS — for Flutter mobile app
# ============================================================

class TenantInfoAPIView(APIView):
    """
    GET /api/v1/auth/tenant-info/
    Returns basic public info about the current tenant.
    Used by the Flutter app to verify a workspace name resolves correctly.
    No authentication required.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        from django.db import connection
        from apps.tenants.models import Tenant

        schema = connection.schema_name
        if not schema or schema == 'public':
            return Response(
                {"error": "workspace_not_found", "message": "Workspace not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            tenant = Tenant.objects.get(schema_name=schema)
            return Response({
                "schema": tenant.schema_name,
                "company_name": tenant.company_name,
                "is_active": tenant.is_active,
            })
        except Tenant.DoesNotExist:
            return Response(
                {"error": "workspace_not_found", "message": "Workspace not found."},
                status=status.HTTP_404_NOT_FOUND,
            )


class AgentLoginAPIView(APIView):
    """
    POST /api/v1/auth/login/
    Authenticate agent and return JWT tokens.

    Request:  { "email": "...", "password": "..." }
    Response: { "access": "...", "refresh": "...", "agent": {...} }
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        serializer = AgentLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        # Look up agent (case-insensitive)
        agent = Agent.objects.filter(email__iexact=email).first()
        if not agent:
            # Don't reveal which field is wrong (security)
            AuditLog.log(
                action=AuditAction.LOGIN_FAILED,
                actor_type="agent",
                actor_email=email,
                description=f"Login failed — agent not found",
                request=request,
            )
            raise InvalidCredentialsException()

        if not agent.is_active:
            raise InvalidCredentialsException()

        if not agent.check_password(password):
            AuditLog.log(
                action=AuditAction.LOGIN_FAILED,
                actor_type="agent",
                actor_email=email,
                entity_repr=agent.name,
                request=request,
            )
            raise InvalidCredentialsException()

        # Generate tokens
        tokens = generate_tokens_for_agent(agent)

        # Track login
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or \
             request.META.get("REMOTE_ADDR", "")
        agent.last_login = timezone.now()
        agent.last_login_ip = ip or None
        agent.total_login_count += 1
        agent.save(update_fields=["last_login", "last_login_ip", "total_login_count"])

        # Create session record
        AgentLoginSession.objects.create(
            agent=agent,
            ip_address=ip or None,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
            device_type="mobile" if any(
                m in request.META.get("HTTP_USER_AGENT", "").lower()
                for m in ("flutter", "dart", "okhttp")
            ) else "api",
            jwt_jti=tokens.get("jti", ""),
        )

        AuditLog.log(
            action=AuditAction.LOGIN,
            actor_type="agent",
            actor_id=agent.pk,
            actor_email=agent.email,
            entity_type="Agent",
            entity_repr=agent.name,
            request=request,
        )

        return Response(
            {
                **tokens,
                "agent": AgentProfileSerializer(agent, context={"request": request}).data,
                "must_change_password": agent.must_change_password,
            }
        )


class AgentRefreshTokenAPIView(APIView):
    """
    POST /api/v1/auth/refresh/
    Refresh expired access token using a valid refresh token.

    Request:  { "refresh": "<refresh_token>" }
    Response: { "access": "<new_access_token>", "refresh": "<rotated_refresh>" }
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework_simplejwt.exceptions import TokenError

        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": "refresh_required", "message": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            refresh = RefreshToken(refresh_token)

            # Verify it's an agent token
            if not refresh.get("agent_id"):
                raise TokenError("Not an agent token")

            # Rotate refresh token (generates new refresh, old one is blacklisted)
            new_tokens = {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }
            return Response(new_tokens)

        except TokenError as exc:
            return Response(
                {
                    "error": "token_invalid",
                    "message": "Invalid or expired refresh token. Please log in again.",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )


class AgentLogoutAPIView(APIView):
    """
    POST /api/v1/auth/logout/
    Invalidate the refresh token (blacklist it).

    Request:  { "refresh": "<refresh_token>" }
    Response: { "message": "Logged out successfully" }
    """

    permission_classes = [IsAuthenticatedAgent]

    def post(self, request):
        refresh_token = request.data.get("refresh")

        if refresh_token:
            blacklist_refresh_token(refresh_token)

        # Mark agent offline immediately so the monitoring dashboard updates.
        try:
            from apps.authentication.presence import set_agent_status
            from apps.core.constants import AgentWorkStatus
            set_agent_status(request.user, AgentWorkStatus.OFFLINE)
        except Exception:
            pass

        # Mark session as inactive
        agent = request.user
        AgentLoginSession.objects.filter(
            agent=agent, is_active=True
        ).update(
            is_active=False, logout_time=timezone.now()
        )

        AuditLog.log(
            action=AuditAction.LOGOUT,
            actor_type="agent",
            actor_id=agent.pk,
            actor_email=agent.email,
            entity_type="Agent",
            entity_repr=agent.name,
            request=request,
        )

        return Response({"message": "Logged out successfully."})


class AgentProfileAPIView(APIView):
    """
    GET  /api/v1/auth/me/     → Return current agent's profile
    PATCH /api/v1/auth/me/    → Update current agent's profile
    """

    permission_classes = [IsAuthenticatedAgent]
    parser_classes = [JSONParser, MultiPartParser]

    def get(self, request):
        serializer = AgentProfileSerializer(
            request.user, context={"request": request}
        )
        return Response(serializer.data)

    def patch(self, request):
        serializer = AgentUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            AgentProfileSerializer(
                request.user, context={"request": request}
            ).data
        )


class AgentPasswordChangeAPIView(APIView):
    """POST /api/v1/auth/change-password/ — Change own password."""

    permission_classes = [IsAuthenticatedAgent]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        agent = request.user
        if not agent.check_password(serializer.validated_data["old_password"]):
            return Response(
                {"error": "wrong_password", "message": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        agent.set_password(serializer.validated_data["new_password"])
        agent.must_change_password = False
        agent.save(update_fields=["password", "must_change_password"])

        AuditLog.log(
            action=AuditAction.PASSWORD_CHANGE,
            actor_type="agent",
            actor_id=agent.pk,
            actor_email=agent.email,
            request=request,
        )

        return Response({"message": "Password changed successfully."})


class AgentListAPIView(generics.ListCreateAPIView):
    """
    GET  /api/v1/auth/agents/  → List all agents (managers/admins only)
    POST /api/v1/auth/agents/  → Create new agent (admins only)
    """

    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsManagerOrAdmin()]
        return [IsTenantAdmin()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AgentCreateSerializer
        return AgentSerializer

    def get_queryset(self):
        agent = self.request.user
        qs = Agent.objects.filter(is_active=True).order_by("name")

        # Managers see agents in their teams; admins see all
        if agent.role == AgentRole.MANAGER:
            team_ids = agent.team_memberships.values_list("team_id", flat=True)
            qs = qs.filter(team_memberships__team_id__in=team_ids).distinct()

        return qs

    def perform_create(self, serializer):
        # Check plan limit
        from apps.plans.models import Subscription
        from django.db import connection

        # Check max_agents limit
        current_count = Agent.objects.filter(is_active=True).count()

        try:
            from apps.plans.models import Subscription
            from apps.core.constants import SubscriptionStatus
            sub = Subscription.objects.filter(
                status__in=SubscriptionStatus.ACTIVE_STATUSES
            ).select_related("plan").first()
            if sub and current_count >= sub.plan.max_agents:
                raise PlanLimitExceededException(
                    limit_type="agents",
                    current=current_count,
                    max_allowed=sub.plan.max_agents,
                )
        except PlanLimitExceededException:
            raise
        except Exception:
            pass  # If we can't check, allow creation

        agent = serializer.save()
        AuditLog.log(
            action=AuditAction.CREATE,
            actor_type="tenant_admin",
            actor_id=self.request.user.pk,
            actor_email=self.request.user.email,
            entity_type="Agent",
            entity_id=agent.pk,
            entity_repr=agent.name,
            request=self.request,
        )


class AgentDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/v1/auth/agents/{id}/  → Agent detail
    PATCH  /api/v1/auth/agents/{id}/  → Update agent
    DELETE /api/v1/auth/agents/{id}/  → Deactivate agent
    """

    def get_permissions(self):
        if self.request.method == "DELETE":
            return [IsTenantAdmin()]
        return [IsManagerOrAdmin(), CanManageAgent()]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return AgentUpdateSerializer
        return AgentSerializer

    def get_queryset(self):
        return Agent.objects.filter(is_active=True)

    def perform_destroy(self, instance):
        # Soft-delete: deactivate instead of hard delete
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        AuditLog.log(
            action=AuditAction.DELETE,
            actor_type="tenant_admin",
            actor_id=self.request.user.pk,
            actor_email=self.request.user.email,
            entity_type="Agent",
            entity_id=instance.pk,
            entity_repr=instance.name,
            request=self.request,
        )


class AgentSetPasswordAPIView(APIView):
    """
    POST /api/v1/auth/agents/{id}/set-password/
    Tenant admin sets/resets another agent's password (no old password needed).
    """

    permission_classes = [IsTenantAdmin]

    def post(self, request, pk):
        agent = get_object_or_404(Agent, pk=pk, is_active=True)

        # Admins cannot reset their own password here — they must use
        # the regular change-password flow (which verifies the old password).
        if agent.pk == request.user.pk:
            return Response(
                {
                    "error": "self_reset_not_allowed",
                    "message": "Use the change-password option to update your own password.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AdminSetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        agent.set_password(serializer.validated_data["new_password"])
        agent.must_change_password = serializer.validated_data.get(
            "require_change_on_login", False
        )
        agent.save(update_fields=["password", "must_change_password"])

        AuditLog.log(
            action=AuditAction.PASSWORD_RESET,
            actor_type="tenant_admin",
            actor_id=request.user.pk,
            actor_email=request.user.email,
            entity_type="Agent",
            entity_id=agent.pk,
            entity_repr=agent.name,
            request=request,
        )

        return Response(
            {"message": f"Password updated for {agent.name}."},
            status=status.HTTP_200_OK,
        )


class TeamListAPIView(generics.ListCreateAPIView):
    """GET/POST /api/v1/auth/teams/"""

    permission_classes = [IsManagerOrAdmin]
    serializer_class = TeamSerializer

    def get_queryset(self):
        return Team.objects.filter(is_active=True).annotate(
            member_count=models.Count("memberships", filter=models.Q(
                memberships__agent__is_active=True
            ))
        )


class TenantFeaturesAPIView(APIView):
    """
    GET /api/v1/auth/features/
    The tenant's EFFECTIVE feature map (plan + add-on entitlements), plan info
    and capacity limits.

    Clients use this to hide/disable gated UI. It is a UX convenience only —
    the backend remains the source of truth and re-checks every gated endpoint.
    """

    permission_classes = [IsAuthenticatedAgent]

    def get(self, request):
        from apps.core.constants import FeatureKey, ModuleKey

        features = getattr(request, "tenant_features", {}) or {}
        # Present every known key so clients don't guess on missing entries.
        full_map = {key: bool(features.get(key, False)) for key in FeatureKey.ALL}

        # `request.tenant_plan` is a SimpleLazyObject — never `is None`, so
        # test truthiness (which forces evaluation).
        plan = getattr(request, "tenant_plan", None)
        plan_data = None
        if plan:
            plan_data = {
                "slug": plan.slug,
                "name": plan.name,
                "limits": {
                    "max_agents": plan.max_agents,
                    "max_leads": plan.max_leads,
                    "max_leads_per_day": plan.max_leads_per_day,
                    "max_whatsapp_bulk_per_day": plan.max_whatsapp_bulk_per_day,
                    "max_email_bulk_per_day": plan.max_email_bulk_per_day,
                    "max_sms_per_day": plan.max_sms_per_day,
                    "storage_gb": plan.storage_gb,
                    "custom_fields_limit": plan.custom_fields_limit,
                    "lead_sources_limit": plan.lead_sources_limit,
                },
            }

        # A module counts as active only when ALL of its features are enabled.
        modules = {
            module: all(full_map.get(k, False) for k in keys)
            for module, keys in ModuleKey.FEATURES.items()
        }

        return Response({"features": full_map, "modules": modules, "plan": plan_data})


# ============================================================
# Live Agent Monitoring API
# ============================================================

class AgentStatusUpdateAPIView(APIView):
    """
    POST /api/v1/auth/status/
    Agent reports a live work-status transition (available / on_call /
    wrap_up / break / offline). Returns the updated live payload.
    """

    permission_classes = [IsAuthenticatedAgent]

    def post(self, request):
        from apps.authentication.presence import agent_live_payload, set_agent_status
        from apps.core.constants import AgentWorkStatus

        status_val = (request.data.get("status") or "").strip()
        if status_val not in AgentWorkStatus.REPORTABLE:
            return Response(
                {"error": "invalid_status",
                 "message": f"status must be one of {AgentWorkStatus.REPORTABLE}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        st = set_agent_status(
            request.user,
            status_val,
            break_reason=(request.data.get("break_reason") or "")[:100],
            call_id=request.data.get("call_id"),
            lead_id=request.data.get("lead_id"),
        )
        return Response(agent_live_payload(st))


class AgentHeartbeatAPIView(APIView):
    """
    POST /api/v1/auth/status/heartbeat/
    Keepalive from the agent app — refreshes last_seen so the active session
    isn't swept to offline. Cheap; no broadcast.
    """

    permission_classes = [IsAuthenticatedAgent]

    def post(self, request):
        from apps.authentication.presence import touch_heartbeat
        touch_heartbeat(request.user)
        return Response({"ok": True})


class LiveAgentsAPIView(APIView):
    """
    GET /api/v1/auth/live-agents/
    Manager/admin snapshot of every agent's current status + today's time
    totals. Used for the initial load of the Live Agents dashboard; ongoing
    updates arrive over the /ws/agent-monitor/ WebSocket.

    Plan-gated on AGENT_MONITORING. Note the agent-side status/heartbeat
    endpoints are deliberately NOT gated — agents must always be able to
    report state, otherwise the dialer breaks on un-entitled plans.
    """

    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.AGENT_MONITORING

    def get(self, request):
        from apps.authentication.models import AgentStatus
        from apps.authentication.presence import agent_live_payload, sweep_stale
        from apps.core.constants import AgentWorkStatus

        # Flip any stale sessions to offline so the snapshot is accurate.
        sweep_stale()

        now = timezone.now()
        statuses = {
            s.agent_id: s
            for s in AgentStatus.objects.select_related("agent").filter(agent__is_active=True)
        }
        agents = Agent.objects.filter(is_active=True).order_by("name")

        out = []
        for agent in agents:
            st = statuses.get(agent.id)
            if st is None:
                out.append({
                    "agent_id": agent.id, "name": agent.name, "email": agent.email,
                    "role": agent.role, "status": AgentWorkStatus.OFFLINE,
                    "status_display": "Offline", "since": None, "break_reason": "",
                    "last_seen": None, "is_online": False, "current_lead_id": None,
                    "session_started_at": None,
                    "totals": {"available": 0, "on_call": 0, "wrap_up": 0, "break": 0, "online": 0},
                })
            else:
                out.append(agent_live_payload(st, now))

        return Response({"agents": out, "server_time": now.isoformat()})


# ============================================================
# B) MVT VIEWS — for web browser tenant admin dashboard
# ============================================================

class TenantAdminLoginView(View):
    """
    GET  /crm/login/  → Render login form
    POST /crm/login/  → Process login, set session, redirect to dashboard
    """

    template_name = "tenant_admin/auth/login.html"

    def get(self, request):
        # Redirect if already logged in
        if request.session.get("agent_id"):
            return redirect("tenant_admin:dashboard")
        next_url = request.GET.get("next", "/crm/")
        return render(request, self.template_name, {"next": next_url})

    def post(self, request):
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        next_url = request.POST.get("next", "/crm/")

        error = None

        agent = Agent.objects.filter(email__iexact=email, is_active=True).first()
        if agent:
            if agent.check_password(password):
                # Set session
                request.session["agent_id"] = agent.pk
                request.session["agent_role"] = agent.role
                request.session["is_tenant_admin"] = agent.is_tenant_admin
                request.session["agent_name"] = agent.name

                # Update login tracking
                agent.last_login = timezone.now()
                ip = request.META.get("REMOTE_ADDR", "")
                agent.last_login_ip = ip or None
                agent.total_login_count += 1
                agent.save(update_fields=["last_login", "last_login_ip", "total_login_count"])

                AuditLog.log(
                    action=AuditAction.LOGIN,
                    actor_type="tenant_admin",
                    actor_id=agent.pk,
                    actor_email=agent.email,
                    entity_repr=agent.name,
                    request=request,
                )

                # Redirect to password change if required
                if agent.must_change_password:
                    return redirect("tenant_admin:change_password")

                return redirect(next_url if next_url.startswith("/crm/") else "/crm/")
            else:
                error = "Invalid email or password."
        else:
            error = "Invalid email or password."

        return render(
            request, self.template_name, {"error": error, "next": next_url}
        )


class TenantAdminLogoutView(View):
    """POST /crm/logout/ — Clear session and redirect to login."""

    def post(self, request):
        agent_id = request.session.get("agent_id")
        if agent_id:
            AuditLog.log(
                action=AuditAction.LOGOUT,
                actor_type="tenant_admin",
                actor_id=agent_id,
                request=request,
            )
        request.session.flush()
        return redirect("tenant_admin:login")


class TenantAdminDashboardView(View):
    """GET /crm/ — Main dashboard shell."""

    template_name = "tenant_admin/dashboard/index.html"

    @method_decorator(tenant_admin_required)
    def get(self, request):
        agent = request.agent
        ctx = {
            "agent": agent,
            "page_title": "Dashboard",
        }
        return render(request, self.template_name, ctx)


class AgentListView(View):
    """GET /crm/agents/ — List all agents."""

    template_name = "tenant_admin/agents/list.html"

    @method_decorator(tenant_admin_required)
    def get(self, request):
        if request.agent.role not in [AgentRole.ADMIN, AgentRole.MANAGER]:
            return redirect("tenant_admin:dashboard")

        agents = Agent.objects.filter(is_active=True).order_by("name")
        return render(
            request, self.template_name,
            {"agents": agents, "page_title": "Agents"}
        )


class AgentCreateView(View):
    """GET/POST /crm/agents/create/ — Create new agent."""

    template_name = "tenant_admin/agents/form.html"

    @method_decorator(tenant_admin_required)
    def get(self, request):
        if request.agent.role != AgentRole.ADMIN:
            messages.error(request, "Only admins can create agents.")
            return redirect("tenant_admin:agent_list")
        from apps.authentication.forms import AgentCreateForm
        form = AgentCreateForm()
        return render(
            request, self.template_name,
            {"form": form, "page_title": "Add Agent", "action": "create"}
        )

    @method_decorator(tenant_admin_required)
    def post(self, request):
        if request.agent.role != AgentRole.ADMIN:
            return redirect("tenant_admin:agent_list")
        from apps.authentication.forms import AgentCreateForm
        form = AgentCreateForm(request.POST, request.FILES)
        if form.is_valid():
            agent = form.save(commit=False)
            agent.set_password(form.cleaned_data["password"])
            agent.must_change_password = True
            agent.save()
            messages.success(request, f"Agent '{agent.name}' created successfully.")
            return redirect("tenant_admin:agent_list")
        return render(
            request, self.template_name,
            {"form": form, "page_title": "Add Agent", "action": "create"}
        )


class AgentUpdateView(View):
    """GET/POST /crm/agents/{id}/edit/ — Edit agent details."""

    template_name = "tenant_admin/agents/form.html"

    @method_decorator(tenant_admin_required)
    def get(self, request, pk):
        agent_to_edit = get_object_or_404(Agent, pk=pk, is_active=True)
        from apps.authentication.forms import AgentUpdateForm
        form = AgentUpdateForm(instance=agent_to_edit)
        return render(
            request, self.template_name,
            {"form": form, "edit_agent": agent_to_edit, "page_title": "Edit Agent", "action": "edit"}
        )

    @method_decorator(tenant_admin_required)
    def post(self, request, pk):
        agent_to_edit = get_object_or_404(Agent, pk=pk, is_active=True)
        from apps.authentication.forms import AgentUpdateForm
        form = AgentUpdateForm(request.POST, request.FILES, instance=agent_to_edit)
        if form.is_valid():
            form.save()
            messages.success(request, f"Agent '{agent_to_edit.name}' updated.")
            return redirect("tenant_admin:agent_list")
        return render(
            request, self.template_name,
            {"form": form, "edit_agent": agent_to_edit, "page_title": "Edit Agent", "action": "edit"}
        )


class AgentDeleteView(View):
    """POST /crm/agents/{id}/delete/ — Deactivate agent."""

    @method_decorator(tenant_admin_required)
    def post(self, request, pk):
        if request.agent.role != AgentRole.ADMIN:
            return JsonResponse({"error": "Admin only"}, status=403)
        agent_to_delete = get_object_or_404(Agent, pk=pk)
        if agent_to_delete.pk == request.agent.pk:
            messages.error(request, "You cannot deactivate your own account.")
            return redirect("tenant_admin:agent_list")
        agent_to_delete.is_active = False
        agent_to_delete.save(update_fields=["is_active"])
        messages.success(request, f"Agent '{agent_to_delete.name}' deactivated.")
        return redirect("tenant_admin:agent_list")


class ProfileView(View):
    """GET/POST /crm/profile/ — Current agent's profile."""

    template_name = "tenant_admin/profile/index.html"

    @method_decorator(tenant_admin_required)
    def get(self, request):
        from apps.authentication.forms import AgentProfileForm
        form = AgentProfileForm(instance=request.agent)
        return render(
            request, self.template_name,
            {"form": form, "page_title": "My Profile"}
        )

    @method_decorator(tenant_admin_required)
    def post(self, request):
        from apps.authentication.forms import AgentProfileForm
        form = AgentProfileForm(request.POST, request.FILES, instance=request.agent)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("tenant_admin:profile")
        return render(
            request, self.template_name,
            {"form": form, "page_title": "My Profile"}
        )


# Need this for the annotation in AgentListAPIView
from django.db import models
