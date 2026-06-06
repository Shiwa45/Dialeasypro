"""
TeleCRM Backend — apps/tenants/views.py

Public-facing API view for tenant (customer) registration.
Called from the marketing/landing page signup form.

POST /api/v1/public/register/
  → Validates form data
  → Creates Tenant + Domain in public schema
  → Schema creation triggers post_schema_sync signal which:
     - Creates default admin Agent
     - Creates starter Subscription
     - Sends welcome email
  → Returns tenant details + login URL
"""
import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.superadmin.models import AuditLog, GlobalSettings
from apps.core.constants import AuditAction
from apps.tenants.serializers import TenantPublicSerializer, TenantRegistrationSerializer

logger = logging.getLogger(__name__)


class TenantRegistrationAPIView(APIView):
    """
    Public endpoint: register a new TeleCRM tenant.
    No authentication required — this is the signup form.

    POST /api/v1/public/register/
    Request:
      {
        "company_name": "Acme Realty Pvt Ltd",
        "industry": "real_estate",
        "primary_contact_name": "Rahul Sharma",
        "primary_contact_email": "rahul@acmerealty.com",
        "primary_contact_phone": "9876543210",
        "city": "Mumbai",
        "state": "MH",
        "plan_slug": "starter"
      }

    Response 201:
      {
        "message": "Account created! Check your email for login credentials.",
        "tenant": { ... },
        "login_url": "https://acme-realty.telecrm.in/crm/login/"
      }
    """

    permission_classes = [AllowAny]
    throttle_scope = "registration"

    def post(self, request):
        # Check if new registrations are allowed
        allow_new = GlobalSettings.get("allow_new_registrations", "true").lower()
        if allow_new != "true":
            return Response(
                {
                    "error": "registrations_closed",
                    "message": (
                        "New registrations are temporarily paused. "
                        "Please contact support@telecrm.in"
                    ),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = TenantRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            tenant = serializer.save()
        except Exception as exc:
            logger.error(f"[Registration] Failed to create tenant: {exc}", exc_info=True)
            return Response(
                {
                    "error": "registration_failed",
                    "message": "Account creation failed. Please try again or contact support.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Build login URL
        from django.conf import settings as django_settings
        login_url = (
            f"https://{tenant.schema_name}.{django_settings.BASE_DOMAIN}/crm/login/"
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_type="api",
            actor_ip=request.META.get("REMOTE_ADDR", ""),
            entity_type="Tenant",
            entity_id=tenant.pk,
            entity_repr=tenant.company_name,
            description=f"New tenant registered: {tenant.schema_name}",
        )

        logger.info(
            f"[Registration] New tenant: {tenant.company_name} ({tenant.schema_name})"
        )

        return Response(
            {
                "message": (
                    "Your CRM account is ready! "
                    "Check your email for login credentials."
                ),
                "tenant": TenantPublicSerializer(tenant).data,
                "login_url": login_url,
                "trial_days": tenant.trial_days_remaining,
            },
            status=status.HTTP_201_CREATED,
        )


class TenantCheckSubdomainAPIView(APIView):
    """
    GET /api/v1/public/check-subdomain/?name=acmerealty
    Check if a subdomain is available before registration.
    Called by the signup form for live availability feedback.
    """

    permission_classes = [AllowAny]
    throttle_scope = "registration"

    def get(self, request):
        from apps.core.utils import slugify_company_name
        from apps.tenants.models import Tenant

        name = request.query_params.get("name", "").strip()
        if not name or len(name) < 2:
            return Response(
                {"error": "name_required", "message": "Please provide at least 2 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        slug = slugify_company_name(name)
        if not slug:
            return Response({"available": False, "slug": "", "reason": "invalid_characters"})

        taken = Tenant.objects.filter(schema_name=slug).exists()
        return Response(
            {
                "available": not taken,
                "slug": slug,
                "url": f"https://{slug}.telecrm.in",
                "reason": "taken" if taken else None,
            }
        )
