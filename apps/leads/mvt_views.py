"""
TeleCRM Backend — apps/leads/mvt_views.py

Django MVT (Model-View-Template) views for the tenant admin web UI.
These render server-side HTML for the CRM web interface (Tailwind + HTMX).

All views require tenant_admin_required decorator.

Routing: /crm/leads/* (added to apps/authentication/urls.py → config/urls.py)
"""
import json
import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.authentication.permissions import role_required, tenant_admin_required
from apps.core.constants import AgentRole, FollowUpType, LeadPriority, LeadSource, LeadStatus
from apps.leads.models import CustomField, FollowUp, Lead, LeadImportJob, LeadNote

logger = logging.getLogger(__name__)


class LeadListMVTView(View):
    """GET /crm/leads/ — Paginated lead list with filters."""

    template_name = "tenant_admin/leads/list.html"

    @tenant_admin_required
    def get(self, request):
        qs = Lead.objects.filter(is_deleted=False).select_related("assigned_to")
        agent = request.agent

        # Role-based scoping
        if agent.role == AgentRole.AGENT:
            qs = qs.filter(assigned_to=agent)

        # Filters from query params
        status_filter = request.GET.get("status", "")
        priority_filter = request.GET.get("priority", "")
        source_filter = request.GET.get("source", "")
        search = request.GET.get("search", "").strip()
        overdue = request.GET.get("overdue", "")

        if status_filter:
            qs = qs.filter(status=status_filter)
        if priority_filter:
            qs = qs.filter(priority=priority_filter)
        if source_filter:
            qs = qs.filter(source=source_filter)
        if search:
            from django.db.models import Q
            qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search))
        if overdue:
            qs = qs.filter(next_followup_at__lt=timezone.now(), next_followup_at__isnull=False)

        qs = qs.order_by("-created_at")
        paginator = Paginator(qs, 25)
        page = paginator.get_page(request.GET.get("page", 1))

        # Agents for filter dropdown
        from apps.authentication.models import Agent
        agents = Agent.objects.filter(is_active=True).values("id", "name")

        ctx = {
            "page_obj": page,
            "leads": page.object_list,
            "page_title": "Leads",
            "status_choices": LeadStatus.CHOICES,
            "priority_choices": LeadPriority.CHOICES,
            "source_choices": LeadSource.CHOICES,
            "agents": list(agents),
            "filters": {
                "status": status_filter,
                "priority": priority_filter,
                "source": source_filter,
                "search": search,
                "overdue": overdue,
            },
            "total_count": qs.count(),
        }
        return render(request, self.template_name, ctx)


class LeadDetailMVTView(View):
    """GET /crm/leads/{id}/ — Full lead detail with activity feed."""

    template_name = "tenant_admin/leads/detail.html"

    @tenant_admin_required
    def get(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk, is_deleted=False)
        followups = lead.followups.order_by("scheduled_at")
        notes = lead.notes.select_related("agent").order_by("-is_pinned", "-created_at")
        activities = lead.activities.select_related("performed_by").order_by("-timestamp")
        custom_fields = CustomField.objects.filter(is_active=True).order_by("sort_order")
        cv_map = {v.field_id: v.value for v in lead.custom_field_values.all()}

        from apps.authentication.models import Agent
        agents = Agent.objects.filter(is_active=True).values("id", "name")

        ctx = {
            "lead": lead,
            "followups": followups,
            "notes": notes,
            "activities": activities,
            "custom_fields": custom_fields,
            "custom_values": cv_map,
            "agents": list(agents),
            "followup_types": FollowUpType.CHOICES,
            "status_choices": LeadStatus.CHOICES,
            "page_title": lead.name,
        }
        return render(request, self.template_name, ctx)


