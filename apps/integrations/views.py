"""
TeleCRM Backend — apps/integrations/views.py

Inbound webhook handlers for all Indian lead sources.

IndiaMART Webhook      POST /api/v1/integrations/indiamart/
Meta Lead Ads Webhook  POST /api/v1/integrations/meta/
Google Ads Webhook     POST /api/v1/integrations/google/
Generic Webhook        POST /api/v1/integrations/webhook/{token}/
Portal Webhook         POST /api/v1/integrations/portal/{slug}/
IntegrationConfigView  GET/POST/PATCH /api/v1/integrations/configs/
"""
import hashlib
import hmac
import json
import logging

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import (
    IsAuthenticatedAgent,
    IsTenantAdmin,
    require_feature,
)
from apps.core.constants import LeadPriority, LeadSource
from apps.core.exceptions import PlanLimitExceededException
from apps.core.quotas import enforce_lead_quota, note_leads_created
from apps.core.utils import normalize_indian_phone
from apps.integrations.models import LeadSourceConfig, WebhookLog
from apps.integrations.serializers import LeadSourceConfigSerializer

logger = logging.getLogger(__name__)


# ============================================================
# Base Webhook View
# ============================================================

class BaseWebhookView(View):
    """
    Base class for all lead source webhook handlers.
    Subclasses implement parse_payload() and optionally validate_signature().
    """

    source = None   # Override in subclass: LeadSource.INDIAMART etc.

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        config = self._get_config()
        if config and not config.is_active:
            return HttpResponse("Integration disabled", status=403)

        # Log raw payload immediately (before any processing)
        raw_body = request.body
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            payload = {"raw": raw_body.decode("utf-8", errors="replace")[:5000]}

        log = WebhookLog.objects.create(
            source=self.source or "webhook",
            config=config,
            method="POST",
            headers=dict(request.headers),
            payload=payload,
        )

        # Validate signature if configured
        if not self.validate_signature(request, raw_body, config):
            log.error = "Signature validation failed"
            log.save(update_fields=["error"])
            logger.warning(f"[Integration] Signature fail — source={self.source}")
            return HttpResponse("Invalid signature", status=401)

        # Parse and create leads
        try:
            leads_created, leads_updated = self.process_payload(payload, config, request)
            log.processed = True
            log.leads_created = leads_created
            log.leads_updated = leads_updated
            log.save(update_fields=["processed", "leads_created", "leads_updated"])

            if config:
                config.total_leads_received += leads_created
                config.last_received_at = timezone.now()
                config.error_message = ""
                config.save(update_fields=["total_leads_received", "last_received_at", "error_message"])

        except PlanLimitExceededException as exc:
            # The tenant is over their plan's lead cap. Surface it distinctly so
            # the Integrations UI shows an upgrade prompt rather than a generic
            # failure — and still answer 200 so the provider doesn't retry
            # forever against a limit that only an upgrade can lift.
            msg = str(exc.detail)
            logger.warning(f"[Integration] Lead quota reached — source={self.source}: {msg}")
            log.error = msg[:500]
            log.save(update_fields=["error"])
            if config:
                config.error_message = msg[:500]
                config.status = "error"
                config.save(update_fields=["error_message", "status"])
            return JsonResponse({"status": "quota_exceeded", "message": msg}, status=200)

        except Exception as exc:
            logger.error(f"[Integration] Processing failed — source={self.source}: {exc}", exc_info=True)
            log.error = str(exc)[:500]
            log.save(update_fields=["error"])
            if config:
                config.error_message = str(exc)[:500]
                config.status = "error"
                config.save(update_fields=["error_message", "status"])

        return JsonResponse({"status": "ok"})

    def validate_signature(self, request, raw_body: bytes, config) -> bool:
        """Override to implement provider-specific signature validation."""
        return True

    def process_payload(self, payload: dict, config, request) -> tuple:
        """Override to implement provider-specific lead creation."""
        raise NotImplementedError

    def _get_config(self):
        # .first() (not .get()) — a duplicate active config for the same source
        # would raise MultipleObjectsReturned and 500 every webhook delivery.
        return (
            LeadSourceConfig.objects.filter(source=self.source, is_active=True)
            .order_by("id")
            .first()
        )

    def _create_or_update_lead(self, lead_data: dict, config, duplicate_action: str = "skip"):
        """
        Core lead creation logic — shared by all webhook handlers.
        Returns (created: bool, lead).
        """
        from apps.leads.models import Lead, LeadActivity
        from apps.authentication.models import Agent

        phone = normalize_indian_phone(lead_data.get("phone", ""))
        if not phone:
            raise ValueError(f"Invalid phone: {lead_data.get('phone')}")

        existing = Lead.objects.filter(phone=phone, is_deleted=False).first()

        # Determine assigned agent
        assigned_to = None
        if config and config.options.get("auto_assign_to"):
            assigned_to = Agent.objects.filter(
                pk=config.options["auto_assign_to"], is_active=True
            ).first()

        if existing:
            if duplicate_action == "skip":
                return False, existing
            elif duplicate_action == "update":
                # Only fill in real, currently-empty Lead model fields.
                UPDATABLE = {
                    "name", "email", "city", "state", "pincode",
                    "alternate_phone", "requirement", "campaign_name", "ad_name",
                }
                changed = {}
                for field, value in lead_data.items():
                    if field not in UPDATABLE:
                        continue
                    if value and not getattr(existing, field, ""):
                        setattr(existing, field, value)
                        changed[field] = value
                if changed:
                    existing.save(update_fields=list(changed.keys()))
                # Fill custom values even on dedupe-update.
                self._save_custom_values(existing, lead_data.get("custom_values"))
                return False, existing

        # Plan capacity. A new lead (not a dedupe-update) counts against the
        # tenant's max_leads / max_leads_per_day caps.
        enforce_lead_quota(1)

        lead = Lead.objects.create(
            phone=phone,
            name=lead_data.get("name", "Unknown"),
            email=lead_data.get("email", ""),
            city=lead_data.get("city", ""),
            state=lead_data.get("state", ""),
            pincode=lead_data.get("pincode", ""),
            alternate_phone=normalize_indian_phone(lead_data.get("alternate_phone", "")) or "",
            requirement=lead_data.get("requirement", ""),
            source=self.source or LeadSource.WEBHOOK,
            source_meta=lead_data.get("meta", {}),
            source_lead_id=str(lead_data.get("source_lead_id", "")),
            campaign_name=lead_data.get("campaign_name", "")[:300],
            ad_name=lead_data.get("ad_name", "")[:300],
            priority=lead_data.get("priority", LeadPriority.WARM),
            assigned_to=assigned_to,
        )
        note_leads_created(1)

        # Persist any mapped custom-field values.
        self._save_custom_values(lead, lead_data.get("custom_values"))

        LeadActivity.objects.create(
            lead=lead, activity_type="imported",
            description=f"Lead received via {self.source or 'webhook'}",
            meta={"source": self.source},
        )
        logger.info(f"[Integration] Lead created: {lead.name} ({lead.phone}) via {self.source}")
        return True, lead

    @staticmethod
    def _save_custom_values(lead, custom_values: dict | None):
        """Write mapped custom-field values, ignoring keys with no matching field."""
        if not custom_values:
            return
        from apps.leads.models import CustomField, CustomFieldValue
        for field_key, value in custom_values.items():
            field = CustomField.objects.filter(field_key=field_key, is_active=True).first()
            if field:
                CustomFieldValue.objects.update_or_create(
                    lead=lead, field=field, defaults={"value": str(value)},
                )


