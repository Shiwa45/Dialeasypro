"""
TeleCRM Backend — apps/automation/views.py

GET/POST   /api/v1/automation/workflows/
GET/PATCH/DELETE /api/v1/automation/workflows/{id}/
POST       /api/v1/automation/workflows/{id}/toggle/      {"is_active": true}
POST       /api/v1/automation/workflows/{id}/duplicate/
POST       /api/v1/automation/workflows/{id}/run/         {"lead_id": 12}  — run its steps on one lead now
GET        /api/v1/automation/runs/?workflow=&lead=&status=
POST       /api/v1/automation/runs/{id}/cancel/
GET        /api/v1/automation/options/                     — everything the editor offers

Tenant admins only, on plans with "Follow-up Automation Rules".
"""
from django.db.models import Count, Q
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import HasFeatureAccess, IsAuthenticatedAgent, IsTenantAdmin
from apps.automation.constants import Action, RunStatus, Trigger
from apps.automation.models import Workflow, WorkflowRun
from apps.automation.serializers import WorkflowRunSerializer, WorkflowSerializer
from apps.core.constants import FeatureKey
from apps.core.pagination import StandardResultsSetPagination


class _Admin:
    permission_classes = [IsAuthenticatedAgent, IsTenantAdmin, HasFeatureAccess]
    required_feature = FeatureKey.FOLLOW_UP_AUTOMATION


def _bad(message, code="invalid", http=status.HTTP_400_BAD_REQUEST):
    return Response({"error": code, "message": message}, status=http)