class LeadCreateMVTView(View):
    """GET/POST /crm/leads/add/ — Create a new lead."""

    template_name = "tenant_admin/leads/form.html"

    @tenant_admin_required
    def get(self, request):
        from apps.leads.forms import LeadForm
        from apps.authentication.models import Agent
        form = LeadForm()
        agents = Agent.objects.filter(is_active=True).values("id", "name")
        return render(request, self.template_name, {
            "form": form,
            "agents": list(agents),
            "page_title": "Add Lead",
            "action": "create",
            "status_choices": LeadStatus.CHOICES,
            "source_choices": LeadSource.CHOICES,
        })

    @tenant_admin_required
    def post(self, request):
        from apps.leads.forms import LeadForm
        from apps.authentication.models import Agent
        form = LeadForm(request.POST)
        if form.is_valid():
            lead = form.save(commit=False)
            if not lead.assigned_to_id:
                lead.assigned_to = request.agent
            lead.save()
            messages.success(request, f"Lead '{lead.name}' created.")
            return redirect("tenant_admin:lead_detail", pk=lead.pk)

        agents = Agent.objects.filter(is_active=True).values("id", "name")
        return render(request, self.template_name, {
            "form": form,
            "agents": list(agents),
            "page_title": "Add Lead",
            "action": "create",
        })


class LeadUpdateMVTView(View):
    """GET/POST /crm/leads/{id}/edit/ — Edit lead fields."""

    template_name = "tenant_admin/leads/form.html"

    @tenant_admin_required
    def get(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk, is_deleted=False)
        from apps.leads.forms import LeadForm
        from apps.authentication.models import Agent
        form = LeadForm(instance=lead)
        agents = Agent.objects.filter(is_active=True).values("id", "name")
        return render(request, self.template_name, {
            "form": form,
            "lead": lead,
            "agents": list(agents),
            "page_title": f"Edit — {lead.name}",
            "action": "edit",
        })

    @tenant_admin_required
    def post(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk, is_deleted=False)
        old_status = lead.status
        from apps.leads.forms import LeadForm
        from apps.authentication.models import Agent
        form = LeadForm(request.POST, instance=lead)
        if form.is_valid():
            updated_lead = form.save()
            if old_status != updated_lead.status:
                from apps.leads.models import LeadActivity
                LeadActivity.objects.create(
                    lead=updated_lead,
                    activity_type="status_change",
                    description=f"Status: {old_status} → {updated_lead.status}",
                    performed_by=request.agent,
                )
            messages.success(request, f"Lead updated.")
            return redirect("tenant_admin:lead_detail", pk=lead.pk)
        agents = Agent.objects.filter(is_active=True).values("id", "name")
        return render(request, self.template_name, {
            "form": form, "lead": lead, "agents": list(agents),
            "page_title": f"Edit — {lead.name}", "action": "edit",
        })


class LeadKanbanMVTView(View):
    """GET /crm/leads/kanban/ — Pipeline kanban board view."""

    template_name = "tenant_admin/leads/kanban.html"

    @tenant_admin_required
    def get(self, request):
        agent = request.agent
        qs = Lead.objects.filter(is_deleted=False)
        if agent.role == AgentRole.AGENT:
            qs = qs.filter(assigned_to=agent)

        PIPELINE_STATUSES = [
            LeadStatus.NEW, LeadStatus.ATTEMPTED, LeadStatus.CONTACTED,
            LeadStatus.INTERESTED, LeadStatus.FOLLOW_UP, LeadStatus.NEGOTIATION,
        ]
        columns = {}
        for st in PIPELINE_STATUSES:
            columns[st] = {
                "label": dict(LeadStatus.CHOICES).get(st, st),
                "leads": list(qs.filter(status=st).select_related("assigned_to")[:50]),
                "count": qs.filter(status=st).count(),
            }

        return render(request, self.template_name, {
            "columns": columns,
            "page_title": "Pipeline",
        })


