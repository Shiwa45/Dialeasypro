"""
TeleCRM Backend — apps/leads/views.py

DRF API views for the Flutter mobile app.

LeadListCreateView           GET/POST  /api/v1/leads/
LeadDetailView               GET/PATCH/DELETE /api/v1/leads/{id}/
LeadStatusUpdateView         PATCH     /api/v1/leads/{id}/status/
LeadBulkAssignView           POST      /api/v1/leads/bulk-assign/
FollowUpListCreateView       GET/POST  /api/v1/leads/{id}/followups/
FollowUpCompleteView         POST      /api/v1/followups/{id}/complete/
LeadNoteListCreateView       GET/POST  /api/v1/leads/{id}/notes/
LeadActivityListView         GET       /api/v1/leads/{id}/activities/
LeadImportView               POST      /api/v1/leads/import/
LeadImportJobDetailView      GET       /api/v1/leads/import/{id}/
CustomFieldListView          GET/POST  /api/v1/leads/custom-fields/
LeadDashboardStatsView       GET       /api/v1/leads/stats/
LeadPipelineView             GET       /api/v1/leads/pipeline/

MVT views for tenant admin web UI are in leads/mvt_views.py
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.constants import AgentRole, LeadStatus
from apps.core.exceptions import PlanLimitExceededException
from apps.core.pagination import LargeResultsSetPagination, StandardResultsSetPagination
from apps.leads.models import (
    CallQueue,
    CallQueueMembership,
    CustomField,
    FollowUp,
    Lead,
    LeadActivity,
    LeadImportJob,
    LeadNote,
)
from apps.leads.serializers import (
    CallQueueSerializer,
    CallQueueSummarySerializer,
    CustomFieldSerializer,
    FollowUpCreateSerializer,
    FollowUpSerializer,
    LeadBatchSerializer,
    LeadBulkAssignSerializer,
    LeadCreateSerializer,
    LeadDetailSerializer,
    LeadImportJobSerializer,
    LeadListSerializer,
    LeadNoteSerializer,
    LeadUpdateSerializer,
)
from apps.authentication.permissions import (
    HasFeatureAccess,
    IsActiveAgent,
    IsAuthenticatedAgent,
    IsManagerOrAdmin,
    IsTenantAdmin,
    feature_required,
)
from apps.core.constants import FeatureKey
from apps.superadmin.models import AuditLog
from apps.core.constants import AuditAction

logger = logging.getLogger(__name__)


# ============================================================
# Lead visibility scoping (single source of truth)
# ============================================================

def leads_visible_to(agent):
    """
    Return the base queryset of leads an agent is allowed to see.

    STRICT rule:
      - Admins & Managers      → all leads in the tenant
      - Senior Agents          → own assigned leads + their teams' leads
      - Everyone else (Agent,  → ONLY leads assigned to themselves
        Read-only, Trainee,
        unknown roles)

    Using a secure default (the final `return`) ensures any role that is not
    explicitly granted broader access can only ever see its own assigned
    leads — an agent can never see leads the admin hasn't assigned to them.
    """
    qs = Lead.objects.filter(is_deleted=False)
    role = getattr(agent, "role", None)

    if role in (AgentRole.ADMIN, AgentRole.MANAGER):
        return qs
    if role == AgentRole.SENIOR_AGENT:
        return qs.filter(
            Q(assigned_to=agent)
            | Q(assigned_to__team_memberships__team__memberships__agent=agent)
        ).distinct()
    # Secure default: own assigned leads only.
    return qs.filter(assigned_to=agent)


def assert_lead_visible(agent, lead_id):
    """
    Raise Http404 if the given lead is not visible to the agent.
    Used by child-resource views (notes, follow-ups, activities) so an agent
    cannot read or write sub-objects of a lead that isn't assigned to them.
    """
    from django.http import Http404
    if not leads_visible_to(agent).filter(pk=lead_id).exists():
        raise Http404("Lead not found.")


# ============================================================
# Lead CRUD
# ============================================================

class LeadListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/leads/     → Paginated lead list with filters
    POST /api/v1/leads/     → Create new lead

    Filters: status, priority, source, assigned_to, city,
             search (name/phone/email), overdue, date_range
    """

    permission_classes = [IsAuthenticatedAgent]
    pagination_class = StandardResultsSetPagination

    def create(self, request, *args, **kwargs):
        """
        Create, then answer with the full lead.

        LeadCreateSerializer lists only the writable fields, so the 201 came
        back without an id — a copy of what the caller had just sent. The
        mobile app parses the response into a Lead, whose id is a non-null
        int, so every successful creation threw on the client and surfaced as
        "An unexpected error occurred". The lead existed; the agent was told
        it had failed, and retried, which is how duplicates get made.
        """
        write = self.get_serializer(data=request.data)
        write.is_valid(raise_exception=True)
        self.perform_create(write)
        headers = self.get_success_headers(write.data)
        return Response(
            LeadDetailSerializer(write.instance, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return LeadCreateSerializer
        return LeadListSerializer

    def get_queryset(self):
        # Role-based visibility (agents see only their assigned leads).
        qs = leads_visible_to(self.request.user).select_related("assigned_to", "batch")

        # ---- Query param filters ----
        params = self.request.query_params

        if status_filter := params.get("status"):
            qs = qs.filter(status=status_filter)

        if priority := params.get("priority"):
            qs = qs.filter(priority=priority)

        if source := params.get("source"):
            qs = qs.filter(source=source)

        if assigned_to := params.get("assigned_to"):
            qs = qs.filter(assigned_to_id=assigned_to)
        if batch := params.get("batch"):
            qs = qs.filter(batch_id=batch)

        if city := params.get("city"):
            qs = qs.filter(city__icontains=city)

        if campaign := params.get("campaign"):
            qs = qs.filter(campaign_name__icontains=campaign)

        if search := params.get("search"):
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(phone__icontains=search) |
                Q(email__icontains=search)
            )

        if params.get("overdue") == "true":
            qs = qs.filter(
                next_followup_at__lt=timezone.now(),
                next_followup_at__isnull=False,
            )

        if date_from := params.get("date_from"):
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to := params.get("date_to"):
            qs = qs.filter(created_at__date__lte=date_to)

        # Ordering
        order_by = params.get("order_by", "-created_at")
        allowed_orderings = [
            "created_at", "-created_at", "name", "-name",
            "next_followup_at", "-score", "score",
        ]
        if order_by in allowed_orderings:
            qs = qs.order_by(order_by)

        return qs

    def perform_create(self, serializer):
        agent = self.request.user

        # Set assigned_to to current agent if not specified
        if not serializer.validated_data.get("assigned_to"):
            serializer.validated_data["assigned_to"] = agent

        lead = serializer.save()

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_type="agent",
            actor_id=agent.pk,
            actor_email=agent.email,
            entity_type="Lead",
            entity_id=lead.pk,
            entity_repr=lead.name,
            request=self.request,
        )


class LeadDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/v1/leads/{id}/  → Lead detail with followups, notes, activities
    PATCH  /api/v1/leads/{id}/  → Update lead fields
    DELETE /api/v1/leads/{id}/  → Soft delete (sets is_deleted=True)
    """

    permission_classes = [IsAuthenticatedAgent]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return LeadUpdateSerializer
        return LeadDetailSerializer

    def get_queryset(self):
        # Scope to leads the agent may see, then prefetch detail relations.
        return leads_visible_to(self.request.user).prefetch_related(
            "followups", "notes", "activities", "custom_field_values__field"
        ).select_related("assigned_to")

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted"])
        AuditLog.log(
            action=AuditAction.DELETE,
            actor_type="agent",
            actor_id=self.request.user.pk,
            actor_email=self.request.user.email,
            entity_type="Lead",
            entity_id=instance.pk,
            entity_repr=instance.name,
            request=self.request,
        )

    def perform_update(self, serializer):
        old_status = serializer.instance.status
        lead = serializer.save()
        new_status = lead.status

        if old_status != new_status:
            LeadActivity.objects.create(
                lead=lead,
                activity_type="status_change",
                description=f"Status changed: {old_status} → {new_status}",
                performed_by=self.request.user,
                meta={"old_status": old_status, "new_status": new_status},
            )


class LeadStatusUpdateView(APIView):
    """
    PATCH /api/v1/leads/{id}/status/
    Dedicated endpoint for quick status updates from the kanban board.
    """

    permission_classes = [IsAuthenticatedAgent]

    def patch(self, request, pk):
        # Only allow status changes on leads visible to this agent.
        try:
            lead = leads_visible_to(request.user).get(pk=pk)
        except Lead.DoesNotExist:
            return Response({"error": "not_found", "message": "Lead not found."}, status=404)

        new_status = request.data.get("status")
        if new_status not in dict(LeadStatus.CHOICES):
            return Response(
                {"error": "invalid_status", "message": "Invalid lead status."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lead.update_status(new_status, agent=request.user)
        return Response({"id": lead.pk, "status": new_status})


class LeadBulkAssignView(APIView):
    """
    POST /api/v1/leads/bulk-assign/
    Assign multiple leads to one agent at once.
    """

    permission_classes = [IsManagerOrAdmin]

    def post(self, request):
        serializer = LeadBulkAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        lead_ids = serializer.validated_data["lead_ids"]
        agent = serializer.validated_data["assigned_to"]

        updated = Lead.objects.filter(
            pk__in=lead_ids, is_deleted=False
        ).update(assigned_to=agent, assigned_at=timezone.now())

        return Response(
            {"updated": updated, "assigned_to": agent.name},
            status=status.HTTP_200_OK,
        )


class LeadUnassignByAgentView(APIView):
    """
    POST /api/v1/leads/unassign-by-agent/   {"agent_id": <int>}

    Clears assigned_to (and assigned_at) on every lead currently assigned to
    one agent — e.g. an agent who's leaving, or whose book needs a clean
    reset before redistribution. The leads themselves are never touched
    beyond that FK: no delete, no status change, no note/history removal.

    Admin-only — this can affect an agent's entire book in one click, a wider
    blast radius than LeadBulkAssignView's hand-picked list, so it sits at the
    same permission level as LeadFlushView rather than IsManagerOrAdmin.
    """

    permission_classes = [IsTenantAdmin]

    def post(self, request):
        from apps.authentication.models import Agent

        agent_id = request.data.get("agent_id")
        agent = Agent.objects.filter(pk=agent_id).first()
        if agent is None:
            return Response(
                {"error": "not_found", "message": "Agent not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        qs = Lead.objects.filter(assigned_to=agent, is_deleted=False)
        count = qs.count()
        qs.update(assigned_to=None, assigned_at=None)

        AuditLog.log(
            action=AuditAction.BULK_ACTION,
            actor_type="tenant_admin",
            actor_id=request.user.pk,
            actor_email=request.user.email,
            entity_type="Lead",
            description=f"Unassigned {count} lead(s) from {agent.name} ({agent.email})",
            request=request,
        )
        logger.info(
            f"[LeadUnassign] {request.user.email} unassigned {count} lead(s) "
            f"from {agent.email}."
        )

        return Response(
            {"unassigned": count, "agent": agent.name},
            status=status.HTTP_200_OK,
        )


class LeadDistributeView(APIView):
    """
    POST /api/v1/leads/distribute/
    Distribute leads matching a filter across one or more agents in one action.
    Multiple agents → round-robin (even) split. Replaces one-by-one assignment.
    """

    permission_classes = [IsManagerOrAdmin]

    def post(self, request):
        from apps.leads.serializers import LeadDistributeSerializer

        serializer = LeadDistributeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        agents = d["agent_ids"]  # validated → list of Agent objects

        qs = Lead.objects.filter(is_deleted=False)
        if d.get("batch_ids"):
            qs = qs.filter(batch_id__in=d["batch_ids"])
        if d.get("only_unassigned"):
            qs = qs.filter(assigned_to__isnull=True)
        if d.get("statuses"):
            qs = qs.filter(status__in=[s.lower() for s in d["statuses"]])
        if d.get("priorities"):
            qs = qs.filter(priority__in=[p.lower() for p in d["priorities"]])
        if d.get("sources"):
            qs = qs.filter(source__in=[s.lower() for s in d["sources"]])
        if d.get("search"):
            term = d["search"]
            qs = qs.filter(
                Q(name__icontains=term) | Q(phone__icontains=term) | Q(email__icontains=term)
            )

        # created_at, not pk, so an equal split gives each agent a
        # time-coherent slice and a re-run produces the same plan.
        qs = qs.order_by("created_at", "id")
        if d.get("limit"):
            qs = qs[: d["limit"]]

        lead_ids = list(qs.values_list("id", flat=True))
        if not lead_ids:
            return Response(
                {"distributed": 0, "unassigned": 0, "per_agent": {},
                 "message": "No leads matched the filter."},
                status=status.HTTP_200_OK,
            )

        # The shared engine, so this path and the import task's auto-assign can
        # never drift apart — the round-robin used to live inline here, which
        # is exactly why the import path could not reuse it.
        from apps.leads.services import distribution as dist

        result = dist.distribute(
            lead_ids, agents,
            method=d.get("method") or dist.Method.ROUND_ROBIN,
            max_per_agent=d.get("max_per_agent"),
            actor=request.user,
        )

        AuditLog.log(
            action=AuditAction.BULK_ACTION,
            actor_type="tenant_admin",
            actor_id=request.user.pk,
            actor_email=request.user.email,
            entity_type="Lead",
            description=(
                f"Distributed {result['distributed']} leads across "
                f"{len(agents)} agent(s) using {result['method']}"
            ),
            request=request,
        )

        return Response(result, status=status.HTTP_200_OK)


class LeadFlushView(APIView):
    """
    POST /api/v1/leads/flush/
    DANGER: Permanently delete leads (hard delete). Tenant-admin only.

    Body:
      confirm   — must equal "FLUSH ALL" (server-side safety guard)
      only_unassigned (optional bool) — restrict to unassigned leads
      statuses  (optional list)       — restrict to these statuses

    Returns the number of leads removed.
    """

    permission_classes = [IsTenantAdmin]

    CONFIRM_PHRASE = "FLUSH ALL"

    def post(self, request):
        if (request.data.get("confirm") or "").strip().upper() != self.CONFIRM_PHRASE:
            return Response(
                {
                    "error": "confirmation_required",
                    "message": f'Type "{self.CONFIRM_PHRASE}" to confirm permanent deletion.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Include soft-deleted rows too — this is a true flush.
        qs = Lead.objects.all()
        if request.data.get("only_unassigned"):
            qs = qs.filter(assigned_to__isnull=True)
        if statuses := request.data.get("statuses"):
            qs = qs.filter(status__in=[s.lower() for s in statuses])

        count = qs.count()
        qs.delete()  # cascades to notes/followups/activities/custom values

        AuditLog.log(
            action=AuditAction.DELETE,
            actor_type="tenant_admin",
            actor_id=request.user.pk,
            actor_email=request.user.email,
            entity_type="Lead",
            description=f"FLUSHED {count} leads (permanent delete)",
            request=request,
        )
        logger.warning(
            f"[LeadFlush] {request.user.email} permanently deleted {count} leads."
        )

        return Response({"deleted": count}, status=status.HTTP_200_OK)


# ============================================================
# Follow-ups
# ============================================================

class FollowUpListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/leads/{lead_id}/followups/   → List follow-ups for a lead
    POST /api/v1/leads/{lead_id}/followups/   → Schedule new follow-up
    """

    permission_classes = [IsAuthenticatedAgent]

    def get_serializer_class(self):
        return FollowUpCreateSerializer if self.request.method == "POST" else FollowUpSerializer

    def get_queryset(self):
        assert_lead_visible(self.request.user, self.kwargs["lead_id"])
        return FollowUp.objects.filter(
            lead_id=self.kwargs["lead_id"]
        ).select_related("assigned_to").order_by("scheduled_at")

    def perform_create(self, serializer):
        agent = self.request.user
        assert_lead_visible(agent, self.kwargs["lead_id"])
        followup = serializer.save(
            lead_id=self.kwargs["lead_id"],
            assigned_to=serializer.validated_data.get("assigned_to") or agent,
        )
        # Update lead's next_followup_at
        lead = followup.lead
        if not lead.next_followup_at or followup.scheduled_at < lead.next_followup_at:
            lead.next_followup_at = followup.scheduled_at
            lead.save(update_fields=["next_followup_at"])

        LeadActivity.objects.create(
            lead=lead,
            activity_type="followup_created",
            description=(
                f"Follow-up scheduled: {followup.get_followup_type_display()} "
                f"at {followup.scheduled_at.strftime('%d %b %H:%M')}"
            ),
            performed_by=agent,
        )

        # Tell the agent it landed on. A manager scheduling a follow-up on
        # someone else's lead was previously silent: the row appeared in the
        # database and the agent found out only if they happened to open that
        # lead. Scheduling your own is not worth a notification — you just did
        # it, and it would arrive before the dialog closed.
        if followup.assigned_to_id and followup.assigned_to_id != agent.pk:
            from apps.authentication.notifications import followup_scheduled

            followup_scheduled(followup)


