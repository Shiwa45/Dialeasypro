"""
TeleCRM Backend — apps/ai/views.py

Every view here is gated on a plan feature (402 + upsell payload when the
tenant hasn't bought the AI Suite module) and scoped so a plain agent can only
read insights for their own calls.
"""
from django.db import connection
from django.db.models import Count, Sum
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.constants import InsightStatus
from apps.ai.models import CallInsight
from apps.ai.serializers import CallInsightSerializer, TranscriptSerializer
from apps.ai.tasks import analyse_call, backfill_transcripts, transcribe_call
from apps.calls.models import CallLog, CallRecording
from apps.core.constants import AgentRole, FeatureKey
from apps.core.permissions import (
    IsAuthenticatedAgent,
    IsManagerOrAdmin,
    IsTenantAdmin,
    feature_required,
)


def _visible_calls(agent):
    """A plain agent only ever sees their own calls."""
    qs = CallLog.objects.all()
    if agent.role == AgentRole.AGENT:
        qs = qs.filter(agent=agent)
    return qs


class _CallScopedView(APIView):
    """Resolves the call in the URL, 404ing if the agent may not see it."""

    def get_call(self, request, pk):
        return _visible_calls(request.user).filter(pk=pk).first()

    def not_found(self):
        return Response(
            {"error": "not_found", "message": "Call not found."},
            status=status.HTTP_404_NOT_FOUND,
        )


class InsightPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


# ============================================================
# Transcription
# ============================================================
class CallTranscriptView(_CallScopedView):
    """GET /api/v1/ai/calls/{call_id}/transcript/"""

    permission_classes = [
        IsAuthenticatedAgent,
        feature_required(FeatureKey.AI_CALL_TRANSCRIPTION),
    ]

    def get(self, request, pk):
        call = self.get_call(request, pk)
        if call is None:
            return self.not_found()
        recording = CallRecording.objects.filter(call=call).first()
        if recording is None:
            return Response(
                {"error": "no_recording", "message": "This call has no recording."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(TranscriptSerializer(recording).data)


class CallTranscribeView(_CallScopedView):
    """
    POST /api/v1/ai/calls/{call_id}/transcribe/

    Re-runs speech-to-text. Managers and admins only — each run costs ASR
    minutes, so it isn't something an agent should be able to loop on.
    """

    permission_classes = [
        IsAuthenticatedAgent,
        IsManagerOrAdmin,
        feature_required(FeatureKey.AI_CALL_TRANSCRIPTION),
    ]

    def post(self, request, pk):
        call = self.get_call(request, pk)
        if call is None:
            return self.not_found()
        if not CallRecording.objects.filter(call=call).exists():
            return Response(
                {"error": "no_recording", "message": "This call has no recording."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        transcribe_call.delay(connection.schema_name, str(call.pk))
        return Response({"queued": True}, status=status.HTTP_202_ACCEPTED)


# ============================================================
# Insights
# ============================================================
class CallInsightView(_CallScopedView):
    """GET /api/v1/ai/calls/{call_id}/insight/"""

    permission_classes = [
        IsAuthenticatedAgent,
        feature_required(FeatureKey.AI_CALL_INSIGHTS),
    ]

    def get(self, request, pk):
        call = self.get_call(request, pk)
        if call is None:
            return self.not_found()
        insight = (
            CallInsight.objects
            .select_related("suggested_disposition")
            .filter(call=call)
            .first()
        )
        if insight is None:
            return Response(
                {"status": InsightStatus.PENDING, "message": "Not analysed yet."},
                status=status.HTTP_200_OK,
            )
        return Response(CallInsightSerializer(insight).data)


class CallAnalyseView(_CallScopedView):
    """POST /api/v1/ai/calls/{call_id}/analyse/ — regenerate the insight."""

    permission_classes = [
        IsAuthenticatedAgent,
        IsManagerOrAdmin,
        feature_required(FeatureKey.AI_CALL_INSIGHTS),
    ]

    def post(self, request, pk):
        call = self.get_call(request, pk)
        if call is None:
            return self.not_found()
        recording = CallRecording.objects.filter(call=call).first()
        if recording is None or not recording.transcript:
            return Response(
                {
                    "error": "no_transcript",
                    "message": "Transcribe this call before analysing it.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        analyse_call.delay(connection.schema_name, str(call.pk))
        return Response({"queued": True}, status=status.HTTP_202_ACCEPTED)


class InsightListView(ListAPIView):
    """
    GET /api/v1/ai/insights/?sentiment=negative&agent=3

    The manager's review queue: every analysed call, newest first.
    """

    permission_classes = [
        IsAuthenticatedAgent,
        feature_required(FeatureKey.AI_CALL_INSIGHTS),
    ]
    serializer_class = CallInsightSerializer
    pagination_class = InsightPagination

    def get_queryset(self):
        qs = (
            CallInsight.objects
            .select_related("call", "call__agent", "call__lead", "suggested_disposition")
            .filter(call__in=_visible_calls(self.request.user))
        )
        sentiment = self.request.query_params.get("sentiment")
        if sentiment:
            qs = qs.filter(sentiment=sentiment)
        agent_id = self.request.query_params.get("agent")
        if agent_id:
            qs = qs.filter(call__agent_id=agent_id)
        return qs.order_by("-generated_at")


# ============================================================
# Operations
# ============================================================
class BackfillView(APIView):
    """
    POST /api/v1/ai/backfill/  {"limit": 50}

    Queue transcription for recordings that predate the module. Admin only —
    it fans out to as many paid ASR calls as `limit`.
    """

    permission_classes = [
        IsAuthenticatedAgent,
        IsTenantAdmin,
        feature_required(FeatureKey.AI_CALL_TRANSCRIPTION),
    ]

    def post(self, request):
        try:
            limit = int(request.data.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, 500))
        backfill_transcripts.delay(connection.schema_name, limit)
        return Response({"queued": True, "limit": limit}, status=status.HTTP_202_ACCEPTED)


class AIUsageView(APIView):
    """
    GET /api/v1/ai/usage/

    Token spend to date, so an admin can see what the module is costing before
    the invoice does. Admin only.
    """

    permission_classes = [
        IsAuthenticatedAgent,
        IsTenantAdmin,
        feature_required(FeatureKey.AI_CALL_INSIGHTS),
    ]

    def get(self, request):
        totals = CallInsight.objects.filter(status=InsightStatus.DONE).aggregate(
            calls_analysed=Count("id"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
        )
        transcripts = CallRecording.objects.filter(transcript_status="done").aggregate(
            calls_transcribed=Count("call_id"),
            audio_seconds=Sum("duration_seconds"),
        )
        return Response({
            "calls_analysed": totals["calls_analysed"] or 0,
            "input_tokens": totals["input_tokens"] or 0,
            "output_tokens": totals["output_tokens"] or 0,
            "calls_transcribed": transcripts["calls_transcribed"] or 0,
            "audio_seconds": transcripts["audio_seconds"] or 0,
            "failed_insights": CallInsight.objects.filter(
                status=InsightStatus.FAILED
            ).count(),
        })
