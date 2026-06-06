"""
TeleCRM Backend — apps/calls/mvt_views.py

Django MVT views for the call log in the tenant admin web UI.
All views are server-rendered with HTMX for live updates.

Routes (under /crm/calls/):
  GET  /             → CallListMVTView       — filterable call log table
  GET  /{id}/        → CallDetailMVTView     — call detail + recording player
  GET  /stats/       → CallStatsMVTView      — call analytics dashboard
  POST /log/         → ManualCallLogMVTView  — log a call that happened outside CRM
  POST /{id}/note/   → CallNoteAddMVTView    — HTMX: add note to call
"""
import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.authentication.permissions import role_required, tenant_admin_required
from apps.calls.models import CallDisposition, CallLog, CallRecording
from apps.core.constants import AgentRole, CallDirection

logger = logging.getLogger(__name__)


class CallListMVTView(View):
    """GET /crm/calls/ — Paginated call log with filters."""

    template_name = "tenant_admin/calls/list.html"

    @tenant_admin_required
    def get(self, request):
        agent = request.agent
        qs = CallLog.objects.select_related(
            "agent", "lead", "disposition"
        ).order_by("-started_at")

        # Role-based scoping
        if agent.role == AgentRole.AGENT:
            qs = qs.filter(agent=agent)

        # Filters
        agent_filter = request.GET.get("agent", "")
        direction = request.GET.get("direction", "")
        connected = request.GET.get("connected", "")
        date_from = request.GET.get("date_from", "")
        date_to = request.GET.get("date_to", "")
        disposition_filter = request.GET.get("disposition", "")
        search = request.GET.get("search", "").strip()

        if agent_filter and agent.role in [AgentRole.ADMIN, AgentRole.MANAGER]:
            qs = qs.filter(agent_id=agent_filter)
        if direction:
            qs = qs.filter(direction=direction)
        if connected:
            qs = qs.filter(is_connected=connected == "1")
        if date_from:
            qs = qs.filter(started_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(started_at__date__lte=date_to)
        if disposition_filter:
            qs = qs.filter(disposition_id=disposition_filter)
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(phone_number__icontains=search) |
                Q(lead__name__icontains=search) |
                Q(notes__icontains=search)
            )

        paginator = Paginator(qs, 30)
        page = paginator.get_page(request.GET.get("page", 1))

        # Today's quick stats for the top bar
        today = timezone.now().date()
        today_calls = CallLog.objects.filter(started_at__date=today)
        if agent.role == AgentRole.AGENT:
            today_calls = today_calls.filter(agent=agent)

        from apps.authentication.models import Agent as AgentModel
        agents = AgentModel.objects.filter(is_active=True).values("id", "name")
        dispositions = CallDisposition.objects.filter(is_active=True).order_by("sort_order")

        ctx = {
            "page_obj": page,
            "calls": page.object_list,
            "page_title": "Call Log",
            "dispositions": dispositions,
            "agents": list(agents),
            "direction_choices": CallDirection.CHOICES,
            "today_stats": {
                "total": today_calls.count(),
                "connected": today_calls.filter(is_connected=True).count(),
            },
            "filters": {
                "agent": agent_filter,
                "direction": direction,
                "connected": connected,
                "date_from": date_from,
                "date_to": date_to,
                "disposition": disposition_filter,
                "search": search,
            },
        }
        return render(request, self.template_name, ctx)


class CallDetailMVTView(View):
    """GET /crm/calls/{id}/ — Call detail with recording player."""

    template_name = "tenant_admin/calls/detail.html"

    @tenant_admin_required
    def get(self, request, pk):
        agent = request.agent
        qs = CallLog.objects.select_related("agent", "lead", "disposition")
        if agent.role == AgentRole.AGENT:
            qs = qs.filter(agent=agent)
        call = get_object_or_404(qs, pk=pk)

        recording_url = None
        if hasattr(call, "recording") and call.recording.file:
            try:
                recording_url = call.recording.get_presigned_url()
            except Exception:
                pass

        dispositions = CallDisposition.objects.filter(is_active=True).order_by("sort_order")
        ctx = {
            "call": call,
            "recording_url": recording_url,
            "dispositions": dispositions,
            "page_title": f"Call — {call.phone_number}",
        }
        return render(request, self.template_name, ctx)

    @tenant_admin_required
    def post(self, request, pk):
        """Update call disposition and notes inline."""
        agent = request.agent
        qs = CallLog.objects.all()
        if agent.role == AgentRole.AGENT:
            qs = qs.filter(agent=agent)
        call = get_object_or_404(qs, pk=pk)

        disposition_id = request.POST.get("disposition")
        notes = request.POST.get("notes", "").strip()

        if disposition_id:
            try:
                call.disposition = CallDisposition.objects.get(pk=disposition_id)
            except CallDisposition.DoesNotExist:
                pass
        if notes:
            call.notes = notes
        call.save(update_fields=["disposition", "notes"])
        messages.success(request, "Call updated.")
        return redirect("call_detail", pk=pk)


