"""
TeleCRM Backend — apps/authentication/notification_views.py

The agent's own notifications. Every endpoint here is scoped to
request.user and cannot be widened by a query parameter — a notification is
addressed to one person, and there is no legitimate reason for an admin to
read someone else's through this API.
"""
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.models import Notification
from apps.authentication.serializers_notifications import NotificationSerializer
from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsAuthenticatedAgent


class NotificationListAPIView(generics.ListAPIView):
    """
    GET /api/v1/auth/notifications/?unread=true

    Newest first. `unread=true` narrows to what still needs attention, which
    is what the bell opens on.
    """

    permission_classes = [IsAuthenticatedAgent]
    serializer_class = NotificationSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user)
        unread = self.request.query_params.get("unread")
        if unread and unread.lower() == "true":
            qs = qs.filter(is_read=False)
        if kind := self.request.query_params.get("kind"):
            qs = qs.filter(kind=kind)
        # created_at is indexed with recipient and is_read; ordering on it
        # explicitly rather than leaning on Meta keeps the pager stable.
        return qs.order_by("-created_at", "-id")


class NotificationUnreadCountAPIView(APIView):
    """
    GET /api/v1/auth/notifications/unread-count/

    Just the number. The bell polls this, so it counts rather than serialising
    a page of rows to find out how many there are.
    """

    permission_classes = [IsAuthenticatedAgent]

    def get(self, request):
        count = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
        return Response({"unread": count})


class NotificationReadAPIView(APIView):
    """POST /api/v1/auth/notifications/{pk}/read/ — mark one as seen."""

    permission_classes = [IsAuthenticatedAgent]

    def post(self, request, pk):
        note = Notification.objects.filter(pk=pk, recipient=request.user).first()
        if note is None:
            # Also the answer when the notification belongs to someone else,
            # deliberately: a 403 would confirm that it exists.
            return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)
        note.mark_read()
        return Response(NotificationSerializer(note).data)


class NotificationReadAllAPIView(APIView):
    """POST /api/v1/auth/notifications/read-all/ — clear the badge."""

    permission_classes = [IsAuthenticatedAgent]

    def post(self, request):
        updated = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return Response({"marked_read": updated})


class FcmTokenAPIView(APIView):
    """
    POST /api/v1/auth/notifications/device/  {"fcm_token": "..."}

    Register the calling agent's device for push. Agent.fcm_token has existed
    since the first migration with nothing to write it; this is that endpoint.
    Sending an empty token unregisters, which is what a client should do on
    logout so the next person to use the phone does not receive the previous
    agent's follow-ups.
    """

    permission_classes = [IsAuthenticatedAgent]

    def post(self, request):
        token = (request.data.get("fcm_token") or "").strip()
        agent = request.user
        agent.fcm_token = token
        agent.save(update_fields=["fcm_token"])
        return Response({"registered": bool(token)})
