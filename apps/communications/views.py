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
WhatsAppVerifyTokenView      POST      /api/v1/comms/whatsapp/webhook-token/
WhatsAppConversationListView GET       /api/v1/comms/whatsapp/conversations/?lead={id}
"""
import logging

from django.db import connection
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import (
    IsNotReadOnly,
    HasFeatureAccess, IsActiveAgent, IsAuthenticatedAgent, IsManagerOrAdmin,
    IsTenantAdmin, feature_required, require_channel_feature,
)
from apps.communications.models import (
    BulkCampaign, WhatsAppConfig, WhatsAppConversation, WhatsAppMessage,
    WhatsAppTemplate,
)
from apps.communications.serializers import (
    BulkCampaignCreateSerializer, BulkCampaignSerializer,
    SendSMSSerializer, SendWhatsAppSerializer,
    WhatsAppConfigSerializer, WhatsAppConversationSerializer,
    WhatsAppMessageSerializer, WhatsAppTemplateSerializer,
)
from apps.core.constants import AgentRole, FeatureKey
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
        from django.db.models import Q

        qs = WhatsAppTemplate.objects.filter(is_active=True).select_related("account")
        if self.request.query_params.get("approved_only"):
            qs = qs.filter(status="approved")
        # ?account=<id>: templates that number can send — its own and the
        # shared ones.
        if account := self.request.query_params.get("account"):
            sender = WhatsAppConfig.objects.filter(pk=account).first() if str(account).isdigit() else None
            if sender is not None:
                # Its own templates, those of other numbers in the same
                # WhatsApp Business Account, and the shared ones.
                qs = qs.filter(Q(account__in=sender.same_business_account()) | Q(account__isnull=True))
        return qs.order_by("name")


class WhatsAppTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/v1/comms/whatsapp/templates/{id}/

    Templates could be created and never touched again. In particular nothing
    could mark one APPROVED, and a bulk campaign only accepts approved
    templates — so every template a tenant wrote sat at "pending" forever and
    the campaign form's template list was permanently empty.

    Approval happens in Meta's Business Manager or the provider's console, not
    here; this is where an admin records the answer they were given.

    DELETE deactivates rather than removes: campaigns and sent messages point
    at the template, and deleting one would take the record of what was sent
    with it.
    """

    serializer_class = WhatsAppTemplateSerializer

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT", "DELETE"):
            return [IsTenantAdmin()]
        return [IsAuthenticatedAgent()]

    def get_queryset(self):
        return WhatsAppTemplate.objects.all()

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])


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
        # Only threads on leads this person may see. `?lead=` was not checked
        # at all, and with no `lead` the endpoint returned every WhatsApp
        # message in the tenant.
        from apps.leads.views import leads_visible_to

        qs = WhatsAppMessage.objects.select_related("sent_by", "template").filter(
            lead__in=leads_visible_to(self.request.user)
        )
        if lead_id := self.request.query_params.get("lead"):
            qs = qs.filter(lead_id=lead_id)
        return qs.order_by("created_at")


