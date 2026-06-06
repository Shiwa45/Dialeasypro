"""
TeleCRM Backend — apps/core/exceptions.py

Custom exception classes and DRF exception handler.
All API errors return a consistent JSON structure:

  {
    "error": "error_code",
    "message": "Human-readable message",
    "detail": { ... }   ← optional extra context
  }
"""
import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


# ============================================================
# Custom DRF Exception Handler
# ============================================================

def custom_exception_handler(exc, context):
    """
    Override DRF's default exception handler to return consistent error format.
    Registered in settings.py: REST_FRAMEWORK['EXCEPTION_HANDLER']
    """
    # Let DRF handle standard exceptions first
    response = drf_exception_handler(exc, context)

    if response is not None:
        error_code = "error"
        message = "An error occurred."
        detail = None

        # Unpack DRF's error format into our format
        if isinstance(response.data, dict):
            if "detail" in response.data:
                message = str(response.data["detail"])
                # Check if detail has a code attribute
                detail_exc = response.data.get("detail")
                if hasattr(detail_exc, "code"):
                    error_code = detail_exc.code
            elif "error" in response.data:
                error_code = response.data.get("error", "error")
                message = response.data.get("message", str(response.data))
            else:
                # Field-level validation errors → collect them
                message = "Validation failed."
                detail = response.data
                error_code = "validation_error"
        elif isinstance(response.data, list):
            message = response.data[0] if response.data else "Error"

        response.data = {
            "error": error_code,
            "message": message,
        }
        if detail:
            response.data["detail"] = detail

        # Log server errors
        if response.status_code >= 500:
            view = context.get("view")
            logger.error(
                f"[API 5xx] {exc.__class__.__name__}: {exc} | "
                f"view={view.__class__.__name__ if view else 'unknown'}",
                exc_info=exc,
            )

    else:
        # Unhandled exceptions → 500
        logger.error(f"[API Unhandled] {exc.__class__.__name__}: {exc}", exc_info=exc)
        response = Response(
            {
                "error": "server_error",
                "message": "An unexpected server error occurred. Our team has been notified.",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response


# ============================================================
# TeleCRM-Specific Exceptions
# ============================================================

class TeleCRMBaseException(APIException):
    """Base class for all TeleCRM custom exceptions."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "telecrm_error"
    default_detail = "A TeleCRM error occurred."


class TenantSuspendedException(TeleCRMBaseException):
    """Raised when a suspended tenant tries to access the platform."""
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "account_suspended"
    default_detail = (
        "Your account has been suspended. "
        "Please contact support at support@telecrm.in"
    )


class FeatureNotEnabledException(TeleCRMBaseException):
    """Raised when a tenant tries to use a feature not in their plan."""
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "feature_not_enabled"
    default_detail = "This feature is not available on your current plan. Please upgrade."

    def __init__(self, feature_key: str = None, upgrade_url: str = "/crm/billing/"):
        super().__init__()
        self.feature_key = feature_key
        self.upgrade_url = upgrade_url

    def get_full_details(self):
        return {
            "error": self.default_code,
            "message": str(self.default_detail),
            "feature_key": self.feature_key,
            "upgrade_url": self.upgrade_url,
        }


class PlanLimitExceededException(TeleCRMBaseException):
    """Raised when a tenant exceeds their plan limits (e.g., agent count, leads)."""
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_code = "plan_limit_exceeded"
    default_detail = "You have reached the limit for your current plan. Please upgrade."

    def __init__(self, limit_type: str, current: int, max_allowed: int):
        self.limit_type = limit_type
        self.current = current
        self.max_allowed = max_allowed
        detail = (
            f"Plan limit exceeded: {limit_type}. "
            f"Current: {current}, Maximum allowed: {max_allowed}. "
            f"Please upgrade your plan."
        )
        super().__init__(detail=detail)


class InvalidPhoneNumberException(TeleCRMBaseException):
    """Raised when an Indian phone number fails validation."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_phone_number"
    default_detail = "Invalid Indian phone number format. Please provide a valid 10-digit mobile number."


class DuplicateLeadException(TeleCRMBaseException):
    """Raised when a lead with the same phone already exists."""
    status_code = status.HTTP_409_CONFLICT
    default_code = "duplicate_lead"
    default_detail = "A lead with this phone number already exists."

    def __init__(self, phone: str = None, existing_lead_id=None):
        self.phone = phone
        self.existing_lead_id = existing_lead_id
        super().__init__()


class TRAIDNDBlockedException(TeleCRMBaseException):
    """Raised when a phone number is registered in TRAI's DND registry."""
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "trai_dnd_blocked"
    default_detail = (
        "This number is registered in TRAI's Do Not Disturb (DND) registry. "
        "Communication may be restricted per TRAI regulations."
    )


class WebhookValidationException(TeleCRMBaseException):
    """Raised when a webhook signature validation fails."""
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "webhook_validation_failed"
    default_detail = "Webhook signature validation failed."


class TenantNotFoundException(TeleCRMBaseException):
    """Raised when tenant lookup fails in a Celery task."""
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "tenant_not_found"
    default_detail = "Tenant not found."


class AgentNotFoundException(TeleCRMBaseException):
    """Raised when agent lookup fails."""
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "agent_not_found"
    default_detail = "Agent not found or inactive."


class InvalidCredentialsException(TeleCRMBaseException):
    """Raised on login failure — intentionally vague to prevent user enumeration."""
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "invalid_credentials"
    default_detail = "Invalid email or password. Please try again."


class TokenExpiredException(TeleCRMBaseException):
    """Raised when JWT token has expired."""
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "token_expired"
    default_detail = "Your session has expired. Please log in again."


class RazorpayException(TeleCRMBaseException):
    """Raised when Razorpay API call fails."""
    status_code = status.HTTP_502_BAD_GATEWAY
    default_code = "payment_gateway_error"
    default_detail = "Payment gateway error. Please try again later."

    def __init__(self, razorpay_error: str = None):
        self.razorpay_error = razorpay_error
        super().__init__()


class BulkOperationException(TeleCRMBaseException):
    """Raised when a bulk operation (WhatsApp/SMS/Email campaign) fails partially."""
    status_code = status.HTTP_207_MULTI_STATUS
    default_code = "bulk_operation_partial_failure"
    default_detail = "Some items in the bulk operation failed."

    def __init__(self, succeeded: int, failed: int, errors: list = None):
        self.succeeded = succeeded
        self.failed = failed
        self.errors = errors or []
        detail = f"Bulk operation completed with {succeeded} successes and {failed} failures."
        super().__init__(detail=detail)


class ImportException(TeleCRMBaseException):
    """Raised when CSV/Excel import fails."""
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "import_error"
    default_detail = "File import failed."

    def __init__(self, row_errors: list = None, message: str = None):
        self.row_errors = row_errors or []
        super().__init__(detail=message or self.default_detail)