# ============================================================
# IndiaMART Webhook
# ============================================================

class IndiaMArtWebhookView(BaseWebhookView):
    """
    POST /api/v1/integrations/indiamart/
    Receives buyer enquiries from IndiaMART via their Lead Manager API.
    Docs: https://seller.indiamart.com/leadmanager/leadsapi

    IndiaMART sends leads as JSON array or single object.
    HMAC-SHA256 signature in X-IM-SIGNATURE header.
    """

    source = LeadSource.INDIAMART

    def validate_signature(self, request, raw_body: bytes, config) -> bool:
        if not config:
            return True  # No config = no validation
        secret = config.credentials.get("webhook_secret", "")
        if not secret:
            return True
        signature = request.headers.get("X-Im-Signature", "")
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def process_payload(self, payload: dict, config, request) -> tuple:
        # IndiaMART wraps leads in different structures depending on API version
        leads_data = []
        if isinstance(payload, list):
            leads_data = payload
        elif "RESPONSE" in payload:
            leads_data = payload["RESPONSE"] if isinstance(payload["RESPONSE"], list) else [payload["RESPONSE"]]
        elif "leads" in payload:
            leads_data = payload["leads"]
        else:
            leads_data = [payload]

        from apps.integrations.field_mapping import apply_field_mapping

        duplicate_action = (config.options.get("duplicate_action", "skip") if config else "skip")
        mapping = (config.options or {}).get("field_mapping", {}) if config else {}
        created, updated = 0, 0

        for raw_lead in leads_data:
            try:
                lead_data, custom_values = apply_field_mapping(raw_lead, mapping)
                lead_data["custom_values"] = custom_values
                lead_data["source_lead_id"] = (
                    raw_lead.get("UNIQUE_QUERY_ID") or raw_lead.get("id", "")
                )
                is_created, _ = self._create_or_update_lead(lead_data, config, duplicate_action)
                if is_created:
                    created += 1
                else:
                    updated += 1
            except Exception as exc:
                logger.warning(f"[IndiaMART] Failed to process lead: {exc}")

        return created, updated


