"""
TeleCRM Backend — apps/communications/views.py

DRF API views for all communication channels.

WhatsAppTemplateListView     GET/POST  /api/v1/comms/whatsapp/templates/
WhatsAppMessageListView      GET       /api/v1/comms/whatsapp/messages/?lead={id}
SendWhatsAppView             POST      /api/v1/comms/whatsapp/send/
SendSMSView                  POST      /api/v1/comms/sms/send/
BulkCampaignListCreateView   GET/POST  /api/v1/comms/campaigns/
BulkCampaignDetailView       GET       /api/v1/comms/campaigns/{id}/
BulkCampaignLaunchView       POST      /api/v1/comms/campaigns/{id}/launch/
BulkCampaignPauseView        POST      /api/v1/comms/campaigns/{id}/pause/
WhatsAppWebhookView          POST      /api/v1/comms/webhook/whatsapp/{provider}/
"""
import logging

from django.db import connection
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import (
    IsActiveAgent, IsAuthenticatedAgent, IsManagerOrAdmin, IsTenantAdmin, feature_required,
)
from apps.communications.models import BulkCampaign, WhatsAppMessage, WhatsAppTemplate
from apps.communications.serializers import (
    BulkCampaignCreateSerializer, BulkCampaignSerializer,
    SendSMSSerializer, SendWhatsAppSerializer,
    WhatsAppMessageSerializer, WhatsAppTemplateSerializer,
)
from apps.core.constants import FeatureKey
from apps.core.pagination import StandardResultsSetPagination
from apps.superadmin.models import AuditLog
from apps.core.constants import AuditAction

logger = logging.getLogger(__name__)


class WhatsAppTemplateListView(generics.ListCreateAPIView):
    """
    GET  /api/v1/comms/whatsapp/templates/  → List approved templates
    POST /api/v1/comms/whatsapp/templates/  → Create new template (admin)
    """

    serializer_class = WhatsAppTemplateSerializer
    pagination_class = None  # Templates are a small, finite list; return plain array

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsTenantAdmin()]
        return [IsAuthenticatedAgent()]

    def get_queryset(self):
        qs = WhatsAppTemplate.objects.filter(is_active=True)
        if self.request.query_params.get("approved_only"):
            qs = qs.filter(status="approved")
        return qs.order_by("name")