class LeadImportMVTView(View):
    """GET/POST /crm/leads/import/ — CSV/XLSX import wizard."""

    template_name = "tenant_admin/leads/import.html"

    @role_required(AgentRole.MANAGER, AgentRole.ADMIN)
    def get(self, request):
        recent_jobs = LeadImportJob.objects.filter(
            imported_by=request.agent
        ).order_by("-created_at")[:5]
        from apps.authentication.models import Agent
        agents = Agent.objects.filter(is_active=True).values("id", "name")
        return render(request, self.template_name, {
            "recent_jobs": recent_jobs,
            "agents": list(agents),
            "source_choices": LeadSource.CHOICES,
            "page_title": "Import Leads",
        })

    @role_required(AgentRole.MANAGER, AgentRole.ADMIN)
    def post(self, request):
        from apps.leads.tasks import process_lead_import
        from django.db import connection

        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            messages.error(request, "Please select a file to upload.")
            return redirect("tenant_admin:lead_import")

        job = LeadImportJob.objects.create(
            imported_by=request.agent,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            duplicate_action=request.POST.get("duplicate_action", "skip"),
            default_source=request.POST.get("source", "manual"),
        )
        result = process_lead_import.apply_async(
            args=[connection.schema_name, str(job.id)],
            queue="bulk_ops",
        )
        job.celery_task_id = result.id
        job.save(update_fields=["celery_task_id"])

        messages.success(request, f"Import started! Tracking job: {job.id}")
        return redirect("tenant_admin:lead_import_status", pk=job.id)


class LeadImportStatusMVTView(View):
    """GET /crm/leads/import/{id}/ — Import job progress page."""

    template_name = "tenant_admin/leads/import_result.html"

    @tenant_admin_required
    def get(self, request, pk):
        job = get_object_or_404(LeadImportJob, pk=pk)
        return render(request, self.template_name, {
            "job": job, "page_title": "Import Status"
        })


# ---- HTMX partial: status update from kanban ---------------

class LeadStatusUpdateMVTView(View):
    """
    POST /crm/leads/{id}/status/ (HTMX)
    Updates lead status via HTMX drag-drop on kanban.
    Returns updated kanban card HTML.
    """

    @tenant_admin_required
    def post(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk, is_deleted=False)
        new_status = request.POST.get("status")
        if new_status in dict(LeadStatus.CHOICES):
            lead.update_status(new_status, agent=request.agent)
        # Return just the card partial (HTMX replaces it)
        return render(request, "tenant_admin/leads/partials/lead_card.html", {"lead": lead})


# ---- HTMX partial: quick add follow-up from lead detail ----

class FollowUpCreateMVTView(View):
    """
    POST /crm/leads/{lead_id}/followup/add/ (HTMX)
    Creates a follow-up and returns updated follow-up list.
    """

    @tenant_admin_required
    def post(self, request, lead_id):
        lead = get_object_or_404(Lead, pk=lead_id, is_deleted=False)
        from apps.leads.forms import FollowUpForm
        form = FollowUpForm(request.POST)
        if form.is_valid():
            fu = form.save(commit=False)
            fu.lead = lead
            fu.assigned_to = request.agent
            fu.save()
            messages.success(request, "Follow-up scheduled.")
        return render(request, "tenant_admin/leads/partials/followup_form.html", {
            "lead": lead,
            "followups": lead.followups.order_by("scheduled_at"),
            "form": form if not form.is_valid() else None,
        })


# ---- HTMX partial: quick add note -------------------------

class LeadNoteCreateMVTView(View):
    """
    POST /crm/leads/{lead_id}/note/add/ (HTMX)
    Adds a note and returns the updated notes section.
    """

    @tenant_admin_required
    def post(self, request, lead_id):
        lead = get_object_or_404(Lead, pk=lead_id, is_deleted=False)
        content = request.POST.get("content", "").strip()
        if content:
            LeadNote.objects.create(lead=lead, agent=request.agent, content=content)
        return render(request, "tenant_admin/leads/partials/notes.html", {
            "lead": lead,
            "notes": lead.notes.select_related("agent").order_by("-is_pinned", "-created_at"),
        })