class SendWhatsAppView(APIView):
    """
    POST /api/v1/comms/whatsapp/send/
    Send a single WhatsApp message to a lead.
    Queues as Celery task for reliable delivery.
    Plan-gated on ONE_CLICK_WHATSAPP.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, IsNotReadOnly]
    required_feature = FeatureKey.ONE_CLICK_WHATSAPP

    def post(self, request):
        serializer = SendWhatsAppSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from apps.communications.tasks import send_single_whatsapp
        from apps.leads.models import Lead

        lead_id = serializer.validated_data["lead_id"]
        # Only a lead this agent may see; the lookup was unscoped.
        from apps.leads.views import leads_visible_to

        lead = leads_visible_to(request.user).filter(pk=lead_id).first()
        if lead is None:
            return Response({"error": "lead_not_found"}, status=404)

        # Only a template the provider will accept. The app offered pending,
        # rejected and switched-off ones too; the send then failed at the
        # provider with nothing but "Send failed" on the phone.
        template_id = serializer.validated_data.get("template_id")
        if template_id is not None:
            from apps.communications.models import WhatsAppTemplate

            template = WhatsAppTemplate.objects.filter(pk=template_id).first()
            if template is None or not template.is_active or template.status != "approved":
                return Response(
                    {"error": "template_not_usable",
                     "message": "That template is not an active, approved template."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        from apps.communications.whatsapp_accounts import resolve_sender
        from apps.communications.whatsapp_ready import (
            NOT_CONNECTED, mock_allowed, unmapped_placeholders, whatsapp_connected,
        )

        account_id = serializer.validated_data.get("account_id")
        sender = resolve_sender(
            account_id=account_id, template=template if template_id is not None else None, lead=lead,
        )
        if sender.error:
            return Response(
                {"error": "sender_not_usable", "message": sender.error},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not whatsapp_connected(sender.account) and not mock_allowed():
            if account_id not in (None, "") and sender.account is not None:
                return Response(
                    {"error": "whatsapp_not_connected",
                     "message": f'"{sender.account.label}" isn\'t connected yet. '
                                "Send it a test message in Settings → WhatsApp, or pick another number."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(NOT_CONNECTED, status=status.HTTP_400_BAD_REQUEST)
        if template_id and serializer.validated_data.get("variables") is None:
            missing = unmapped_placeholders(template)
            if missing:
                return Response(
                    {"error": "template_variables_unmapped",
                     "message": "This template's variables aren't mapped to lead fields yet: "
                                + ", ".join("{{%d}}" % n for n in missing)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        send_single_whatsapp.apply_async(
            kwargs={
                "schema_name": connection.schema_name,
                "lead_id": lead_id,
                "message": serializer.validated_data.get("message", ""),
                "template_id": template_id,
                "sent_by_id": request.user.pk,
                "variables": serializer.validated_data.get("variables"),
                # The resolved sender, so the message goes out from the number
                # the agent was shown even if the lead writes in meanwhile.
                "account_id": sender.account.pk if sender.account is not None else None,
            },
            queue="notifications",
        )

        return Response({
            "message": "WhatsApp message queued.", "lead": lead.name,
            "sent_from": sender.account.sender_label if sender.account is not None else None,
        })


class LogNativeWhatsAppView(APIView):
    """
    POST /api/v1/comms/whatsapp/log-native/  {"lead_id", "message"}

    The app opened the phone's own WhatsApp for this lead. That left no
    trace in the CRM, so a manager could not see the contact happened. The
    app cannot know whether the agent then pressed Send inside WhatsApp, so
    this records exactly what is known: WhatsApp was opened, with this text.
    """

    permission_classes = [IsAuthenticatedAgent, IsNotReadOnly]

    def post(self, request):
        from apps.leads.models import LeadActivity
        from apps.leads.views import leads_visible_to

        try:
            lead_id = int(request.data.get("lead_id"))
        except (TypeError, ValueError):
            return Response({"error": "lead_id_required"}, status=400)
        lead = leads_visible_to(request.user).filter(pk=lead_id).first()
        if lead is None:
            return Response({"error": "lead_not_found"}, status=404)

        message = (request.data.get("message") or "").strip()
        LeadActivity.objects.create(
            lead=lead,
            activity_type="whatsapp",
            performed_by=request.user,
            description=(
                f"WhatsApp opened from the app: {message[:200]}" if message
                else "WhatsApp opened from the app"
            ),
        )
        lead.log_contact(contact_type="whatsapp")
        return Response({"logged": True}, status=201)


class SendSMSView(APIView):
    """POST /api/v1/comms/sms/send/ — Send a single SMS. Gated on ONE_CLICK_SMS."""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, IsNotReadOnly]
    required_feature = FeatureKey.ONE_CLICK_SMS

    def post(self, request):
        serializer = SendSMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from apps.communications.tasks import send_single_sms
        from apps.leads.models import Lead

        lead_id = serializer.validated_data["lead_id"]
        # Only a lead this agent may see; the lookup was unscoped.
        from apps.leads.views import leads_visible_to

        lead = leads_visible_to(request.user).filter(pk=lead_id).first()
        if lead is None:
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

    def create(self, request, *args, **kwargs):
        """
        Create, then answer with the full campaign.

        BulkCampaignCreateSerializer lists only the writable fields, so the
        201 came back without an id, a status or a recipient estimate — the
        client was handed a copy of what it had just sent. Nothing could link
        to the new campaign or tell whether it had become a draft or a
        scheduled send without refetching the whole list.
        """
        write = self.get_serializer(data=request.data)
        write.is_valid(raise_exception=True)
        campaign = self.perform_create(write)
        headers = self.get_success_headers(write.data)
        return Response(
            BulkCampaignSerializer(campaign).data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    def perform_create(self, serializer):
        # The required feature depends on the campaign's channel, so it can't
        # be a static required_feature on the view.
        require_channel_feature(
            self.request, serializer.validated_data.get("channel"), bulk=True
        )
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
        return campaign


class CampaignAudiencePreviewView(APIView):
    """
    POST /api/v1/comms/campaigns/preview-audience/
    Body: {"audience_filters": {...}}  →  {"count": 412}

    How many leads a set of filters actually reaches, before a campaign is
    created. The form had no way to ask: an admin picked filters, saved the
    campaign, and only then found out whether it was addressing 4 people or
    4,000 — with a launch button next to the answer.

    Deliberately runs the same _resolve_campaign_audience the send uses, so
    the number shown and the number messaged cannot drift apart.
    """

    # Manager/admin only, like campaigns themselves. Any agent could call
    # this and count every lead in the tenant, past their own visibility.
    permission_classes = [IsManagerOrAdmin]

    def post(self, request):
        filters = request.data.get("audience_filters") or {}
        if not isinstance(filters, dict):
            return Response(
                {"error": "invalid_filters", "message": "audience_filters must be an object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.communications.tasks import _resolve_campaign_audience

        # A stand-in campaign: the resolver only reads audience_filters, and
        # this must not create a row just to count.
        preview = BulkCampaign(audience_filters=filters)
        audience = _resolve_campaign_audience(preview)

        # DND leads are skipped at send time, so they are not "will be sent to".
        dnd = sum(1 for lead in audience if lead.is_dnd)
        with_phone = sum(1 for lead in audience if (lead.phone or "").strip() and not lead.is_dnd)
        with_email = sum(1 for lead in audience if (lead.email or "").strip())

        return Response({
            "count": len(audience),
            "dnd": dnd,
            # Channel matters: an audience of 400 leads with 12 email
            # addresses is not a 400-recipient email campaign.
            "with_phone": with_phone,
            "with_email": with_email,
        })


class BulkCampaignDetailView(generics.RetrieveAPIView):
    """GET /api/v1/comms/campaigns/{id}/ — Campaign detail with live stats."""

    permission_classes = [IsManagerOrAdmin]
    serializer_class = BulkCampaignSerializer

    def get_queryset(self):
        return BulkCampaign.objects.all()


class CampaignRecipientListView(APIView):
    """
    GET /api/v1/comms/campaigns/{id}/recipients/?status=failed&page=1

    Who a campaign went to and what happened to each message. A finished
    campaign was a card with a count and nothing behind it — no way to see
    which customers failed, or why.
    """

    permission_classes = [IsManagerOrAdmin]

    def get(self, request, pk):
        from apps.communications.models import CampaignRecipient

        campaign = BulkCampaign.objects.filter(pk=pk).first()
        if campaign is None:
            return Response({"error": "not_found"}, status=404)
        qs = (
            CampaignRecipient.objects.filter(campaign=campaign)
            .select_related("lead").order_by("status", "lead__name")
        )
        if status_param := request.query_params.get("status"):
            qs = qs.filter(status=status_param)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        rows = [
            {
                "id": r.pk,
                "lead_id": r.lead_id,
                "lead_name": r.lead.name if r.lead_id else "",
                "phone": r.phone,
                "status": r.status,
                "error_message": r.error_message,
                "sent_at": r.sent_at,
            }
            for r in page
        ]
        return paginator.get_paginated_response(rows)


LAUNCHABLE_STATUSES = ("draft", "scheduled", "paused")


class BulkCampaignLaunchView(APIView):
    """
    POST /api/v1/comms/campaigns/{id}/launch/ — Start sending a campaign.
    Gated per channel (bulk_whatsapp / bulk_email / bulk_sms). Re-checked here
    and not only at creation, since a plan can lapse between the two.
    """

    permission_classes = [IsManagerOrAdmin]

    def post(self, request, pk):
        try:
            campaign = BulkCampaign.objects.get(pk=pk, status__in=LAUNCHABLE_STATUSES)
        except BulkCampaign.DoesNotExist:
            return Response({"error": "campaign_not_found_or_not_launchable"}, status=404)

        require_channel_feature(request, campaign.channel, bulk=True)

        # The template was checked when the campaign was created, but it can
        # be switched off or its approval withdrawn since — and then every
        # message fails at the provider, long after the admin has left.
        template = campaign.template
        if campaign.channel == "whatsapp" and template is not None:
            if not template.is_active or template.status != "approved":
                return Response(
                    {"error": "template_not_usable",
                     "message": f'"{template.name}" is no longer an active, approved template. '
                                "Pick another before launching."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if campaign.channel == "whatsapp":
            # Not connected → the mock provider would mark the whole audience
            # "sent" with nothing delivered. Unmapped {{N}} → customers get the
            # literal placeholder. Both refused here, before anything queues.
            from apps.communications.tasks import whatsapp_launch_problem
            from apps.communications.whatsapp_ready import NOT_CONNECTED

            problem = whatsapp_launch_problem(campaign)
            if problem:
                code = "whatsapp_not_connected" if problem == NOT_CONNECTED["message"] else "campaign_not_ready"
                return Response({"error": code, "message": problem}, status=status.HTTP_400_BAD_REQUEST)

        from apps.communications import tasks as comm_tasks

        CAMPAIGN_TASK_MAP = {
            "whatsapp": comm_tasks.send_bulk_whatsapp_campaign,
            "email": comm_tasks.send_bulk_email_campaign,
            "sms": comm_tasks.send_bulk_sms_campaign,
        }
        task_fn = CAMPAIGN_TASK_MAP.get(campaign.channel)
        if not task_fn:
            return Response({"error": "unsupported_channel"}, status=400)

        # Claim it before dispatching, conditionally — the same way the
        # scheduler does. This used to dispatch first and mark it running
        # after, so a double click, or a click as the scheduler picked up a
        # scheduled campaign, sent the whole audience twice. Whoever wins this
        # UPDATE owns the launch.
        previous_status = campaign.status
        claimed = BulkCampaign.objects.filter(
            pk=campaign.pk, status__in=LAUNCHABLE_STATUSES
        ).update(status="running")
        if not claimed:
            return Response(
                {"error": "campaign_already_launched",
                 "message": "This campaign is already running."},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            result = task_fn.apply_async(
                args=[connection.schema_name, str(campaign.id)],
                queue="bulk_ops",
            )
        except Exception:
            # Nothing was queued — give the campaign back so it can be retried.
            BulkCampaign.objects.filter(pk=campaign.pk, status="running").update(
                status=previous_status
            )
            raise
        campaign.celery_task_id = result.id
        campaign.status = "running"
        campaign.save(update_fields=["celery_task_id"])

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


def _require_whatsapp_feature(request):
    """403→402 upsell unless the plan has any WhatsApp channel feature."""
    has = getattr(request, "has_feature", lambda k: False)
    if has(FeatureKey.ONE_CLICK_WHATSAPP) or has(FeatureKey.BULK_WHATSAPP):
        return
    from apps.core.exceptions import FeatureNotEnabledException
    raise FeatureNotEnabledException(feature_key=FeatureKey.BULK_WHATSAPP)


def _audit_account(request, config, description):
    AuditLog.log(
        action=AuditAction.UPDATE,
        actor_type="agent",
        actor_id=request.user.pk,
        actor_email=request.user.email,
        tenant_schema=connection.schema_name,
        entity_type="WhatsAppConfig",
        entity_id=config.pk,
        entity_repr=config.label,
        description=description,
        request=request,
        is_sensitive=True,
    )


def _account_or_404(pk):
    from django.http import Http404

    config = WhatsAppConfig.objects.filter(pk=pk).first()
    if config is None:
        raise Http404("WhatsApp account not found.")
    return config


def _test_account(request, config):
    """
    Send a real one-off message through this account's saved credentials. On
    success the account is marked active (sends start flowing); on failure the
    provider's own error is stored and returned, and it stays inactive.
    """
    from django.utils import timezone

    from apps.communications.providers.whatsapp import (
        WhatsAppError, provider_class, verify_config,
    )

    phone = (request.data.get("phone") or "").strip()
    message = (request.data.get("message") or "TeleCRM WhatsApp test message.").strip()
    if not phone:
        return Response(
            {"error": "phone_required", "message": "Provide a phone number to test with."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ok, detail = verify_config(config)
    if not ok:
        config.is_active = False
        config.last_error = detail
        config.save(update_fields=["is_active", "last_error", "updated_at"])
        return Response(
            {"ok": False, "error": "invalid_credentials", "message": detail},
            status=status.HTTP_400_BAD_REQUEST,
        )

    provider = provider_class(config.provider)(dict(config.credentials or {}))
    try:
        msg_id = provider.send_text(phone=phone, message=message)
    except WhatsAppError as exc:
        config.is_active = False
        config.last_error = str(exc)[:500]
        config.save(update_fields=["is_active", "last_error", "updated_at"])
        return Response(
            {"ok": False, "error": "send_failed", "message": str(exc)},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    config.is_active = True
    config.last_error = ""
    config.last_verified_at = timezone.now()
    config.save(update_fields=["is_active", "last_error", "last_verified_at", "updated_at"])
    return Response({"ok": True, "provider_message_id": msg_id, "sent_to": phone})


def _rotate_verify_token(request, config):
    """
    Mint a fresh webhook verify token and return it EXACTLY ONCE.

    The token is what proves a caller is Meta during the webhook handshake, so
    it is a secret: WhatsAppConfigSerializer masks it like any other, and the
    only way to read one is to create it here and paste it straight into the
    Meta app. Rotating invalidates the old one, which will break verification
    until Meta's webhook configuration is updated with the new value — that is
    the intended trade and the response says so.
    """
    import secrets

    token = secrets.token_urlsafe(32)
    credentials = dict(config.credentials or {})
    rotated = bool(credentials.get("verify_token"))
    credentials["verify_token"] = token
    config.credentials = credentials
    config.save(update_fields=["credentials", "updated_at"])

    _audit_account(request, config, f"Rotated the Meta WhatsApp webhook verify token ({config.label})")
    logger.info(
        "[Meta CTWA] Verify token rotated | schema=%s account=%s by=%s",
        connection.schema_name, config.pk, request.user.pk,
    )
    return Response({
        "verify_token": token,
        "rotated": rotated,
        "message": (
            "Copy this now — it is not shown again. Paste it into the Meta "
            "app's WhatsApp webhook configuration as the Verify Token, then "
            "click Verify and Save."
        ),
    })


class WhatsAppConfigView(APIView):
    """
    GET/PUT /api/v1/comms/whatsapp/config/

    The tenant's DEFAULT WhatsApp account — kept for the screens and app
    versions written when a tenant had one connection. The full list lives at
    /comms/whatsapp/accounts/. Admin-only, and only useful to a tenant whose
    plan includes a WhatsApp feature. Credentials are write-only; the
    response never contains a secret's value.
    """

    permission_classes = [IsAuthenticatedAgent, IsTenantAdmin]

    def get(self, request):
        _require_whatsapp_feature(request)
        config = WhatsAppConfig.get_solo()
        return Response(WhatsAppConfigSerializer(config, context={"request": request}).data)

    def put(self, request):
        _require_whatsapp_feature(request)
        config = WhatsAppConfig.get_solo()
        serializer = WhatsAppConfigSerializer(config, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _audit_account(request, config, f"Updated WhatsApp provider to {config.provider}")
        return Response(WhatsAppConfigSerializer(config, context={"request": request}).data)


class WhatsAppConfigTestView(APIView):
    """POST /api/v1/comms/whatsapp/config/test/ — test-send from the default account."""

    permission_classes = [IsAuthenticatedAgent, IsTenantAdmin]

    def post(self, request):
        return _test_account(request, WhatsAppConfig.get_solo())


class WhatsAppAccountListView(APIView):
    """
    GET  /api/v1/comms/whatsapp/accounts/  → every connected WhatsApp number
    POST /api/v1/comms/whatsapp/accounts/  → connect another one

    A second number needs the multi-account plan feature
    (WHATSAPP_MULTI_PROVIDER). Admin-only.
    """

    permission_classes = [IsAuthenticatedAgent, IsTenantAdmin]

    def get(self, request):
        _require_whatsapp_feature(request)
        from apps.communications.whatsapp_accounts import can_add_account

        accounts = WhatsAppConfig.objects.order_by("-is_default", "label", "pk")
        return Response({
            "results": WhatsAppConfigSerializer(accounts, many=True, context={"request": request}).data,
            "can_add": can_add_account(request),
        })

    def post(self, request):
        _require_whatsapp_feature(request)
        from apps.communications.whatsapp_accounts import can_add_account

        if not can_add_account(request):
            from apps.core.exceptions import FeatureNotEnabledException

            raise FeatureNotEnabledException(feature_key=FeatureKey.WHATSAPP_MULTI_PROVIDER)
        if not (request.data.get("label") or "").strip():
            return Response(
                {"error": "validation_error", "message": "Validation failed.",
                 "detail": {"label": ["Give this number a name, e.g. Sales or Support."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = dict(request.data)
        config = WhatsAppConfig()
        source_id = data.pop("copy_credentials_from", None)
        if source_id not in (None, ""):
            # Another number in a WhatsApp Business Account that is already
            # connected: the token, app secret and webhook settings are the
            # account's, so only the new number's id has to be entered.
            source = WhatsAppConfig.objects.filter(pk=source_id).first()
            if source is None or source.provider != "meta_cloud":
                return Response(
                    {"error": "invalid_source",
                     "message": "Pick a connected Meta Cloud API number to copy the account details from."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            pnid = str((data.get("credentials") or {}).get("phone_number_id") or "").strip()
            if not pnid:
                return Response(
                    {"error": "validation_error", "message": "Validation failed.",
                     "detail": {"phone_number_id": ["Pick or enter the new number's Phone number ID."]}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            shared = {k: v for k, v in (source.credentials or {}).items()
                      if k in SAME_ACCOUNT_CREDENTIALS and v}
            data["credentials"] = {**shared, "phone_number_id": pnid}
            data["provider"] = "meta_cloud"
            for field in SAME_ACCOUNT_SETTINGS:
                data.setdefault(field, getattr(source, f"{field}_id" if field == "inbound_assign_to" else field))
        serializer = WhatsAppConfigSerializer(config, data=data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _audit_account(request, config, f"Connected WhatsApp number {config.label} ({config.provider})")
        return Response(
            WhatsAppConfigSerializer(config, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


#: Credentials that belong to the WhatsApp Business Account / Meta app rather
#: than to one number — copied when another number of the same account is added.
SAME_ACCOUNT_CREDENTIALS = (
    "access_token", "business_account_id", "app_secret", "verify_token", "ads_access_token",
)
#: Inbound settings copied the same way: the numbers share one webhook.
SAME_ACCOUNT_SETTINGS = (
    "default_language", "graph_api_version", "inbound_enabled", "create_leads_from_inbound",
    "ctwa_leads_only", "reopen_lead_on_inbound", "inbound_assign_to",
)


class WhatsAppAccountMetaNumbersView(APIView):
    """
    GET /api/v1/comms/whatsapp/accounts/{id}/meta-numbers/

    Every phone number in this number's Meta WhatsApp Business Account, read
    from Meta with the saved token — so adding a second number of the same
    account is a pick from a list, not a hunt for its Phone number ID.
    Each row says whether it is already connected here.
    """

    permission_classes = [IsAuthenticatedAgent, IsTenantAdmin]

    def get(self, request, pk):
        import requests
        from django.conf import settings

        _require_whatsapp_feature(request)
        config = _account_or_404(pk)
        creds = config.credentials or {}
        waba, token = config.business_account_id, creds.get("access_token")
        if config.provider != "meta_cloud" or not waba or not token:
            return Response(
                {"error": "not_meta_cloud",
                 "message": "This needs a Meta Cloud API number with its access token and "
                            "WhatsApp Business Account ID saved."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        version = config.graph_api_version or getattr(settings, "META_GRAPH_API_VERSION", "v25.0")
        try:
            resp = requests.get(
                f"https://graph.facebook.com/{version}/{waba}/phone_numbers",
                params={"fields": "id,display_phone_number,verified_name,quality_rating,"
                                  "code_verification_status,status"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            body = resp.json() if resp.content else {}
        except (requests.RequestException, ValueError) as exc:
            logger.warning("[WA] Listing WABA numbers failed for account %s: %s", config.pk, exc)
            return Response({"error": "meta_unreachable", "message": "Could not reach Meta. Try again."},
                            status=status.HTTP_502_BAD_GATEWAY)
        if resp.status_code >= 400 or "error" in body:
            message = (body.get("error") or {}).get("message") or f"Meta answered {resp.status_code}."
            return Response({"error": "meta_error", "message": message}, status=status.HTTP_502_BAD_GATEWAY)

        connected = {
            a.phone_number_id: a.label for a in WhatsAppConfig.objects.exclude(phone_number_id="")
        }
        numbers = [
            {
                "phone_number_id": str(n.get("id") or ""),
                "display_phone": n.get("display_phone_number") or "",
                "verified_name": n.get("verified_name") or "",
                "quality_rating": n.get("quality_rating") or "",
                "status": n.get("status") or n.get("code_verification_status") or "",
                "connected_as": connected.get(str(n.get("id") or "")),
            }
            for n in body.get("data") or [] if n.get("id")
        ]
        return Response({"business_account_id": waba, "numbers": numbers})


class WhatsAppAccountDetailView(APIView):
    """GET/PATCH/DELETE /api/v1/comms/whatsapp/accounts/{id}/ — admin-only."""

    permission_classes = [IsAuthenticatedAgent, IsTenantAdmin]

    def get(self, request, pk):
        _require_whatsapp_feature(request)
        return Response(WhatsAppConfigSerializer(_account_or_404(pk), context={"request": request}).data)

    def patch(self, request, pk):
        _require_whatsapp_feature(request)
        config = _account_or_404(pk)
        serializer = WhatsAppConfigSerializer(config, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _audit_account(request, config, f"Updated WhatsApp number {config.label}")
        return Response(WhatsAppConfigSerializer(config, context={"request": request}).data)

    def delete(self, request, pk):
        """
        Disconnect a number. Its messages, templates and campaigns stay: they
        are history, and a message keeps its text even without a sender. A
        campaign still sending from it must be paused first.
        """
        _require_whatsapp_feature(request)
        config = _account_or_404(pk)
        if BulkCampaign.objects.filter(whatsapp_account=config, status__in=("running", "scheduled")).exists():
            return Response(
                {"error": "account_in_use",
                 "message": f"A running or scheduled campaign sends from {config.label}. Pause it first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        label = config.label
        _audit_account(request, config, f"Disconnected WhatsApp number {label}")
        config.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WhatsAppAccountTestView(APIView):
    """POST /api/v1/comms/whatsapp/accounts/{id}/test/ {"phone": "+9198..."}"""

    permission_classes = [IsAuthenticatedAgent, IsTenantAdmin]

    def post(self, request, pk):
        return _test_account(request, _account_or_404(pk))


class WhatsAppAccountMakeDefaultView(APIView):
    """POST /api/v1/comms/whatsapp/accounts/{id}/make-default/"""

    permission_classes = [IsAuthenticatedAgent, IsTenantAdmin]

    def post(self, request, pk):
        config = _account_or_404(pk)
        config.is_default = True
        config.save()
        _audit_account(request, config, f"Made {config.label} the default WhatsApp number")
        return Response(WhatsAppConfigSerializer(config, context={"request": request}).data)


class WhatsAppAccountVerifyTokenView(APIView):
    """POST /api/v1/comms/whatsapp/accounts/{id}/webhook-token/ — see _rotate_verify_token."""

    permission_classes = [IsAuthenticatedAgent, IsTenantAdmin]

    def post(self, request, pk):
        return _rotate_verify_token(request, _account_or_404(pk))


class WhatsAppSendersView(APIView):
    """
    GET /api/v1/comms/whatsapp/senders/

    The numbers an agent can send from — names and numbers only, never a
    credential. Feeds the "Send from" picker on one-click sends and campaigns.
    """

    permission_classes = [IsAuthenticatedAgent]

    def get(self, request):
        accounts = WhatsAppConfig.objects.order_by("-is_default", "label", "pk")
        return Response([
            {
                "id": a.pk, "label": a.label, "display_phone": a.display_phone,
                "is_default": a.is_default, "is_active": a.is_active, "provider": a.provider,
            }
            for a in accounts
        ])


class WhatsAppWebhookView(APIView):
    """
    POST /api/v1/comms/webhook/whatsapp/{provider}/
    Receives delivery status updates and inbound messages from WhatsApp providers.
    Updates WhatsAppMessage status and creates inbound message records.
    """

    permission_classes = [AllowAny]
    # Not rate-limited. A provider posts every delivery and read receipt from
    # a handful of addresses; under the default anonymous throttle
    # (20/hour per IP) the 21st callback in an hour got a 429, and a campaign
    # of any size lost almost all of its statuses. Keeping strangers out is
    # the job of authentication, not of a throttle.
    throttle_classes = []

    def post(self, request, provider):
        # The URL must carry this tenant's webhook token. Without it, anyone
        # could mark messages delivered/read/failed or inject "customer
        # replies" — with a notification to the agent — into any thread.
        import hmac

        # Each WhatsApp account has its own token, so the token also says
        # which account (number) the post is for.
        sent = request.query_params.get("token") or request.headers.get("X-Webhook-Token") or ""
        config = None
        if sent:
            for candidate in WhatsAppConfig.objects.exclude(webhook_token=""):
                if hmac.compare_digest(sent, candidate.webhook_token):
                    config = candidate
                    break
        if config is None:
            logger.warning(f"[WA Webhook] Unauthenticated post refused ({provider})")
            return Response({"error": "unauthenticated"}, status=401)

        payload = request.data if isinstance(request.data, dict) else {}
        logger.info(f"[WA Webhook] Event from {provider}: {list(payload.keys())}")

        # Parsing and recording for every provider live in
        # whatsapp_webhooks.py. Always 200: a provider that gets an error
        # retries the same event, which cannot fix a payload we can't read.
        from apps.communications import whatsapp_webhooks

        try:
            whatsapp_webhooks.handle(provider, payload, account=config)
        except Exception as exc:
            logger.error(f"[WA Webhook] Handler error ({provider}): {exc}", exc_info=True)

        return Response({"status": "ok"})


# ============================================================
# Inbound WhatsApp — Click-to-WhatsApp administration
# ============================================================

class WhatsAppVerifyTokenView(APIView):
    """POST /api/v1/comms/whatsapp/webhook-token/ — the default account's (see _rotate_verify_token)."""

    permission_classes = [IsAuthenticatedAgent, IsTenantAdmin]

    def post(self, request):
        return _rotate_verify_token(request, WhatsAppConfig.get_solo())


