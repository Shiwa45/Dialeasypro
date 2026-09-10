"""
TeleCRM Backend — apps/authentication/serializers_notifications.py

Kept beside the notification views rather than in the main serializers module,
which is already long and concerns login, agents and teams.
"""
from rest_framework import serializers

from apps.authentication.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """
    The REST shape.

    Field names match apps/authentication/notifications.py :: serialize(),
    which builds the WebSocket frame. A client receives the same object
    whether it arrived live or on a page load, so there is one parser rather
    than two that drift.
    """

    lead_id = serializers.IntegerField(source="lead_id_ref", read_only=True)
    followup_id = serializers.IntegerField(source="followup_id_ref", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id", "kind", "title", "body",
            "lead_id", "followup_id", "url",
            "is_read", "created_at",
        ]
        read_only_fields = fields