# ============================================================
# Meta (Facebook/Instagram) Lead Ads Webhook
# ============================================================

class MetaLeadAdsWebhookView(BaseWebhookView):
    """
    GET  /api/v1/integrations/meta/  → Webhook verification (Meta requires GET)
    POST /api/v1/integrations/meta/  → Lead form submission event

    Meta sends a GET request first to verify the webhook endpoint.
    Then sends POST with lead form data in real time.
    Lead form values must be fetched via Meta Graph API (not included in webhook payload).
    """

    source = LeadSource.META_FACEBOOK

    def get(self, request, *args, **kwargs):
        """Handle Meta's webhook verification challenge."""
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        config = self._get_config()
        verify_token = config.credentials.get("verify_token", "") if config else ""

        if mode == "subscribe" and token == verify_token:
            logger.info("[Meta] Webhook verified")
            return HttpResponse(challenge, content_type="text/plain")

        return HttpResponse("Forbidden", status=403)

    def validate_signature(self, request, raw_body: bytes, config) -> bool:
        """Validate X-Hub-Signature-256 from Meta."""
        if not config:
            return True
        app_secret = config.credentials.get("app_secret", "")
        if not app_secret:
            return True
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not signature.startswith("sha256="):
            return False
        expected = f"sha256={hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()}"
        return hmac.compare_digest(expected, signature)

    def process_payload(self, payload: dict, config, request) -> tuple:
        """
        Meta sends leadgen events. We extract lead ID and fetch details via Graph API.
        For now, log and return — full Graph API fetch is implemented below.
        """
        created, updated = 0, 0

        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                if change.get("field") != "leadgen":
                    continue
                value = change.get("value", {})
                lead_id = value.get("leadgen_id")
                form_id = value.get("form_id")
                page_id = value.get("page_id")

                if lead_id and config:
                    # Fetch lead details from Meta Graph API
                    lead_data = self._fetch_meta_lead(lead_id, config)
                    if lead_data:
                        is_created, _ = self._create_or_update_lead(
                            lead_data, config,
                            duplicate_action=config.options.get("duplicate_action", "skip"),
                        )
                        if is_created:
                            created += 1

        return created, updated

    def _fetch_meta_lead(self, lead_id: str, config) -> dict | None:
        """
        Fetch lead form details from Meta Graph API and map them to CRM fields
        using the tenant's configured field mapping.
        """
        try:
            import requests as req
            from apps.integrations.field_mapping import (
                flatten_meta_field_data, apply_field_mapping,
            )

            access_token = config.credentials.get("access_token", "")
            if not access_token:
                return None

            # Request campaign/ad attribution alongside the form field data.
            resp = req.get(
                f"https://graph.facebook.com/v18.0/{lead_id}",
                params={
                    "access_token": access_token,
                    "fields": (
                        "field_data,created_time,ad_id,ad_name,adset_id,"
                        "adset_name,campaign_id,campaign_name,form_id,platform"
                    ),
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            raw_fields = flatten_meta_field_data(data.get("field_data", []))
            mapping = (config.options or {}).get("field_mapping", {})
            lead_data, custom_values = apply_field_mapping(raw_fields, mapping)

            lead_data["source_lead_id"] = lead_id
            lead_data["custom_values"] = custom_values
            # Campaign attribution (explicit mapping can still override).
            lead_data.setdefault("campaign_name", data.get("campaign_name", ""))
            lead_data.setdefault("ad_name", data.get("ad_name") or data.get("adset_name", ""))
            # Keep full attribution in raw meta for reporting/debugging.
            lead_data["meta"].update({
                "campaign_id": data.get("campaign_id", ""),
                "campaign_name": data.get("campaign_name", ""),
                "adset_name": data.get("adset_name", ""),
                "ad_id": data.get("ad_id", ""),
                "ad_name": data.get("ad_name", ""),
                "form_id": data.get("form_id", ""),
                "platform": data.get("platform", ""),
            })
            return lead_data
        except Exception as exc:
            logger.error(f"[Meta] Failed to fetch lead {lead_id}: {exc}")
            return None


# ============================================================
# Google Ads Lead Forms Webhook
# ============================================================

class GoogleAdsWebhookView(BaseWebhookView):
    """
    POST /api/v1/integrations/google/
    Receives lead form submissions from Google Ads Lead Form extensions.
    Uses Zapier or direct webhook integration.
    """

    source = LeadSource.GOOGLE_ADS

    def process_payload(self, payload: dict, config, request) -> tuple:
        from apps.integrations.field_mapping import apply_field_mapping

        mapping = (config.options or {}).get("field_mapping", {}) if config else {}
        lead_data, custom_values = apply_field_mapping(payload, mapping)
        lead_data["custom_values"] = custom_values
        lead_data["source_lead_id"] = payload.get("lead_id", "")
        # Google Lead Form extensions include campaign attribution.
        lead_data.setdefault("campaign_name", payload.get("campaign_name", "") or payload.get("campaign", ""))
        lead_data.setdefault("ad_name", payload.get("adgroup_name", "") or payload.get("ad_name", ""))
        is_created, _ = self._create_or_update_lead(
            lead_data, config,
            duplicate_action=config.options.get("duplicate_action", "skip") if config else "skip",
        )
        return (1, 0) if is_created else (0, 1)


# ============================================================
# Generic Webhook (token-based)
# ============================================================

class GenericWebhookView(BaseWebhookView):
    """
    POST /api/v1/integrations/webhook/{token}/
    A universal webhook URL that any external system can POST to.
    Token is unique per tenant and per integration source.

    Payload format (flexible — tries to extract common fields):
    {
      "name": "Rahul Sharma",
      "phone": "9876543210",
      "email": "rahul@example.com",
      "city": "Mumbai",
      "message": "Looking for 2BHK in Andheri"
    }
    """

    source = LeadSource.WEBHOOK

    def post(self, request, token, *args, **kwargs):
        # Find config by token (overrides base class which uses source)
        try:
            config = LeadSourceConfig.objects.get(webhook_token=token, is_active=True)
            self.source = config.source
        except LeadSourceConfig.DoesNotExist:
            return HttpResponse("Invalid webhook token", status=401)

        return super().post(request, token=token, *args, **kwargs)

    def _get_config(self):
        return None  # Overridden in post()

    def process_payload(self, payload: dict, config, request) -> tuple:
        from apps.integrations.field_mapping import apply_field_mapping

        mapping = (config.options or {}).get("field_mapping", {}) if config else {}
        lead_data, custom_values = apply_field_mapping(payload, mapping)
        lead_data["custom_values"] = custom_values
        lead_data["source_lead_id"] = payload.get("id") or payload.get("lead_id", "")
        lead_data.setdefault("campaign_name", payload.get("campaign_name", "") or payload.get("utm_campaign", ""))
        duplicate_action = config.options.get("duplicate_action", "skip") if config else "skip"
        is_created, _ = self._create_or_update_lead(lead_data, config, duplicate_action)
        return (1, 0) if is_created else (0, 1)


# ============================================================
# Integration Config API
# ============================================================

class IntegrationConfigListView(generics.ListCreateAPIView):
    """
    GET  /api/v1/integrations/configs/  → List all configured integrations
    POST /api/v1/integrations/configs/  → Enable/configure a new integration

    Each lead source maps to its own plan feature (LeadSource.FEATURE_MAP), and
    the plan also caps how many integrations may be active at once
    (Plan.lead_sources_limit).
    """

    permission_classes = [IsTenantAdmin]
    serializer_class = LeadSourceConfigSerializer
    pagination_class = None  # Small finite list; return plain array

    def get_queryset(self):
        return LeadSourceConfig.objects.order_by("source")

    def perform_create(self, serializer):
        source = serializer.validated_data.get("source")

        # Gate on the feature for this specific source (per-source pricing).
        if feature_key := LeadSource.FEATURE_MAP.get(source):
            require_feature(self.request, feature_key)

        # Enforce the plan's cap on simultaneously-active integrations.
        plan = getattr(self.request, "tenant_plan", None)
        if plan and plan.lead_sources_limit:
            active = LeadSourceConfig.objects.filter(is_active=True).count()
            if active >= plan.lead_sources_limit:
                raise PlanLimitExceededException(
                    limit_type="lead source integrations",
                    current=active,
                    max_allowed=plan.lead_sources_limit,
                )

        serializer.save()


class IntegrationConfigDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/v1/integrations/configs/{id}/
    Update or disable an integration.
    """

    permission_classes = [IsTenantAdmin]
    serializer_class = LeadSourceConfigSerializer

    def get_queryset(self):
        return LeadSourceConfig.objects.all()


class MetaFormFieldsView(APIView):
    """
    GET /api/v1/integrations/meta/forms/
    Introspect the tenant's Meta Lead Ad forms + their question field names,
    so the UI can offer the REAL field names to map (no guessing).

    Requires the Meta config to have access_token and a page_id saved.
    """

    permission_classes = [IsTenantAdmin]

    def get(self, request):
        config = LeadSourceConfig.objects.filter(
            source__in=[LeadSource.META_FACEBOOK, LeadSource.META_INSTAGRAM]
        ).first()
        if not config:
            return Response({"error": "no_config", "message": "Add the Meta integration first."}, status=404)

        access_token = (config.credentials or {}).get("access_token", "")
        page_id = (config.credentials or {}).get("page_id") or (config.options or {}).get("page_id")
        if not access_token or not page_id:
            return Response(
                {
                    "error": "missing_credentials",
                    "message": "Save your Page Access Token and Page ID first to auto-fetch form fields.",
                },
                status=400,
            )

        try:
            import requests as req
            resp = req.get(
                f"https://graph.facebook.com/v18.0/{page_id}/leadgen_forms",
                params={"access_token": access_token, "fields": "id,name,status,questions"},
                timeout=15,
            )
            resp.raise_for_status()
            forms = []
            for form in resp.json().get("data", []):
                questions = [
                    {"key": q.get("key") or q.get("id"), "label": q.get("label", "")}
                    for q in form.get("questions", [])
                ]
                forms.append({
                    "id": form.get("id"),
                    "name": form.get("name"),
                    "status": form.get("status"),
                    "fields": questions,
                })
            return Response({"forms": forms})
        except req.exceptions.HTTPError as exc:
            meta_err = ""
            try:
                meta_err = exc.response.json().get("error", {}).get("message", "")
            except Exception:
                meta_err = str(exc)
            logger.warning(f"[Meta] Form introspection failed: {meta_err or exc}")
            return Response(
                {
                    "error": "fetch_failed",
                    "message": f"Meta API Error: {meta_err or str(exc)}. Check your Page ID and Page Access Token.",
                },
                status=400,
            )
        except Exception as exc:
            logger.warning(f"[Meta] Form introspection failed: {exc}")
            return Response(
                {"error": "fetch_failed", "message": f"Could not fetch forms from Meta: {exc}"},
                status=400,
            )


class MetaSyncLeadsView(APIView):
    """
    POST /api/v1/integrations/meta/sync/
    Manually pull the newest Meta Lead Ads leads into the CRM — a fallback for
    when the realtime webhook hasn't delivered (or missed) leads.
    """

    permission_classes = [IsTenantAdmin]

    def post(self, request):
        config = LeadSourceConfig.objects.filter(
            source__in=[LeadSource.META_FACEBOOK, LeadSource.META_INSTAGRAM]
        ).first()
        if not config:
            return Response(
                {"error": "no_config", "message": "Add the Meta integration first."},
                status=404,
            )

        from apps.integrations.meta_sync import sync_meta_leads

        result = sync_meta_leads(config)
        if result.get("error") == "missing_credentials":
            return Response(
                {"error": "missing_credentials",
                 "message": "Save your Page Access Token and Page ID first."},
                status=400,
            )
        if result.get("error"):
            return Response(
                {"error": "fetch_failed",
                 "message": "Could not fetch leads from Meta. Check the token/Page ID."},
                status=502,
            )

        msg = f"{result['created']} new lead(s) imported"
        if result["skipped"]:
            msg += f", {result['skipped']} already in CRM"
        if result.get("quota_reached"):
            msg += ". Stopped early — your plan's lead limit was reached. Upgrade to import the rest."
        return Response({**result, "message": msg})


class WebhookLogListView(generics.ListAPIView):
    """GET /api/v1/integrations/logs/ — Integration webhook log for debugging."""

    permission_classes = [IsTenantAdmin]
    pagination_class = None  # Already capped at 200 rows; return plain array
    from apps.integrations.serializers import WebhookLogSerializer as _LogSer

    def get_serializer_class(self):
        from apps.integrations.serializers import WebhookLogSerializer
        return WebhookLogSerializer

    def get_queryset(self):
        qs = WebhookLog.objects.order_by("-created_at")
        if source := self.request.query_params.get("source"):
            qs = qs.filter(source=source)
        return qs[:200]
