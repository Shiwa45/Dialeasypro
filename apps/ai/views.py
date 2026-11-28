"""
TeleCRM Backend — apps/ai/views.py

Every view here is gated on a plan feature (402 + upsell payload when the
tenant hasn't bought the AI Suite module) and scoped so a plain agent can only
read insights for their own calls.
"""
from django.db import connection
from django.db.models import Count, F, Sum
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.constants import InsightStatus
from apps.ai.models import CallInsight
from apps.ai.serializers import CallInsightSerializer, RecordedCallSerializer, TranscriptSerializer
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
    """
    Calls this person may see — the same rule as the call log.

    Only the "agent" role used to be restricted, so HR, Accounts and Read-only
    users could open any call's transcript and AI analysis.
    """
    from apps.calls.scoping import calls_visible_to

    return calls_visible_to(agent, CallLog.objects.all())


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

    Re-runs speech-to-text. Managers and admins only — each run costs audio
    tokens, so it isn't something an agent should be able to loop on.
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
        # force: the task skips a recording that is already transcribed, so
        # "Re-transcribe" used to do nothing for exactly the calls it is for.
        transcribe_call.delay(connection.schema_name, str(call.pk), force=True)
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
        if recording is None:
            return Response(
                {"error": "no_recording", "message": "This call has no recording to analyse."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not recording.transcript:
            # The transcript failed or never ran (e.g. the Gemini model was
            # retired). Refusing here left "Re-analyse" stuck on a 400 with no
            # way out on the website, so transcribe again: the transcription
            # task queues the analysis itself when it finishes.
            transcribe_call.delay(connection.schema_name, str(call.pk), force=True)
            return Response(
                {"queued": True, "transcribing": True}, status=status.HTTP_202_ACCEPTED,
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
        # Failures and queued rows are worth finding on purpose, so let the
        # caller ask for them rather than paging the whole queue looking.
        insight_status = self.request.query_params.get("status")
        if insight_status:
            qs = qs.filter(status=insight_status)

        # Postgres sorts NULLs above everything on a DESC, so a plain
        # "-generated_at" put every not-yet-analysed row at the TOP of the
        # queue. Queue a backfill of 50 and the manager's review list opens on
        # 50 blank rows. Un-analysed rows belong at the end; the tiebreak on id
        # keeps paging stable when several land in the same second.
        return qs.order_by(F("generated_at").desc(nulls_last=True), "-id")


# ============================================================
# Recorded calls — summarised on request
# ============================================================
def _has_audio(qs):
    return qs.filter(recording__isnull=False).exclude(recording__cloud_url="", recording__file="")


class RecordedCallListView(ListAPIView):
    """
    GET /api/v1/ai/calls/?summary=none|done|failed&sentiment=&agent=&q=

    Every connected call that has a recording, newest first, each with its
    summary if one has been made. Nothing here spends AI credits: a summary
    is made only when someone presses Summarise on a call.
    """

    permission_classes = [
        IsAuthenticatedAgent,
        feature_required(FeatureKey.AI_CALL_INSIGHTS),
    ]
    serializer_class = RecordedCallSerializer
    pagination_class = InsightPagination

    def get_queryset(self):
        from django.db.models import Q

        qs = _has_audio(
            _visible_calls(self.request.user).filter(is_connected=True)
        ).select_related("agent", "lead", "recording", "insight", "insight__suggested_disposition")

        p = self.request.query_params
        summary = p.get("summary")
        if summary == "none":
            # Not summarised yet: no row, or one that never finished.
            qs = qs.filter(Q(insight__isnull=True) | Q(insight__status=InsightStatus.PENDING))
        elif summary == "done":
            qs = qs.filter(insight__status=InsightStatus.DONE)
        elif summary == "processing":
            qs = qs.filter(insight__status=InsightStatus.PROCESSING)
        elif summary == "failed":
            qs = qs.filter(insight__status__in=[InsightStatus.FAILED, InsightStatus.SKIPPED])
        sentiment = p.get("sentiment")
        if sentiment:
            qs = qs.filter(insight__status=InsightStatus.DONE, insight__sentiment=sentiment)
        if p.get("agent"):
            qs = qs.filter(agent_id=p["agent"])
        q = (p.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(lead__name__icontains=q) | Q(phone_number__icontains=q))
        return qs.order_by("-started_at", "-pk")


class CallSummariseView(_CallScopedView):
    """
    POST /api/v1/ai/calls/{call_id}/summarise/   {"force": false}

    Make the summary for this one call: transcribe the recording if needed,
    then summarise it. Anyone who can see the call may summarise it once.
    A call already summarised is answered from what is stored, at no cost;
    making it again ({"force": true}) is for managers and admins.
    """

    permission_classes = [
        IsAuthenticatedAgent,
        feature_required(FeatureKey.AI_CALL_INSIGHTS),
    ]

    # A summary still "processing" after this long is treated as stuck
    # (a worker killed mid-run) and may be started again.
    STUCK_AFTER_MINUTES = 15

    def post(self, request, pk):
        from datetime import timedelta

        from django.utils import timezone

        from apps.ai.services.gemini import is_enabled

        call = self.get_call(request, pk)
        if call is None:
            return self.not_found()
        if not call.is_connected:
            return Response(
                {"error": "not_connected", "message": "Only answered calls can be summarised."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        recording = CallRecording.objects.filter(call=call).first()
        if recording is None or not (recording.cloud_url or recording.file):
            return Response(
                {"error": "no_recording", "message": "This call has no recording to summarise."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not is_enabled():
            return Response(
                {"error": "ai_not_configured",
                 "message": "AI summaries are switched off on the server (GEMINI_API_KEY is not set)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        force = str(request.data.get("force", "")).lower() in ("1", "true", "yes")
        insight = CallInsight.objects.filter(call=call).first()

        if insight and insight.status == InsightStatus.DONE and not force:
            return Response(
                {"already_done": True, "insight": CallInsightSerializer(insight).data},
                status=status.HTTP_200_OK,
            )
        if force and request.user.role not in (AgentRole.ADMIN, AgentRole.MANAGER) \
                and not getattr(request.user, "is_superuser", False):
            return Response(
                {"error": "forbidden", "message": "Only a manager or admin can make a summary again."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if insight and insight.status == InsightStatus.PROCESSING and \
                insight.updated_at > timezone.now() - timedelta(minutes=self.STUCK_AFTER_MINUTES):
            # Already on its way — a second click must not pay twice.
            return Response({"queued": True, "already_running": True}, status=status.HTTP_202_ACCEPTED)

        needs_transcript = not (recording.transcript and recording.transcript_status == "done")
        has_feature = getattr(request, "has_feature", None)
        if needs_transcript and callable(has_feature) and not has_feature(FeatureKey.AI_CALL_TRANSCRIPTION):
            return Response(
                {"error": "feature_not_enabled",
                 "message": "Call transcription isn't part of your plan, so this recording can't be summarised."},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        if insight is None:
            insight = CallInsight(call=call)
        insight.status = InsightStatus.PROCESSING
        insight.error = ""
        insight.save()

        schema = connection.schema_name
        try:
            if not needs_transcript:
                analyse_call.delay(schema, str(call.pk))
                transcribing = False
            else:
                # Transcription hands over to the summary when it finishes.
                transcribe_call.delay(schema, str(call.pk))
                transcribing = True
        except Exception:  # noqa: BLE001 — broker unreachable
            insight.status = InsightStatus.PENDING
            insight.save(update_fields=["status", "updated_at"])
            return Response(
                {"error": "queue_unavailable", "message": "Could not start the summary. Try again in a minute."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"queued": True, "transcribing": transcribing}, status=status.HTTP_202_ACCEPTED)


# ============================================================
# Operations
# ============================================================
class BackfillView(APIView):
    """
    POST /api/v1/ai/backfill/  {"limit": 50}

    Queue transcription for recordings that predate the module. Admin only —
    it fans out to as many paid transcription calls as `limit`.
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
        from apps.ai.services.gemini import is_enabled

        waiting = CallRecording.objects.exclude(cloud_url="", file="").exclude(
            transcript_status="done"
        )
        return Response({
            # Whether the server has GEMINI_API_KEY. Without it nothing is
            # ever transcribed and the screen had no way of saying so.
            "gemini_configured": is_enabled(),
            # Recordings not yet transcribed (waiting, running or failed).
            "recordings_waiting": waiting.count(),
            "transcripts_failed": waiting.filter(transcript_status="failed").count(),
            "calls_analysed": totals["calls_analysed"] or 0,
            "input_tokens": totals["input_tokens"] or 0,
            "output_tokens": totals["output_tokens"] or 0,
            "calls_transcribed": transcripts["calls_transcribed"] or 0,
            "audio_seconds": transcripts["audio_seconds"] or 0,
            "failed_insights": CallInsight.objects.filter(
                status=InsightStatus.FAILED
            ).count(),
        })
