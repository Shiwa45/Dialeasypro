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
from django.db.models import Count, Q, Sum
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

    def get_serializer_class(self):
        if self.request.method == "POST":
            return LeadCreateSerializer
        return LeadListSerializer

    def get_queryset(self):
        # Role-based visibility (agents see only their assigned leads).
        qs = leads_visible_to(self.request.user).select_related("assigned_to")

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

        qs = qs.order_by("created_at")
        if d.get("limit"):
            qs = qs[: d["limit"]]

        lead_ids = list(qs.values_list("id", flat=True))
        if not lead_ids:
            return Response(
                {"distributed": 0, "per_agent": {}, "message": "No leads matched the filter."},
                status=status.HTTP_200_OK,
            )

        # Round-robin split across agents.
        from collections import defaultdict
        buckets = defaultdict(list)
        for i, lead_id in enumerate(lead_ids):
            buckets[agents[i % len(agents)].pk].append(lead_id)

        now = timezone.now()
        per_agent = {}
        for agent in agents:
            ids = buckets.get(agent.pk, [])
            if ids:
                # Update in chunks to keep the IN clause reasonable.
                for start in range(0, len(ids), 1000):
                    Lead.objects.filter(pk__in=ids[start:start + 1000]).update(
                        assigned_to=agent, assigned_at=now
                    )
            per_agent[agent.name] = len(ids)

        AuditLog.log(
            action=AuditAction.BULK_ACTION,
            actor_type="tenant_admin",
            actor_id=request.user.pk,
            actor_email=request.user.email,
            entity_type="Lead",
            description=f"Distributed {len(lead_ids)} leads across {len(agents)} agent(s)",
            request=request,
        )

        return Response(
            {"distributed": len(lead_ids), "per_agent": per_agent},
            status=status.HTTP_200_OK,
        )


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

        allowed_types = [
            "text/csv", "application/csv",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        ]
        if file.content_type not in allowed_types and not file.name.endswith((".csv", ".xlsx")):
            return Response(
                {
                    "error": "invalid_file_type",
                    "message": "Only CSV and XLSX files are supported.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

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

        # Create import job
        job = LeadImportJob.objects.create(
            imported_by=request.user,
            file=file,
            original_filename=file.name,
            column_mapping=column_mapping,
            duplicate_action=request.data.get("duplicate_action", "skip"),
            default_assigned_to=assigned_to or request.user,
            default_source=request.data.get("source", "manual"),
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


class LeadImportJobDetailView(generics.RetrieveAPIView):
    """GET /api/v1/leads/import/{id}/ — Poll import job status."""

    permission_classes = [IsManagerOrAdmin]
    serializer_class = LeadImportJobSerializer

    def get_queryset(self):
        return LeadImportJob.objects.filter(imported_by=self.request.user)


# ============================================================
# Custom Fields
# ============================================================

class CustomFieldListView(generics.ListCreateAPIView):
    """
    GET  /api/v1/leads/custom-fields/  → List tenant's custom fields
    POST /api/v1/leads/custom-fields/  → Create custom field (admin only)
    """

    serializer_class = CustomFieldSerializer
    pagination_class = None  # Small finite list; return plain array

    def get_permissions(self):
        # Reading custom fields is always allowed (agents must render existing
        # data); CREATING them is plan-gated on CUSTOM_FIELDS.
        if self.request.method == "POST":
            return [IsTenantAdmin(), feature_required(FeatureKey.CUSTOM_FIELDS)()]
        return [IsAuthenticatedAgent()]

    def get_queryset(self):
        return CustomField.objects.filter(is_active=True).order_by("sort_order")

    def perform_create(self, serializer):
        # Check plan limit
        from apps.plans.models import Subscription
        from apps.core.constants import SubscriptionStatus

        try:
            sub = Subscription.objects.filter(
                status__in=SubscriptionStatus.ACTIVE_STATUSES
            ).select_related("plan").first()
            if sub:
                current = CustomField.objects.filter(is_active=True).count()
                if current >= sub.plan.custom_fields_limit:
                    raise PlanLimitExceededException(
                        limit_type="custom_fields",
                        current=current,
                        max_allowed=sub.plan.custom_fields_limit,
                    )
        except PlanLimitExceededException:
            raise

        serializer.save()


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
        today = timezone.now().date()

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

        params = request.query_params
        if status_filter := params.get("status"):
            qs = qs.filter(status=status_filter)
        if assigned_to := params.get("assigned_to"):
            qs = qs.filter(assigned_to_id=assigned_to)
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

    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.AUTO_DIALER
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

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.AUTO_DIALER

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

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.AUTO_DIALER

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
