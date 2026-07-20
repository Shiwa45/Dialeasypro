"""
TeleCRM Backend — apps/calls/views.py

DRF API views for call management.

CallLogListCreateView    GET/POST  /api/v1/calls/
CallLogDetailView        GET       /api/v1/calls/{id}/
ClickToCallView          POST      /api/v1/calls/click-to-call/
CallDispositionListView  GET       /api/v1/calls/dispositions/
CallProviderWebhookView  POST      /api/v1/calls/webhook/{provider}/
CallStatsView            GET       /api/v1/calls/stats/
"""
import logging

from django.db import connection
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import (
    HasFeatureAccess,
    IsActiveAgent,
    IsAuthenticatedAgent,
    IsManagerOrAdmin,
)
from apps.calls.models import CallDisposition, CallLog, CallRecording
from apps.calls.serializers import (
    CallDispositionSerializer,
    CallLogCreateSerializer,
    CallLogSerializer,
    ClickToCallSerializer,
)
from apps.core.constants import AgentRole, FeatureKey, LeadStatus
from apps.core.pagination import StandardResultsSetPagination
from apps.leads.models import Lead, LeadActivity

logger = logging.getLogger(__name__)


class CallLogListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/calls/     → Paginated call log (filterable by date, agent, lead)
    POST /api/v1/calls/     → Log a manual call
    """

    permission_classes = [IsAuthenticatedAgent]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        return CallLogCreateSerializer if self.request.method == "POST" else CallLogSerializer

    def get_queryset(self):
        agent = self.request.user
        qs = CallLog.objects.select_related(
            "agent", "lead", "disposition", "recording"
        ).order_by("-started_at")

        # Role-based scoping
        if agent.role == AgentRole.AGENT:
            qs = qs.filter(agent=agent)

        params = self.request.query_params
        if lead_id := params.get("lead"):
            qs = qs.filter(lead_id=lead_id)
        if agent_id := params.get("agent"):
            qs = qs.filter(agent_id=agent_id)
        if date_from := params.get("date_from"):
            qs = qs.filter(started_at__date__gte=date_from)
        if date_to := params.get("date_to"):
            qs = qs.filter(started_at__date__lte=date_to)
        if connected := params.get("connected"):
            qs = qs.filter(is_connected=connected.lower() == "true")
        if direction := params.get("direction"):
            qs = qs.filter(direction=direction)

        return qs

    def perform_create(self, serializer):
        call = serializer.save(agent=self.request.user)
        # Update lead's last_contacted_at and contact_count
        if call.lead:
            call.lead.log_contact(contact_type="call")
            # A dialed lead is now "worked" — it must never be served again as a
            # fresh/new lead, and the queue lock it was pulled under is released.
            lead = call.lead
            lead.has_been_worked = True
            lead.last_dialed_at = timezone.now()
            lead.locked_by = None
            lead.locked_at = None
            lead.lock_expires_at = None
            lead.locked_queue = None
            # Auto-advance status: new → attempted so the lead is never
            # treated as untouched again. Only advance from "new" — we must
            # never downgrade a lead that's already at a later stage.
            update_fields = [
                "has_been_worked", "last_dialed_at",
                "locked_by", "locked_at", "lock_expires_at", "locked_queue",
            ]
            if lead.status == LeadStatus.NEW:
                lead.status = LeadStatus.ATTEMPTED
                update_fields.append("status")
            lead.save(update_fields=update_fields)
            # Log in lead activity feed
            LeadActivity.objects.create(
                lead=call.lead,
                activity_type="call",
                description=(
                    f"Call {'connected' if call.is_connected else 'not connected'} "
                    f"— {call.duration_display}"
                    + (f". {call.notes}" if call.notes else "")
                ),
                performed_by=self.request.user,
                meta={"call_id": str(call.id), "duration": call.duration_seconds},
            )


class CallLogDetailView(generics.RetrieveAPIView):
    """GET /api/v1/calls/{id}/ — Call detail with recording."""

    permission_classes = [IsAuthenticatedAgent]
    serializer_class = CallLogSerializer

    def get_queryset(self):
        agent = self.request.user
        qs = CallLog.objects.select_related("agent", "lead", "disposition", "recording")
        if agent.role == AgentRole.AGENT:
            qs = qs.filter(agent=agent)
        return qs


def _queue_ai_pipeline(call) -> None:
    """
    Kick off transcription (which chains into insights) for a freshly uploaded
    recording. The task no-ops for tenants without the AI Suite module, so
    there's nothing to check here.

    A broker that's down must never fail the upload — the recording is already
    stored, and `POST /api/v1/ai/backfill/` can pick it up later.
    """
    from apps.ai.tasks import transcribe_call

    try:
        transcribe_call.delay(connection.schema_name, str(call.pk))
    except Exception as exc:  # noqa: BLE001 — broker unreachable, etc.
        logger.warning("Could not queue AI pipeline for call %s: %s", call.pk, exc)


class CallRecordingUploadView(APIView):
    """
    POST /api/v1/calls/{id}/recording/   (multipart/form-data)

    The mobile app uploads the on-device OEM call-recording audio file it
    matched to this call. The file is pushed to Cloudinary and linked to the
    CallLog. Idempotent: re-uploading the same call overwrites (no duplicates).

    Form fields:
      file            — the audio file (required)
      duration_seconds (optional)
      source_filename  (optional) original device filename
      matched_by       (optional) filename_number | timestamp | manual
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.CALL_RECORDING_ACCESS
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    # Reject anything that isn't plausibly a call recording.
    MAX_BYTES = 100 * 1024 * 1024  # 100 MB
    ALLOWED_EXT = {"mp3", "m4a", "amr", "wav", "ogg", "aac", "3gp", "mp4"}

    def post(self, request, pk):
        agent = request.user

        # Only the owning agent (or a manager/admin) may attach a recording.
        try:
            qs = CallLog.objects.all()
            if agent.role == AgentRole.AGENT:
                qs = qs.filter(agent=agent)
            call = qs.get(pk=pk)
        except CallLog.DoesNotExist:
            return Response(
                {"error": "not_found", "message": "Call not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ---- Mode A: app already uploaded to Cloudinary, just link the URL ----
        client_cloud_url = (request.data.get("cloud_url") or "").strip()
        if client_cloud_url:
            existing = CallRecording.objects.filter(call=call).first()
            if existing and existing.cloud_url:
                return Response(
                    {"id": existing.pk, "already_uploaded": True, "playback_url": existing.cloud_url},
                    status=status.HTTP_200_OK,
                )
            try:
                duration = int(request.data.get("duration_seconds") or 0)
            except (TypeError, ValueError):
                duration = 0
            rec, _ = CallRecording.objects.update_or_create(
                call=call,
                defaults={
                    "cloud_url": client_cloud_url,
                    "cloud_public_id": (request.data.get("cloud_public_id") or "")[:300],
                    "duration_seconds": duration,
                    "format": (request.data.get("format") or "m4a")[:10],
                    "source_filename": (request.data.get("source_filename") or "")[:400],
                    "matched_by": (request.data.get("matched_by") or "filename_number")[:20],
                    "uploaded_at": timezone.now(),
                },
            )
            _queue_ai_pipeline(call)
            return Response(
                {"id": rec.pk, "playback_url": rec.cloud_url, "duration_seconds": rec.duration_seconds},
                status=status.HTTP_201_CREATED,
            )

        # ---- Mode B: app sends the raw file; backend uploads to Cloudinary ----
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"error": "file_required", "message": "Provide an audio file or a cloud_url."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if upload.size > self.MAX_BYTES:
            return Response(
                {"error": "file_too_large", "message": "Recording exceeds 100 MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ext = (upload.name.rsplit(".", 1)[-1] if "." in upload.name else "").lower()
        if ext and ext not in self.ALLOWED_EXT:
            return Response(
                {"error": "invalid_format", "message": f"Unsupported audio format: .{ext}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Idempotency: if this call already has a recording, don't re-upload.
        existing = CallRecording.objects.filter(call=call).first()
        if existing and existing.cloud_url:
            return Response(
                {
                    "id": existing.pk,
                    "already_uploaded": True,
                    "playback_url": existing.cloud_url,
                },
                status=status.HTTP_200_OK,
            )

        from apps.core.cloudinary_utils import upload_call_recording

        public_id = f"call_{call.pk}"
        result = upload_call_recording(
            upload,
            tenant_schema=connection.schema_name,
            public_id=public_id,
        )
        if not result:
            # Local-media fallback: Cloudinary isn't configured (or the upload
            # failed) — store the file on the server's media volume instead so
            # recordings still work with zero external configuration.
            result = self._store_locally(request, upload, ext or "m4a", call)
        if not result:
            return Response(
                {
                    "error": "upload_failed",
                    "message": "Recording storage is not configured or upload failed.",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            duration = int(request.data.get("duration_seconds") or result.get("duration") or 0)
        except (TypeError, ValueError):
            duration = result.get("duration") or 0

        rec, _ = CallRecording.objects.update_or_create(
            call=call,
            defaults={
                "cloud_url": result["url"],
                "cloud_public_id": result["public_id"],
                "file_size_bytes": result.get("bytes", upload.size),
                "duration_seconds": duration,
                "format": (result.get("format") or ext or "m4a")[:10],
                "source_filename": (request.data.get("source_filename") or upload.name)[:400],
                "matched_by": (request.data.get("matched_by") or "manual")[:20],
                "uploaded_at": timezone.now(),
            },
        )
        _queue_ai_pipeline(call)

        return Response(
            {
                "id": rec.pk,
                "playback_url": rec.cloud_url,
                "duration_seconds": rec.duration_seconds,
            },
            status=status.HTTP_201_CREATED,
        )

    def _store_locally(self, request, upload, ext: str, call) -> dict | None:
        """Save the recording under MEDIA_ROOT and return Cloudinary-shaped metadata."""
        try:
            from django.conf import settings
            from django.core.files.storage import default_storage

            rel_path = f"call_recordings/{connection.schema_name}/call_{call.pk}.{ext}"
            if default_storage.exists(rel_path):
                default_storage.delete(rel_path)
            saved = default_storage.save(rel_path, upload)
            url = request.build_absolute_uri(settings.MEDIA_URL + saved)
            return {
                "url": url,
                "public_id": f"local:{saved}",
                "bytes": upload.size,
                "duration": 0,
                "format": ext,
            }
        except Exception as exc:
            logger.error(f"[Recording] Local storage fallback failed: {exc}")
            return None


class ClickToCallView(APIView):
    """
    POST /api/v1/calls/click-to-call/
    Initiate a click-to-call via the configured telecom provider.

    The provider dials the agent first, then connects to the lead.
    Creates a CallLog record immediately in 'initiated' state.
    The provider's webhook updates it with actual duration/status.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.CLOUD_TELEPHONY

    def post(self, request):
        serializer = ClickToCallSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        lead_id = serializer.validated_data["lead_id"]
        try:
            lead = Lead.objects.get(pk=lead_id, is_deleted=False)
        except Lead.DoesNotExist:
            return Response({"error": "lead_not_found"}, status=404)

        phone = serializer.validated_data.get("phone_number") or lead.phone
        agent = request.user

        # Create CallLog in initiated state
        call = CallLog.objects.create(
            agent=agent,
            lead=lead,
            direction="outbound",
            phone_number=phone,
        )

        # Mark the lead as worked & advance status (same as manual call logging)
        lead.log_contact(contact_type="call")
        update_fields = ["has_been_worked", "last_dialed_at"]
        lead.has_been_worked = True
        lead.last_dialed_at = timezone.now()
        if lead.status == LeadStatus.NEW:
            lead.status = LeadStatus.ATTEMPTED
            update_fields.append("status")
        lead.save(update_fields=update_fields)

        # Attempt provider call
        try:
            result = _initiate_provider_call(agent, phone, call)
            call.provider = result.get("provider", "other")
            call.provider_call_id = result.get("call_id", "")
            call.save(update_fields=["provider", "provider_call_id"])

            return Response({
                "call_id": str(call.id),
                "status": "initiated",
                "message": "Call initiated. Your phone will ring first.",
                "provider_call_id": result.get("call_id"),
            })
        except Exception as exc:
            logger.error(f"[Click-to-call] Failed: {exc}")
            call.delete()
            return Response(
                {"error": "call_failed", "message": "Could not initiate call. Check integration settings."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


def _initiate_provider_call(agent, phone: str, call: CallLog) -> dict:
    """
    Initiate call via configured telecom provider.
    Returns dict with provider name and call_id.
    Placeholder — real implementation wires to Exotel/MCUBE API.
    """
    from apps.superadmin.models import GlobalSettings

    # Determine which provider is configured for this tenant
    # In production, tenant settings will have the provider config
    provider = GlobalSettings.get("default_call_provider", "manual")

    if provider == "exotel":
        return _call_via_exotel(agent.phone, phone)
    elif provider == "mcube":
        return _call_via_mcube(agent.phone, phone)
    else:
        # Manual mode — just log it, no actual dial
        return {"provider": "manual", "call_id": f"manual_{call.id}"}


def _call_via_exotel(agent_phone: str, lead_phone: str) -> dict:
    """Exotel click-to-call API. Implement when Exotel credentials are configured."""
    raise NotImplementedError("Exotel integration not configured")


def _call_via_mcube(agent_phone: str, lead_phone: str) -> dict:
    """MCUBE click-to-call API. Implement when MCUBE credentials are configured."""
    raise NotImplementedError("MCUBE integration not configured")


class CallDispositionListView(generics.ListAPIView):
    """GET /api/v1/calls/dispositions/ — Available call dispositions."""

    permission_classes = [IsAuthenticatedAgent]
    serializer_class = CallDispositionSerializer
    queryset = CallDisposition.objects.filter(is_active=True).order_by("sort_order")
    pagination_class = None  # Return all dispositions (short list)


class CallProviderWebhookView(APIView):
    """
    POST /api/v1/calls/webhook/{provider}/
    Receives real-time call events from telecom providers.
    Updates CallLog with actual duration, status, recording URL.
    """

    permission_classes = [AllowAny]  # Validated via provider-specific signature

    def post(self, request, provider):
        payload = request.data
        logger.info(f"[Webhook] Call event from {provider}: {list(payload.keys())}")

        handlers = {
            "exotel": self._handle_exotel,
            "mcube": self._handle_mcube,
            "knowlarity": self._handle_knowlarity,
        }

        handler = handlers.get(provider)
        if not handler:
            return Response({"error": "unknown_provider"}, status=400)

        try:
            handler(payload)
        except Exception as exc:
            logger.error(f"[Webhook] {provider} handler error: {exc}", exc_info=True)

        return Response({"status": "ok"})

    def _handle_exotel(self, payload: dict):
        """Process Exotel call status webhook."""
        call_sid = payload.get("CallSid")
        status_str = payload.get("Status")  # "completed", "failed", "busy", "no-answer"
        duration = int(payload.get("Duration", 0))

        try:
            call = CallLog.objects.get(provider_call_id=call_sid)
        except CallLog.DoesNotExist:
            logger.warning(f"[Exotel] CallLog not found for SID: {call_sid}")
            return

        call.duration_seconds = duration
        call.is_connected = status_str == "completed"
        call.provider_meta = payload
        if payload.get("EndTime"):
            from django.utils.dateparse import parse_datetime
            call.ended_at = parse_datetime(payload["EndTime"])
        call.save(update_fields=["duration_seconds", "is_connected", "provider_meta", "ended_at"])

        # Queue recording download if available
        if recording_url := payload.get("RecordingUrl"):
            from apps.calls.tasks import download_call_recording
            from django.db import connection
            download_call_recording.apply_async(
                args=[connection.schema_name, str(call.id), recording_url],
                queue="call_uploads",
            )

    def _handle_mcube(self, payload: dict):
        """Process MCUBE call event webhook."""
        # MCUBE sends different field names — map them
        call_id = payload.get("uniqueid") or payload.get("callid")
        duration = int(payload.get("duration", 0))
        status_str = payload.get("disposition", "")

        try:
            call = CallLog.objects.get(provider_call_id=call_id)
        except CallLog.DoesNotExist:
            return

        call.duration_seconds = duration
        call.is_connected = status_str == "ANSWERED"
        call.provider_meta = payload
        call.save(update_fields=["duration_seconds", "is_connected", "provider_meta"])

    def _handle_knowlarity(self, payload: dict):
        """Process Knowlarity webhook — placeholder."""
        pass


class CallStatsView(APIView):
    """
    GET /api/v1/calls/stats/
    Call analytics for the dashboard and reports.
    """

    permission_classes = [IsAuthenticatedAgent]

    def get(self, request):
        agent = request.user
        params = request.query_params
        date_from = params.get("date_from")
        date_to = params.get("date_to")

        qs = CallLog.objects.all()
        if agent.role == AgentRole.AGENT:
            qs = qs.filter(agent=agent)
        if date_from:
            qs = qs.filter(started_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(started_at__date__lte=date_to)

        today = timezone.now().date()
        today_qs = qs.filter(started_at__date=today)

        stats = qs.aggregate(
            total_calls=Count("id"),
            connected_calls=Count("id", filter=Q(is_connected=True)),
            total_duration=Sum("duration_seconds"),
            avg_duration=Avg("duration_seconds", filter=Q(is_connected=True)),
            total_cost_paise=Sum("call_cost_paise"),
        )

        return Response({
            "today": {
                "total": today_qs.count(),
                "connected": today_qs.filter(is_connected=True).count(),
                "total_duration_seconds": today_qs.filter(is_connected=True)
                    .aggregate(s=Sum("duration_seconds"))["s"] or 0,
            },
            "period": {
                "total_calls": stats["total_calls"] or 0,
                "connected_calls": stats["connected_calls"] or 0,
                "connection_rate": round(
                    (stats["connected_calls"] or 0) / (stats["total_calls"] or 1) * 100, 1
                ),
                "total_duration_seconds": stats["total_duration"] or 0,
                "avg_duration_seconds": round(stats["avg_duration"] or 0),
                "total_cost_rupees": (stats["total_cost_paise"] or 0) / 100,
            },
            "by_disposition": list(
                qs.filter(disposition__isnull=False)
                .values("disposition__name")
                .annotate(count=Count("id"))
                .order_by("-count")
            ),
        })