class WorkflowListCreateView(_Admin, generics.ListCreateAPIView):
    serializer_class = WorkflowSerializer
    pagination_class = None

    def get_queryset(self):
        return Workflow.objects.select_related("created_by").annotate(
            open_runs_count=Count("runs", filter=Q(runs__status__in=RunStatus.OPEN)),
        ).order_by("-is_active", "name")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class WorkflowDetailView(_Admin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = WorkflowSerializer
    queryset = Workflow.objects.select_related("created_by")


class WorkflowToggleView(_Admin, APIView):
    def post(self, request, pk):
        wf = Workflow.objects.filter(pk=pk).first()
        if wf is None:
            return _bad("Workflow not found.", "not_found", status.HTTP_404_NOT_FOUND)
        wf.is_active = bool(request.data.get("is_active", not wf.is_active))
        wf.save(update_fields=["is_active", "updated_at"])
        if not wf.is_active:
            # Runs on a wait stop at their next step (the engine checks);
            # nothing is cancelled here, so switching back on lets them carry on.
            pass
        return Response(WorkflowSerializer(wf).data)


class WorkflowDuplicateView(_Admin, APIView):
    def post(self, request, pk):
        wf = Workflow.objects.filter(pk=pk).first()
        if wf is None:
            return _bad("Workflow not found.", "not_found", status.HTTP_404_NOT_FOUND)
        copy = Workflow.objects.create(
            name=f"{wf.name} (copy)"[:120], description=wf.description, is_active=False,
            trigger=wf.trigger, trigger_config=wf.trigger_config, conditions=wf.conditions,
            steps=wf.steps, repeat=wf.repeat, quiet_hours_enabled=wf.quiet_hours_enabled,
            quiet_start=wf.quiet_start, quiet_end=wf.quiet_end, created_by=request.user,
        )
        return Response(WorkflowSerializer(copy).data, status=status.HTTP_201_CREATED)


class WorkflowRunNowView(_Admin, APIView):
    """Run the workflow's steps on one lead now — to try it on your own number."""

    def post(self, request, pk):
        from apps.automation.services.engine import start_manual
        from apps.leads.models import Lead

        wf = Workflow.objects.filter(pk=pk).first()
        if wf is None:
            return _bad("Workflow not found.", "not_found", status.HTTP_404_NOT_FOUND)
        lead = Lead.objects.filter(pk=request.data.get("lead_id"), is_deleted=False).first()
        if lead is None:
            return _bad("Pick a lead to run it on.", "lead_required")
        if not wf.steps:
            return _bad("Add a step first.", "no_steps")
        run = start_manual(wf, lead, actor=request.user)
        return Response(WorkflowRunSerializer(run).data, status=status.HTTP_201_CREATED)


class WorkflowRunListView(_Admin, generics.ListAPIView):
    serializer_class = WorkflowRunSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = WorkflowRun.objects.select_related("workflow", "lead")
        p = self.request.query_params
        if wf := p.get("workflow"):
            qs = qs.filter(workflow_id=wf)
        if lead := p.get("lead"):
            qs = qs.filter(lead_id=lead)
        if st := p.get("status"):
            qs = qs.filter(status=st)
        if p.get("errors") == "true":
            qs = qs.filter(has_errors=True)
        return qs.order_by("-created_at")


class WorkflowRunCancelView(_Admin, APIView):
    def post(self, request, pk):
        from django.utils import timezone

        run = WorkflowRun.objects.filter(pk=pk).first()
        if run is None:
            return _bad("Run not found.", "not_found", status.HTTP_404_NOT_FOUND)
        if run.status not in RunStatus.OPEN:
            return _bad("This run has already finished.", "finished")
        run.status = RunStatus.CANCELLED
        run.finished_at = timezone.now()
        run.next_run_at = None
        run.log = list(run.log or []) + [{
            "step": run.current_step, "type": "end", "result": "skipped",
            "detail": f"Stopped by {request.user.name}.", "at": timezone.now().isoformat(),
        }]
        run.save()
        return Response(WorkflowRunSerializer(run).data)


class WorkflowOptionsView(_Admin, APIView):
    """Everything the editor's dropdowns offer, in one call."""

    def get(self, request):
        from apps.authentication.models import Agent
        from apps.calls.models import CallDisposition
        from apps.communications.models import WhatsAppConfig, WhatsAppTemplate
        from apps.core.constants import FollowUpType, LeadSource, LeadStatus
        from apps.leads.models import LeadBatch

        return Response({
            "triggers": [
                {"key": k, "label": label, "description": Trigger.DESCRIPTIONS.get(k, ""),
                 "scanned": k in Trigger.SCANNED}
                for k, label in Trigger.CHOICES
            ],
            "actions": [{"key": k, "label": label} for k, label in Action.CHOICES],
            "statuses": [{"key": k, "label": label} for k, label in LeadStatus.CHOICES],
            "sources": [{"key": k, "label": label} for k, label in LeadSource.CHOICES],
            "followup_types": [{"key": k, "label": label} for k, label in FollowUpType.CHOICES],
            "dispositions": [
                {"id": d.pk, "name": d.name, "category": d.category}
                for d in CallDisposition.objects.filter(is_active=True).order_by("sort_order", "name")
            ],
            "agents": [
                {"id": a.pk, "name": a.name, "role": a.role}
                for a in Agent.objects.filter(is_active=True).order_by("name")
            ],
            "batches": [
                {"id": b.pk, "name": b.name}
                for b in LeadBatch.objects.order_by("-created_at")[:200]
            ],
            "templates": [
                {"id": t.pk, "name": t.name, "status": t.status, "body_text": t.body_text,
                 "account": t.account_id, "account_label": t.account.label if t.account else None,
                 "unmapped": _unmapped(t)}
                for t in WhatsAppTemplate.objects.filter(is_active=True).select_related("account").order_by("name")
            ],
            "whatsapp_numbers": [
                {"id": a.pk, "label": a.label, "display_phone": a.display_phone,
                 "is_default": a.is_default, "is_active": a.is_active}
                for a in WhatsAppConfig.objects.order_by("-is_default", "label")
            ],
            "placeholders": ["name", "first_name", "phone", "email", "city", "requirement",
                             "agent_name", "agent_phone"],
        })


def _unmapped(template) -> list:
    from apps.communications.whatsapp_ready import unmapped_placeholders

    return unmapped_placeholders(template)