class MyFollowUpsView(generics.ListAPIView):
    """
    GET /api/v1/leads/followups/mine/?days=14

    Every follow-up assigned to the caller that is still open, soonest first.

    Follow-ups could previously only be listed one lead at a time, so nothing
    could answer "what is coming up for me" — which is exactly what a phone
    needs in order to hand the reminders to Android and have them fire whether
    or not the app is running.

    Overdue ones are included deliberately. They are the ones that most need
    to be on the list.
    """

    permission_classes = [IsAuthenticatedAgent]
    serializer_class = FollowUpSerializer
    pagination_class = None

    def get_queryset(self):
        from datetime import timedelta

        try:
            days = max(1, min(int(self.request.query_params.get("days", 14)), 90))
        except (TypeError, ValueError):
            days = 14

        horizon = timezone.now() + timedelta(days=days)
        return (
            FollowUp.objects.filter(
                assigned_to=self.request.user,
                is_completed=False,
                scheduled_at__lte=horizon,
            )
            .select_related("lead", "assigned_to")
            .order_by("scheduled_at")[:200]
        )


class FollowUpCompleteView(APIView):
    """POST /api/v1/followups/{id}/complete/ — Mark follow-up as done."""

    permission_classes = [IsAuthenticatedAgent]

    def post(self, request, pk):
        # Only allow completing follow-ups on leads visible to this agent.
        try:
            followup = FollowUp.objects.select_related("lead").get(
                pk=pk, lead__in=leads_visible_to(request.user)
            )
        except FollowUp.DoesNotExist:
            return Response({"error": "not_found"}, status=404)

        notes = request.data.get("notes", "")
        followup.complete(notes=notes, agent=request.user)
        return Response({"id": followup.pk, "completed": True})