class TemplateMediaUploadView(APIView):
    """
    POST /api/v1/comms/template-media/   (multipart: file)
    Upload an image for a template header (or one-click image message) to
    Cloudinary and return its URL. Tenant-admin only.
    """

    permission_classes = [IsTenantAdmin]
    parser_classes = [MultiPartParser, FormParser]

    MAX_BYTES = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXT = {"jpg", "jpeg", "png", "gif", "webp"}

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"error": "file_required", "message": "No image provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size > self.MAX_BYTES:
            return Response(
                {"error": "file_too_large", "message": "Image exceeds 10 MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ext = (upload.name.rsplit(".", 1)[-1] if "." in upload.name else "").lower()
        if ext and ext not in self.ALLOWED_EXT:
            return Response(
                {"error": "invalid_format", "message": f"Unsupported image type: .{ext}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.core.cloudinary_utils import upload_image
        result = upload_image(upload, tenant_schema=connection.schema_name)
        if not result:
            return Response(
                {"error": "upload_failed", "message": "Image storage is not configured or upload failed."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            {"url": result["url"], "public_id": result["public_id"]},
            status=status.HTTP_201_CREATED,
        )


class WhatsAppMessageListView(generics.ListAPIView):
    """
    GET /api/v1/comms/whatsapp/messages/?lead={id}
    WhatsApp conversation thread for a lead.
    """

    permission_classes = [IsAuthenticatedAgent]
    serializer_class = WhatsAppMessageSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = WhatsAppMessage.objects.select_related("sent_by", "template")
        if lead_id := self.request.query_params.get("lead"):
            qs = qs.filter(lead_id=lead_id)
        return qs.order_by("created_at")


class SendWhatsAppView(APIView):
    """
    POST /api/v1/comms/whatsapp/send/
    Send a single WhatsApp message to a lead.
    Queues as Celery task for reliable delivery.
    """

    permission_classes = [IsAuthenticatedAgent]

    def post(self, request):
        serializer = SendWhatsAppSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from apps.communications.tasks import send_single_whatsapp
        from apps.leads.models import Lead

        lead_id = serializer.validated_data["lead_id"]
        try:
            lead = Lead.objects.get(pk=lead_id, is_deleted=False)
        except Lead.DoesNotExist:
            return Response({"error": "lead_not_found"}, status=404)

        send_single_whatsapp.apply_async(
            kwargs={
                "schema_name": connection.schema_name,
                "lead_id": lead_id,
                "message": serializer.validated_data.get("message", ""),
                "template_id": serializer.validated_data.get("template_id"),
                "sent_by_id": request.user.pk,
            },
            queue="notifications",
        )

        return Response({"message": "WhatsApp message queued.", "lead": lead.name})


class SendSMSView(APIView):
    """POST /api/v1/comms/sms/send/ — Send a single SMS to a lead."""

    permission_classes = [IsAuthenticatedAgent]

    def post(self, request):
        serializer = SendSMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from apps.communications.tasks import send_single_sms
        from apps.leads.models import Lead

        lead_id = serializer.validated_data["lead_id"]
        try:
            lead = Lead.objects.get(pk=lead_id, is_deleted=False)
        except Lead.DoesNotExist:
            return Response({"error": "lead_not_found"}, status=404)

        if lead.is_dnd:
            return Response(
                {"error": "dnd_blocked", "message": "This number is DND-registered."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        send_single_sms.apply_async(
            kwargs={
                "schema_name": connection.schema_name,
                "lead_id": lead_id,
                "message": serializer.validated_data["message"],
                "sender_id": serializer.validated_data.get("sender_id", ""),
                "sent_by_id": request.user.pk,
            },
            queue="notifications",
        )

        return Response({"message": "SMS queued.", "lead": lead.name})


class BulkCampaignListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/comms/campaigns/  → List campaigns
    POST /api/v1/comms/campaigns/  → Create draft campaign
    """

    permission_classes = [IsManagerOrAdmin]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        return BulkCampaignCreateSerializer if self.request.method == "POST" else BulkCampaignSerializer

    def get_queryset(self):
        qs = BulkCampaign.objects.select_related("created_by", "template").order_by("-created_at")
        if channel := self.request.query_params.get("channel"):
            qs = qs.filter(channel=channel)
        if status_filter := self.request.query_params.get("status"):
            qs = qs.filter(status=status_filter)
        return qs

    def perform_create(self, serializer):
        campaign = serializer.save(created_by=self.request.user)
        # Estimate recipient count
        from apps.communications.tasks import _resolve_campaign_audience
        audience = _resolve_campaign_audience(campaign)
        campaign.estimated_recipients = len(audience)
        campaign.save(update_fields=["estimated_recipients"])

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_type="agent",
            actor_id=self.request.user.pk,
            actor_email=self.request.user.email,
            entity_type="BulkCampaign",
            entity_id=campaign.id,
            entity_repr=campaign.name,
            request=self.request,
        )


class BulkCampaignDetailView(generics.RetrieveAPIView):
    """GET /api/v1/comms/campaigns/{id}/ — Campaign detail with live stats."""

    permission_classes = [IsManagerOrAdmin]
    serializer_class = BulkCampaignSerializer

    def get_queryset(self):
        return BulkCampaign.objects.all()


class BulkCampaignLaunchView(APIView):
    """POST /api/v1/comms/campaigns/{id}/launch/ — Start sending a campaign."""

    permission_classes = [IsManagerOrAdmin]

    def post(self, request, pk):
        try:
            campaign = BulkCampaign.objects.get(pk=pk, status__in=["draft", "scheduled", "paused"])
        except BulkCampaign.DoesNotExist:
            return Response({"error": "campaign_not_found_or_not_launchable"}, status=404)

        from apps.communications import tasks as comm_tasks

        CAMPAIGN_TASK_MAP = {
            "whatsapp": comm_tasks.send_bulk_whatsapp_campaign,
            "email": comm_tasks.send_bulk_email_campaign,
            "sms": comm_tasks.send_bulk_sms_campaign,
        }
        task_fn = CAMPAIGN_TASK_MAP.get(campaign.channel)
        if not task_fn:
            return Response({"error": "unsupported_channel"}, status=400)

        result = task_fn.apply_async(
            args=[connection.schema_name, str(campaign.id)],
            queue="bulk_ops",
        )
        campaign.celery_task_id = result.id
        campaign.status = "running"
        campaign.save(update_fields=["celery_task_id", "status"])

        AuditLog.log(
            action=AuditAction.BULK_ACTION,
            actor_type="agent",
            actor_id=request.user.pk,
            actor_email=request.user.email,
            entity_type="BulkCampaign",
            entity_id=campaign.id,
            entity_repr=f"Launched: {campaign.name}",
            request=request,
        )

        return Response({"message": f"Campaign '{campaign.name}' launched.", "id": str(campaign.id)})


class BulkCampaignPauseView(APIView):
    """POST /api/v1/comms/campaigns/{id}/pause/ — Pause a running campaign."""

    permission_classes = [IsManagerOrAdmin]

    def post(self, request, pk):
        try:
            campaign = BulkCampaign.objects.get(pk=pk, status="running")
        except BulkCampaign.DoesNotExist:
            return Response({"error": "campaign_not_running"}, status=400)

        # Revoke the celery task if it's still running
        if campaign.celery_task_id:
            from config.celery import app as celery_app
            celery_app.control.revoke(campaign.celery_task_id, terminate=True)

        campaign.status = "paused"
        campaign.save(update_fields=["status"])
        return Response({"message": "Campaign paused."})


class WhatsAppWebhookView(APIView):
    """
    POST /api/v1/comms/webhook/whatsapp/{provider}/
    Receives delivery status updates and inbound messages from WhatsApp providers.
    Updates WhatsAppMessage status and creates inbound message records.
    """

    permission_classes = [AllowAny]

    def post(self, request, provider):
        payload = request.data
        logger.info(f"[WA Webhook] Event from {provider}: {list(payload.keys())}")

        try:
            if provider == "interakt":
                self._handle_interakt(payload)
            elif provider in ["aisensy", "wati", "gupshup"]:
                self._handle_generic(payload, provider)
        except Exception as exc:
            logger.error(f"[WA Webhook] Handler error ({provider}): {exc}", exc_info=True)

        return Response({"status": "ok"})

    def _handle_interakt(self, payload: dict):
        """Process Interakt webhook — status updates and inbound messages."""
        event_type = payload.get("type")
        data = payload.get("data", {})

        if event_type == "message_status":
            # Delivery status update
            msg_id = data.get("message_id", "")
            new_status = data.get("status", "")  # sent, delivered, read, failed
            if msg_id and new_status:
                from django.utils import timezone as tz
                update = {"status": new_status}
                if new_status == "delivered":
                    update["delivered_at"] = tz.now()
                elif new_status == "read":
                    update["read_at"] = tz.now()
                WhatsAppMessage.objects.filter(
                    provider_message_id=msg_id
                ).update(**update)

        elif event_type == "inbound_message":
            # Inbound message from lead
            phone = data.get("customer_phone_number", "")
            content = data.get("message", {}).get("text", {}).get("body", "")
            if not phone or not content:
                return

            from apps.leads.models import Lead
            try:
                phone_normalized = f"+91{phone}" if not phone.startswith("+") else phone
                lead = Lead.objects.get(phone=phone_normalized, is_deleted=False)
                msg = WhatsAppMessage.objects.create(
                    lead=lead, direction="inbound",
                    message_type="text", content=content,
                    provider="interakt", status="received",
                    provider_message_id=data.get("wa_message_id", ""),
                )
                # Notify the assigned agent via WebSocket
                if lead.assigned_to_id:
                    from apps.core.consumers import send_agent_notification
                    from django.db import connection
                    send_agent_notification(
                        schema_name=connection.schema_name,
                        agent_id=lead.assigned_to_id,
                        event_type="message_received",
                        data={
                            "lead_id": lead.pk,
                            "lead_name": lead.name,
                            "channel": "whatsapp",
                            "message_preview": content[:100],
                        },
                    )
                # Update lead activity
                from apps.leads.models import LeadActivity
                LeadActivity.objects.create(
                    lead=lead, activity_type="whatsapp",
                    description=f"WhatsApp reply received: {content[:100]}",
                )
            except Lead.DoesNotExist:
                logger.debug(f"[WA Webhook] Inbound from unknown number {phone}")

    def _handle_generic(self, payload: dict, provider: str):
        """Generic handler for other providers."""
        logger.info(f"[WA Webhook] Generic handler for {provider} — implement if needed")
