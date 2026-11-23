"""
TeleCRM Backend — apps/automation/serializers.py
"""
from rest_framework import serializers

from apps.automation import validation
from apps.automation.constants import Trigger
from apps.automation.models import Workflow, WorkflowRun


class WorkflowSerializer(serializers.ModelSerializer):
    trigger_label = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source="created_by.name", read_only=True, default=None)
    open_runs = serializers.SerializerMethodField()

    class Meta:
        model = Workflow
        fields = [
            "id", "name", "description", "is_active", "trigger", "trigger_label",
            "trigger_config", "conditions", "steps", "repeat",
            "quiet_hours_enabled", "quiet_start", "quiet_end",
            "runs_count", "last_run_at", "open_runs",
            "created_by", "created_by_name", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "runs_count", "last_run_at", "created_by", "created_at", "updated_at"]

    def get_trigger_label(self, obj) -> str:
        return dict(Trigger.CHOICES).get(obj.trigger, obj.trigger)

    def get_open_runs(self, obj) -> int:
        annotated = getattr(obj, "open_runs_count", None)
        if annotated is not None:
            return annotated
        from apps.automation.constants import RunStatus

        return obj.runs.filter(status__in=RunStatus.OPEN).count()

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Give the workflow a name.")
        return value

    def validate(self, data):
        inst = self.instance
        trigger = data.get("trigger", getattr(inst, "trigger", None))
        if trigger is None:
            raise serializers.ValidationError({"trigger": "Pick what starts the workflow."})
        if "trigger_config" in data or "trigger" in data or inst is None:
            data["trigger_config"] = validation.clean_trigger_config(
                trigger, data.get("trigger_config", getattr(inst, "trigger_config", {})),
            )
        if "conditions" in data or inst is None:
            data["conditions"] = validation.clean_conditions(data.get("conditions", {}))
        if "steps" in data or inst is None:
            data["steps"] = validation.clean_steps(data.get("steps", []))
        return data


class WorkflowRunSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source="workflow.name", read_only=True)
    lead_name = serializers.CharField(source="lead.name", read_only=True)
    lead_phone = serializers.CharField(source="lead.phone", read_only=True)
    total_steps = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowRun
        fields = [
            "id", "workflow", "workflow_name", "lead", "lead_name", "lead_phone",
            "trigger", "context", "status", "current_step", "total_steps", "next_run_at",
            "finished_at", "log", "has_errors", "error", "created_at",
        ]
        read_only_fields = fields

    def get_total_steps(self, obj) -> int:
        return len(obj.workflow.steps or [])