# ============================================================
# Notes & Activities
# ============================================================

class LeadNoteListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/leads/{lead_id}/notes/  → Notes for a lead
    POST /api/v1/leads/{lead_id}/notes/  → Add note
    """

    permission_classes = [IsAuthenticatedAgent]
    serializer_class = LeadNoteSerializer
    parser_classes = [MultiPartParser]

    def get_queryset(self):
        assert_lead_visible(self.request.user, self.kwargs["lead_id"])
        return LeadNote.objects.filter(
            lead_id=self.kwargs["lead_id"]
        ).select_related("agent").order_by("-is_pinned", "-created_at")

    def perform_create(self, serializer):
        assert_lead_visible(self.request.user, self.kwargs["lead_id"])
        note = serializer.save(
            lead_id=self.kwargs["lead_id"],
            agent=self.request.user,
        )
        LeadActivity.objects.create(
            lead=note.lead,
            activity_type="note_added",
            description=note.content[:100],
            performed_by=self.request.user,
        )


class LeadActivityListView(generics.ListAPIView):
    """GET /api/v1/leads/{lead_id}/activities/ — Immutable activity feed."""

    permission_classes = [IsAuthenticatedAgent]

    def get_queryset(self):
        assert_lead_visible(self.request.user, self.kwargs["lead_id"])
        return LeadActivity.objects.filter(
            lead_id=self.kwargs["lead_id"]
        ).select_related("performed_by").order_by("-timestamp")

    def get_serializer_class(self):
        from apps.leads.serializers import LeadActivitySerializer
        return LeadActivitySerializer


# ============================================================
# Import
# ============================================================

class LeadImportView(APIView):
    """
    POST /api/v1/leads/import/
    Upload CSV/XLSX file to import leads.
    Returns an import job ID for progress tracking.
    Plan-gated on LEAD_IMPORT.
    """

    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.LEAD_IMPORT
    parser_classes = [MultiPartParser]

    def post(self, request):
        from apps.leads.tasks import process_lead_import
        from django.db import connection

        file = request.FILES.get("file")
        if not file:
            return Response(
                {"error": "file_required", "message": "Please upload a CSV or XLSX file."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Accept any file — format auto-detected during parsing
        pass

        # Get column mapping from form data
        import json
        column_mapping = {}
        if mapping_str := request.data.get("column_mapping"):
            try:
                column_mapping = json.loads(mapping_str)
            except json.JSONDecodeError:
                pass

        # Get default assigned_to
        from apps.authentication.models import Agent
        assigned_to = None
        if assigned_id := request.data.get("assigned_to"):
            assigned_to = Agent.objects.filter(pk=assigned_id, is_active=True).first()

        # ---- Batch & auto-assign options --------------------
        # `auto_assign` arrives from multipart form data, so it is the STRING
        # "true"/"false" — `bool("false")` is True, which would silently turn
        # auto-assign on for everyone who explicitly turned it off.
        raw_auto = str(request.data.get("auto_assign", "")).strip().lower()
        auto_assign = raw_auto in ("true", "1", "yes", "on")

        assign_to_agents = []
        if raw_agents := request.data.get("assign_to_agents"):
            try:
                parsed = json.loads(raw_agents) if isinstance(raw_agents, str) else raw_agents
                if isinstance(parsed, list):
                    # Keep the admin's order; round robin starts with their
                    # first pick. Validate against active agents so a stale id
                    # from the browser cannot silently shrink the rotation.
                    wanted = [int(x) for x in parsed]
                    live = set(
                        Agent.objects.filter(pk__in=wanted, is_active=True)
                        .values_list("pk", flat=True)
                    )
                    assign_to_agents = [pk for pk in wanted if pk in live]
            except (json.JSONDecodeError, TypeError, ValueError):
                assign_to_agents = []

        from apps.leads.services.distribution import Method

        assign_method = str(request.data.get("assign_method") or Method.ROUND_ROBIN)
        if assign_method not in Method.ALL:
            assign_method = Method.ROUND_ROBIN

        max_per_agent = None
        if raw_cap := request.data.get("assign_max_per_agent"):
            try:
                max_per_agent = max(1, int(raw_cap))
            except (TypeError, ValueError):
                max_per_agent = None

        if auto_assign and not assign_to_agents:
            return Response(
                {
                    "error": "agents_required",
                    "message": (
                        "Auto-assign is on but no active agents were selected. "
                        "Pick at least one agent, or turn auto-assign off."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # A batch name is required. "Batch 14" tells nobody where a
        # consignment came from, and the name is how anyone finds it again
        # when they come to assign or report on it weeks later.
        batch_name = str(request.data.get("batch_name") or "").strip()[:150]
        if not batch_name:
            return Response(
                {
                    "error": "batch_name_required",
                    "message": "Give this batch a name before importing.",
                    "detail": {"batch_name": ["Required."]},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create import job
        job = LeadImportJob.objects.create(
            imported_by=request.user,
            file=file,
            original_filename=file.name,
            column_mapping=column_mapping,
            duplicate_action=request.data.get("duplicate_action", "skip"),
            # When auto-assign is on, leads must land UNASSIGNED so the
            # distributor has something to place. Defaulting them to the
            # importing admin first would make every lead look assigned and
            # the distribution a no-op.
            default_assigned_to=None if auto_assign else (assigned_to or request.user),
            default_source=request.data.get("source", "manual"),
            batch_name=batch_name,
            auto_assign=auto_assign,
            assign_method=assign_method,
            assign_to_agents=assign_to_agents,
            assign_max_per_agent=max_per_agent,
        )

        # Kick off Celery task
        schema_name = connection.schema_name
        result = process_lead_import.apply_async(
            args=[schema_name, str(job.id)],
            queue="bulk_ops",
        )
        job.celery_task_id = result.id
        job.save(update_fields=["celery_task_id"])

        return Response(
            {
                "import_job_id": str(job.id),
                "message": "Import started. Use the job ID to track progress.",
                "status_url": f"/api/v1/leads/import/{job.id}/",
            },
            status=status.HTTP_202_ACCEPTED,
        )



def auto_map_custom_fields(headers: list, custom_fields: list) -> dict:
    """
    Guess which sheet column belongs to each custom field.

    The mapping screen defaults every field to "Do Not Import". Standard columns
    arrive with a guess already filled in; custom fields did not, so an admin who
    clicked straight through step 2 got leads with every custom field blank —
    which, on the lead detail screen, looks exactly like the import having
    dropped them.

    Matching is deliberately strict: a header only maps when it equals the
    field's name or its key once case, spaces, underscores and hyphens are
    normalised away, so "Loan Amount", "loan_amount" and "LOAN AMOUNT" all hit
    the same field while "amount" hits nothing. A wrong guess silently writes
    bad data into a field someone later has to notice and correct, which is a
    worse outcome than making them pick from the dropdown — so near-misses are
    deliberately left unmapped.

    Returns {"custom_<field_key>": "<header>"} for the confident matches only.
    """
    def norm(text) -> str:
        return "".join(ch for ch in str(text).lower() if ch.isalnum())

    by_header = {}
    for header in headers:
        # First header wins, so a duplicated column name cannot flip the target.
        by_header.setdefault(norm(header), header)

    mapping = {}
    for field in custom_fields:
        for candidate in (field.name, field.field_key):
            if header := by_header.get(norm(candidate)):
                mapping[f"custom_{field.field_key}"] = header
                break
    return mapping

class LeadImportPreviewView(APIView):
    """
    POST /api/v1/leads/import/preview/
    Upload CSV/XLSX file to parse headers and preview sample rows for column mapping.
    """

    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.LEAD_IMPORT
    parser_classes = [MultiPartParser]

    def post(self, request):
        from apps.leads.tasks import _parse_import_file
        from apps.leads.models import CustomField

        file = request.FILES.get("file")
        if not file:
            return Response(
                {"error": "file_required", "message": "Please upload a CSV or XLSX file."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filename = file.name.lower()
        file_content = file.read()
        rows = _parse_import_file(file_content, filename)
        if rows is None or not rows:
            return Response(
                {"error": "invalid_file", "message": "Could not read data from the uploaded file. Please make sure it is a valid CSV or Excel spreadsheet with header rows."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        headers = list(rows[0].keys())
        sample_rows = rows[:3]

        # Auto-match headers to CRM lead fields
        default_mapping = {
            "name": ["name", "full name", "contact name", "customer name", "lead name", "first name"],
            "phone": ["phone", "mobile", "contact", "phone number", "mobile number", "contact no", "cell"],
            "email": ["email", "email address", "mail"],
            "city": ["city", "location", "town"],
            "state": ["state"],
            "requirement": ["requirement", "query", "message", "remarks", "comments", "description"],
            "budget": ["budget", "amount", "price"],
            "notes": ["notes", "note"],
        }

        auto_mapping = {}
        normalized_headers = {h.lower().strip(): h for h in headers}
        for lead_field, aliases in default_mapping.items():
            for alias in aliases:
                if alias in normalized_headers:
                    auto_mapping[lead_field] = normalized_headers[alias]
                    break

        available_fields = [
            {"key": "name", "label": "Full Name / Lead Name", "required": True},
            {"key": "phone", "label": "Phone Number", "required": True},
            {"key": "email", "label": "Email Address"},
            {"key": "city", "label": "City"},
            {"key": "state", "label": "State"},
            {"key": "requirement", "label": "Requirement / Query"},
            {"key": "budget", "label": "Budget"},
            {"key": "notes", "label": "Notes / Remarks"},
        ]

        # Offer the tenant's custom fields as mapping targets, and pre-fill the
        # ones whose header is unambiguous — see auto_map_custom_fields.
        c_fields = list(CustomField.objects.filter(is_active=True))
        for cf in c_fields:
            available_fields.append({
                "key": f"custom_{cf.field_key}",
                "label": f"{cf.name} (Custom Field)",
            })
        auto_mapping.update(auto_map_custom_fields(headers, c_fields))

        return Response({
            "headers": headers,
            "sample_rows": sample_rows,
            "total_rows": len(rows),
            "auto_mapping": auto_mapping,
            "available_fields": available_fields,
        })


class LeadImportJobDetailView(generics.RetrieveAPIView):
    """GET /api/v1/leads/import/{id}/ — Poll import job status."""

    permission_classes = [IsManagerOrAdmin]
    serializer_class = LeadImportJobSerializer

    def get_queryset(self):
        return LeadImportJob.objects.filter(imported_by=self.request.user)


# ============================================================
# Custom Fields
# ============================================================

class CustomFieldListView(generics.ListAPIView):
    """
    GET /api/v1/leads/custom-fields/  → The tenant's custom fields.

    Read-only by design. These fields are the spreadsheet columns a client may
    map an import onto, and they are configured for each client from the
    platform's own panel — Tenants → the tenant → Import fields — not by the
    client themselves. POST used to be open to any tenant admin.
    """

    serializer_class = CustomFieldSerializer
    pagination_class = None  # Small finite list; return plain array
    permission_classes = [IsAuthenticatedAgent]

    def get_queryset(self):
        return CustomField.objects.filter(is_active=True).order_by("sort_order")


# ============================================================
# Dashboard Stats & Pipeline
# ============================================================

class LeadDashboardStatsView(APIView):
    """
    GET /api/v1/leads/stats/
    Returns aggregated lead statistics for the dashboard KPI cards.
    """

    permission_classes = [IsAuthenticatedAgent]

    def get(self, request):
        agent = request.user
        today = timezone.localdate()

        base_qs = leads_visible_to(agent)

        # Today's stats
        today_new = base_qs.filter(created_at__date=today).count()
        today_followups = FollowUp.objects.filter(
            lead__in=base_qs,
            scheduled_at__date=today,
            is_completed=False,
        ).count()
        overdue_followups = base_qs.filter(
            next_followup_at__lt=timezone.now(),
            next_followup_at__isnull=False,
        ).count()

        # Status breakdown
        status_counts = dict(
            base_qs.values_list("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )

        # Conversion rate (won / (won + lost))
        won = status_counts.get(LeadStatus.WON, 0)
        lost = status_counts.get(LeadStatus.LOST, 0)
        conversion = round((won / (won + lost) * 100) if (won + lost) > 0 else 0, 1)

        # Deal value
        pipeline_value = base_qs.filter(
            status__in=[LeadStatus.INTERESTED, LeadStatus.FOLLOW_UP, LeadStatus.NEGOTIATION]
        ).aggregate(total=Sum("deal_value"))["total"] or 0

        return Response({
            "today": {
                "new_leads": today_new,
                "followups_due": today_followups,
                "overdue_followups": overdue_followups,
            },
            "total": {
                "total_leads": base_qs.count(),
                "active_leads": base_qs.filter(
                    status__in=[
                        LeadStatus.NEW, LeadStatus.ATTEMPTED, LeadStatus.CONTACTED,
                        LeadStatus.INTERESTED, LeadStatus.FOLLOW_UP, LeadStatus.NEGOTIATION,
                    ]
                ).count(),
                "won": won,
                "lost": lost,
                "conversion_rate": conversion,
                "pipeline_value": float(pipeline_value),
            },
            "by_status": status_counts,
        })


class LeadPipelineView(APIView):
    """
    GET /api/v1/leads/pipeline/
    Returns leads grouped by status for the kanban board.
    Lightweight — only returns fields needed for the board cards.
    """

    permission_classes = [IsAuthenticatedAgent]

    def get(self, request):
        qs = leads_visible_to(request.user).select_related("assigned_to")

        pipeline_statuses = [
            LeadStatus.NEW, LeadStatus.ATTEMPTED, LeadStatus.CONTACTED,
            LeadStatus.INTERESTED, LeadStatus.FOLLOW_UP, LeadStatus.NEGOTIATION,
        ]

        result = {}
        for status_key in pipeline_statuses:
            leads = qs.filter(status=status_key).values(
                "id", "name", "phone", "city", "priority",
                "score", "deal_value", "next_followup_at",
                "assigned_to__name", "created_at",
            ).order_by("-priority", "-score")[:50]  # Cap per column
            result[status_key] = list(leads)

        return Response(result)


class LeadExportView(APIView):
    """
    GET /api/v1/leads/export/
    Export leads as CSV. Respects same filters as LeadListCreateView.
    Plan-gated on LEAD_EXPORT.
    Returns streaming CSV response.
    """

    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.LEAD_EXPORT

    def get(self, request):
        import csv
        from django.http import StreamingHttpResponse

        qs = leads_visible_to(request.user).select_related("assigned_to")

        # The same filters the list applies, so the file matches the screen it
        # was exported from. Source, priority, search and overdue were missing
        # here: narrowing the list to one source and pressing Export quietly
        # produced every lead in the tenant.
        params = request.query_params
        if status_filter := params.get("status"):
            qs = qs.filter(status=status_filter)
        if priority := params.get("priority"):
            qs = qs.filter(priority=priority)
        if source := params.get("source"):
            qs = qs.filter(source=source)
        if assigned_to := params.get("assigned_to"):
            qs = qs.filter(assigned_to_id=assigned_to)
        if batch := params.get("batch"):
            qs = qs.filter(batch_id=batch)
        if city := params.get("city"):
            qs = qs.filter(city__icontains=city)
        if search := params.get("search"):
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )
        if params.get("overdue") == "true":
            qs = qs.filter(
                next_followup_at__lt=timezone.now(),
                next_followup_at__isnull=False,
            )
        if date_from := params.get("date_from"):
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to := params.get("date_to"):
            qs = qs.filter(created_at__date__lte=date_to)

        # Cap export at 50,000 rows
        qs = qs.order_by("-created_at")[:50000]

        fields = [
            "name", "phone", "alternate_phone", "email", "city", "state",
            "source", "status", "priority", "score", "budget", "requirement",
            "deal_value", "assigned_to__name", "next_followup_at",
            "last_contacted_at", "contact_count", "is_dnd", "created_at",
        ]
        headers = [
            "Name", "Phone", "Alt Phone", "Email", "City", "State",
            "Source", "Status", "Priority", "Score", "Budget (₹)", "Requirement",
            "Deal Value (₹)", "Assigned To", "Next Follow-up",
            "Last Contacted", "Contact Count", "DND", "Created At",
        ]

        def generate():
            pseudo_buffer = _Echo()
            writer = csv.writer(pseudo_buffer)
            yield writer.writerow(headers)
            for row in qs.values_list(*fields):
                yield writer.writerow(row)

        filename = f"leads_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
        response = StreamingHttpResponse(generate(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        from apps.superadmin.models import AuditLog
        from apps.core.constants import AuditAction
        AuditLog.log(
            action=AuditAction.EXPORT,
            actor_type="agent",
            actor_id=request.user.pk,
            actor_email=request.user.email,
            entity_type="Lead",
            description="Exported leads CSV",
            request=request,
        )
        return response


class _Echo:
    """Pseudo file-like object for streaming CSV."""
    def write(self, value):
        return value


# ============================================================
# Call Queue API (industry-grade calling queue system)
# ============================================================

class CallQueueListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/leads/queues/   → List all queues (admin/manager)
    POST /api/v1/leads/queues/   → Create a queue (admin/manager)
    """

    permission_classes = [IsManagerOrAdmin]
    serializer_class = CallQueueSerializer
    pagination_class = None

    def get_queryset(self):
        return CallQueue.objects.prefetch_related("memberships__agent").order_by("name")


class CallQueueDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/v1/leads/queues/{id}/  (admin/manager)
    """

    permission_classes = [IsManagerOrAdmin]
    serializer_class = CallQueueSerializer

    def get_queryset(self):
        return CallQueue.objects.prefetch_related("memberships__agent")


class AvailableQueuesView(APIView):
    """
    GET /api/v1/leads/queues/available/
    Queues the current agent is a member of, with live pending-lead counts.
    """

    permission_classes = [IsAuthenticatedAgent]

    def get(self, request):
        agent = request.user
        queues = (
            CallQueue.objects.filter(is_active=True, memberships__agent=agent)
            .distinct()
            .order_by("name")
        )
        data = CallQueueSummarySerializer(
            queues, many=True, context={"agent": agent}
        ).data
        return Response(data)


class QueuePullNextView(APIView):
    """
    POST /api/v1/leads/queues/{id}/pull/
    Atomically check out the next eligible lead from the queue and lock it to
    the requesting agent. Guarantees no two agents ever receive the same lead.
    """

    permission_classes = [IsAuthenticatedAgent]

    def post(self, request, pk):
        agent = request.user

        try:
            queue = CallQueue.objects.get(pk=pk, is_active=True)
        except CallQueue.DoesNotExist:
            return Response(
                {"error": "not_found", "message": "Queue not found or inactive."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not queue.memberships.filter(agent=agent).exists():
            return Response(
                {"error": "not_a_member", "message": "You are not assigned to this queue."},
                status=status.HTTP_403_FORBIDDEN,
            )

        now = timezone.now()
        with transaction.atomic():
            # Lock the row at the DB level; skip rows another txn is locking.
            lead = (
                queue.eligible_leads(agent)
                .select_for_update(skip_locked=True)
                .first()
            )
            if lead is None:
                return Response(
                    {"empty": True, "message": "No leads available in this queue right now."},
                    status=status.HTTP_200_OK,
                )

            lead.locked_by = agent
            lead.locked_at = now
            lead.lock_expires_at = now + timedelta(minutes=queue.lock_ttl_minutes)
            lead.locked_queue = queue
            lead.save(update_fields=[
                "locked_by", "locked_at", "lock_expires_at", "locked_queue",
            ])

        return Response(
            {
                "lead": LeadDetailSerializer(lead, context={"request": request}).data,
                "lock_expires_at": lead.lock_expires_at.isoformat(),
                "queue": {"id": queue.pk, "name": queue.name, "mode": queue.mode},
            },
            status=status.HTTP_200_OK,
        )


class QueueReleaseView(APIView):
    """
    POST /api/v1/leads/queues/release/
    Release a lead the agent had checked out (e.g. on skip or session end).
    Body: { "lead_id": <id>, "mark_dialed": false }
    """

    permission_classes = [IsAuthenticatedAgent]

    def post(self, request):
        agent = request.user
        lead_id = request.data.get("lead_id")
        mark_dialed = bool(request.data.get("mark_dialed", False))

        try:
            lead = Lead.objects.get(pk=lead_id, locked_by=agent)
        except (Lead.DoesNotExist, ValueError, TypeError):
            return Response(
                {"error": "not_found", "message": "No such lead locked by you."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if mark_dialed:
            lead.mark_worked(dialed=True)
        lead.release_lock()

        return Response({"released": True, "lead_id": lead.pk})


# ============================================================
# Lead batches
# ============================================================

class LeadBatchListView(generics.ListAPIView):
    """
    GET /api/v1/leads/batches/

    Filters: status, source, kind, q (matches the name or the number).
    Ordered newest batch first, which is the one an admin almost always wants.
    """

    serializer_class = LeadBatchSerializer
    permission_classes = [IsManagerOrAdmin]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        from apps.leads.models import LeadBatch

        qs = LeadBatch.objects.select_related("created_by", "import_job")
        p = self.request.query_params
        if status_filter := p.get("status"):
            qs = qs.filter(status=status_filter)
        if source := p.get("source"):
            qs = qs.filter(source=source)
        if kind := p.get("kind"):
            qs = qs.filter(kind=kind)
        if p.get("has_unassigned") == "true":
            # Batches with at least one lead still to place — the working set
            # for someone who has come here to distribute.
            qs = qs.filter(leads__is_deleted=False, leads__assigned_to__isnull=True).distinct()
        if q := p.get("q"):
            cond = Q(name__icontains=q)
            if q.strip().isdigit():
                cond |= Q(number=int(q.strip()))
            qs = qs.filter(cond)
        return qs.order_by("-number")


class LeadBatchDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/v1/leads/batches/{id}/

    PATCH accepts `name` and `notes` only — everything else about a batch is
    decided by the system (see LeadBatchSerializer.read_only_fields).

    DELETE detaches the leads and removes the batch; it never deletes leads.
    Deleting a consignment record must not delete the people in it.
    """

    serializer_class = LeadBatchSerializer
    permission_classes = [IsManagerOrAdmin]

    def get_queryset(self):
        from apps.leads.models import LeadBatch

        return LeadBatch.objects.select_related("created_by", "import_job")

    def perform_destroy(self, instance):
        instance.leads.update(batch=None)
        instance.delete()