class ManualCallLogMVTView(View):
    """GET/POST /crm/calls/log/ — Manually log a call made outside the CRM."""

    template_name = "tenant_admin/calls/log_form.html"

    @tenant_admin_required
    def get(self, request):
        from apps.calls.forms import ManualCallLogForm
        from apps.leads.models import Lead
        form = ManualCallLogForm()
        dispositions = CallDisposition.objects.filter(is_active=True).order_by("sort_order")
        # Pre-fill lead if ?lead= param provided
        lead_id = request.GET.get("lead")
        lead = None
        if lead_id:
            lead = Lead.objects.filter(pk=lead_id, is_deleted=False).first()
        return render(request, self.template_name, {
            "form": form,
            "dispositions": dispositions,
            "prefill_lead": lead,
            "page_title": "Log Call",
        })

    @tenant_admin_required
    def post(self, request):
        from apps.calls.forms import ManualCallLogForm
        from apps.leads.models import Lead, LeadActivity
        form = ManualCallLogForm(request.POST)
        if form.is_valid():
            call = form.save(commit=False)
            call.agent = request.agent
            call.provider = "manual"
            call.save()

            # Update lead activity if linked
            if call.lead:
                call.lead.log_contact(contact_type="call")
                LeadActivity.objects.create(
                    lead=call.lead,
                    activity_type="call",
                    description=(
                        f"Manual call log — "
                        f"{'Connected' if call.is_connected else 'Not Connected'} "
                        f"({call.duration_display})"
                        + (f". {call.notes}" if call.notes else "")
                    ),
                    performed_by=request.agent,
                    meta={"call_id": str(call.id), "duration": call.duration_seconds},
                )

            messages.success(request, "Call logged successfully.")
            if call.lead:
                return redirect("tenant_admin:lead_detail", pk=call.lead_id)
            return redirect("call_list")

        dispositions = CallDisposition.objects.filter(is_active=True)
        return render(request, self.template_name, {
            "form": form,
            "dispositions": dispositions,
            "page_title": "Log Call",
        })


class CallStatsMVTView(View):
    """GET /crm/calls/stats/ — Call analytics page for managers/admins."""

    template_name = "tenant_admin/calls/stats.html"

    @role_required(AgentRole.MANAGER, AgentRole.ADMIN)
    def get(self, request):
        from django.db.models import Avg, Count, Q, Sum
        from apps.authentication.models import Agent as AgentModel

        date_from = request.GET.get("date_from", "")
        date_to = request.GET.get("date_to", "")
        agent_id = request.GET.get("agent", "")

        qs = CallLog.objects.all()
        if date_from:
            qs = qs.filter(started_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(started_at__date__lte=date_to)
        if agent_id:
            qs = qs.filter(agent_id=agent_id)

        # Aggregate stats
        stats = qs.aggregate(
            total=Count("id"),
            connected=Count("id", filter=Q(is_connected=True)),
            total_duration=Sum("duration_seconds", filter=Q(is_connected=True)),
            avg_duration=Avg("duration_seconds", filter=Q(is_connected=True)),
        )
        stats["connection_rate"] = round(
            (stats["connected"] or 0) / max(stats["total"] or 1, 1) * 100, 1
        )

        # Per-agent breakdown
        agent_breakdown = (
            qs.values("agent__name", "agent__id")
            .annotate(
                total=Count("id"),
                connected=Count("id", filter=Q(is_connected=True)),
                total_duration=Sum("duration_seconds"),
            )
            .order_by("-total")
        )

        # By disposition
        by_disposition = (
            qs.filter(disposition__isnull=False)
            .values("disposition__name", "disposition__is_positive")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        agents = AgentModel.objects.filter(is_active=True).values("id", "name")
        ctx = {
            "stats": stats,
            "agent_breakdown": list(agent_breakdown),
            "by_disposition": list(by_disposition),
            "agents": list(agents),
            "filters": {"date_from": date_from, "date_to": date_to, "agent": agent_id},
            "page_title": "Call Analytics",
        }
        return render(request, self.template_name, ctx)