class WhatsAppConversationListView(generics.ListAPIView):
    """
    GET /api/v1/comms/whatsapp/conversations/?lead={id}&ad_referred=true

    WhatsApp threads with their Meta ad attribution, newest activity first.
    Powers the "where did this lead come from?" panel on a lead, and a
    campaign-level view of Click-to-WhatsApp traffic.
    """

    permission_classes = [IsAuthenticatedAgent, IsActiveAgent]
    serializer_class = WhatsAppConversationSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = WhatsAppConversation.objects.select_related("lead")

        # Secure by default, the same rule as the lead list: admins and
        # managers see every thread; everybody else sees only threads on leads
        # they can see.
        #
        # This used to be "if role == agent: restrict" — the inverted default
        # calls/scoping.py warns about — so HR, Accounts, Read-only, Senior
        # agents and any role added later could list EVERY WhatsApp
        # conversation in the tenant. Admin/manager skip the `lead__in`
        # subquery only because leads_visible_to would return every lead for
        # them anyway — the result is identical, the query is cheaper.
        from apps.leads.views import leads_visible_to

        agent = self.request.user
        if getattr(agent, "role", None) not in (AgentRole.ADMIN, AgentRole.MANAGER):
            queryset = queryset.filter(lead__in=leads_visible_to(agent))

        if lead_id := self.request.query_params.get("lead"):
            queryset = queryset.filter(lead_id=lead_id)
        if (ad_only := self.request.query_params.get("ad_referred")) is not None:
            queryset = queryset.filter(is_ad_referred=ad_only.lower() in ("1", "true", "yes"))
        if campaign_id := self.request.query_params.get("campaign_id"):
            queryset = queryset.filter(meta_campaign_id=campaign_id)

        return queryset.order_by("-last_message_at", "-created_at")