class LeadBatchStatusView(APIView):
    """POST /api/v1/leads/batches/{id}/status/ {"status": "closed"|"open"}"""

    permission_classes = [IsManagerOrAdmin]

    def post(self, request, pk):
        from apps.leads.models import LeadBatch

        batch = LeadBatch.objects.filter(pk=pk).first()
        if batch is None:
            return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

        wanted = (request.data.get("status") or "").strip()
        if wanted == LeadBatch.STATUS_CLOSED:
            batch.close()
        elif wanted == LeadBatch.STATUS_OPEN:
            batch.reopen()
        else:
            return Response(
                {"error": "invalid_status", "message": "status must be 'open' or 'closed'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(LeadBatchSerializer(batch).data)


class LeadBatchDistributeView(APIView):
    """
    POST /api/v1/leads/batches/distribute/

    Distribute the leads in one or more batches across agents. This is the
    endpoint the Batches screen calls: an admin ticks batch 1 and batch 3,
    picks four agents and a method, and only those batches are touched.

    Methods live in apps/leads/services/distribution.py and are shared with the
    import task's auto-assign, so a batch distributed by hand and one
    distributed on import split identically.
    """

    permission_classes = [IsManagerOrAdmin]

    def post(self, request):
        from apps.leads.models import LeadBatch
        from apps.leads.serializers import LeadBatchDistributeSerializer
        from apps.leads.services import distribution as dist

        serializer = LeadBatchDistributeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        agents = d["agent_ids"]  # validated → Agent objects, caller order kept

        lead_ids = dist.leads_for_batches(
            d["batch_ids"],
            only_unassigned=d.get("only_unassigned", True),
            limit=d.get("limit"),
        )
        if not lead_ids:
            return Response({
                "distributed": 0,
                "unassigned": 0,
                "per_agent": {},
                "message": (
                    "Nothing to distribute — every lead in the selected batch(es) "
                    "is already assigned."
                    if d.get("only_unassigned", True)
                    else "The selected batch(es) contain no leads."
                ),
            })

        result = dist.distribute(
            lead_ids, agents,
            method=d["method"],
            max_per_agent=d.get("max_per_agent"),
            actor=request.user,
        )

        labels = [
            b.label for b in LeadBatch.objects.filter(pk__in=d["batch_ids"])
        ]
        result["batches"] = labels

        AuditLog.log(
            action=AuditAction.BULK_ACTION,
            actor_type="tenant_admin",
            actor_id=request.user.pk,
            actor_email=request.user.email,
            entity_type="Lead",
            description=(
                f"Distributed {result['distributed']} lead(s) from "
                f"{len(d['batch_ids'])} batch(es) across {len(agents)} agent(s) "
                f"using {d['method']}"
            ),
            request=request,
        )
        return Response(result)


class LeadBatchStatsView(APIView):
    """
    GET /api/v1/leads/batches/{id}/stats/

    Per-agent breakdown and status mix for one batch — what an admin looks at
    after distributing, to check the split landed the way they meant.
    """

    permission_classes = [IsManagerOrAdmin]

    def get(self, request, pk):
        from apps.leads.models import Lead, LeadBatch

        batch = LeadBatch.objects.filter(pk=pk).first()
        if batch is None:
            return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

        leads = Lead.objects.filter(batch=batch, is_deleted=False)
        by_agent = list(
            leads.filter(assigned_to__isnull=False)
            .values("assigned_to")
            .annotate(n=Count("id"), name=F("assigned_to__name"))
            .order_by("-n")
        )
        by_status = dict(
            leads.values_list("status").annotate(n=Count("id")).values_list("status", "n")
        )

        return Response({
            "batch": LeadBatchSerializer(batch).data,
            "total": leads.count(),
            "unassigned": leads.filter(assigned_to__isnull=True).count(),
            "by_agent": [
                {"agent_id": r["assigned_to"], "name": r["name"], "leads": r["n"]}
                for r in by_agent
            ],
            "by_status": by_status,
        })
