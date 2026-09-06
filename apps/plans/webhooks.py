"""
TeleCRM Backend — apps/plans/webhooks.py

Razorpay webhook endpoint.
Processes payment events from Razorpay and updates subscription/invoice status.

Registered at: /webhooks/razorpay/  (public URL conf)

Events handled:
  payment.captured       → Mark invoice paid, activate subscription
  subscription.charged   → Create invoice for recurring payment
  subscription.cancelled → Update subscription status
  subscription.halted    → Mark subscription past_due
  payment.failed         → Log payment failure
"""
import json
import logging
from datetime import datetime, timezone as dt_timezone

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.plans.services import RazorpayService

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class RazorpayWebhookView(View):
    """
    Razorpay webhook receiver.
    Validates signature before processing any event.
    """

    def post(self, request, *args, **kwargs):
        # ---- 1. Validate signature -------------------------
        signature = request.headers.get("X-Razorpay-Signature", "")
        if not signature:
            logger.warning("[Webhook] Missing Razorpay signature")
            return HttpResponse("Signature required", status=400)

        body = request.body
        rp = RazorpayService()

        if not rp.verify_webhook_signature(body, signature):
            logger.warning("[Webhook] Invalid Razorpay signature — rejecting")
            return HttpResponse("Invalid signature", status=401)

        # ---- 2. Parse event --------------------------------
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return HttpResponse("Invalid JSON", status=400)

        event = payload.get("event")
        entity = payload.get("payload", {})

        logger.info(f"[Webhook] Razorpay event: {event}")

        # ---- 3. Route to handler ---------------------------
        handlers = {
            "payment.captured": self._handle_payment_captured,
            "subscription.charged": self._handle_subscription_charged,
            "subscription.cancelled": self._handle_subscription_cancelled,
            "subscription.halted": self._handle_subscription_halted,
            "payment.failed": self._handle_payment_failed,
        }

        handler = handlers.get(event)
        if handler:
            try:
                handler(entity)
            except Exception as exc:
                logger.error(f"[Webhook] Handler failed for {event}: {exc}", exc_info=True)
                # Return 200 to prevent Razorpay from retrying (log and investigate)
                return JsonResponse({"status": "handler_error", "event": event})

        return JsonResponse({"status": "ok", "event": event})

    def _handle_payment_captured(self, entity: dict):
        """Payment captured — mark invoice as paid."""
        payment = entity.get("payment", {}).get("entity", {})
        payment_id = payment.get("id")
        order_id = payment.get("order_id")
        subscription_id = payment.get("subscription_id")

        if not payment_id:
            return

        from apps.plans.models import Invoice

        # Find matching invoice
        invoice = None
        if order_id:
            invoice = Invoice.objects.filter(razorpay_order_id=order_id).first()
        if not invoice and subscription_id:
            invoice = Invoice.objects.filter(
                subscription__razorpay_subscription_id=subscription_id,
                payment_status="pending",
            ).order_by("-created_at").first()

        if invoice:
            invoice.mark_paid(payment_id)
            logger.info(f"[Webhook] Invoice {invoice.invoice_number} marked paid")

    def _handle_subscription_charged(self, entity: dict):
        """Recurring subscription payment — create invoice."""
        subscription_data = entity.get("subscription", {}).get("entity", {})
        payment_data = entity.get("payment", {}).get("entity", {})

        sub_id = subscription_data.get("id")
        payment_id = payment_data.get("id")

        if not sub_id:
            return

        from apps.plans.models import Subscription

        try:
            subscription = Subscription.objects.get(razorpay_subscription_id=sub_id)
        except Subscription.DoesNotExist:
            logger.warning(f"[Webhook] Subscription not found: {sub_id}")
            return

        # Update subscription period dates.
        #
        # django.utils.timezone.utc was removed in Django 5.0, and this runs
        # 5.1 — so this block raised AttributeError on EVERY subscription.charged
        # event. The handler's except returns 200 to stop Razorpay retrying, so
        # the failure was completely silent: subscriptions were never marked
        # active, tenants never re-enabled, and no invoice was ever raised for a
        # recurring payment. Use the stdlib UTC.
        current_start = subscription_data.get("current_start")
        current_end = subscription_data.get("current_end")
        if current_start:
            subscription.current_period_start = datetime.fromtimestamp(
                current_start, tz=dt_timezone.utc
            )
        if current_end:
            subscription.current_period_end = datetime.fromtimestamp(
                current_end, tz=dt_timezone.utc
            )

        from apps.core.constants import SubscriptionStatus
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.save(
            update_fields=["status", "current_period_start", "current_period_end"]
        )

        # Update tenant
        subscription.tenant.subscription_status = SubscriptionStatus.ACTIVE
        subscription.tenant.is_active = True
        subscription.tenant.save(update_fields=["subscription_status", "is_active"])

        # Create invoice for this charge — unless we already did.
        #
        # Razorpay retries a webhook until it gets a 2xx, and redelivers on its
        # own schedule besides. Without this check every retry raised a second
        # GST invoice for one payment, each with its own sequential number,
        # which is a filing problem that cannot be quietly deleted afterwards.
        from apps.plans.models import Invoice

        if payment_id and Invoice.objects.filter(razorpay_payment_id=payment_id).exists():
            logger.info(f"[Webhook] Invoice already exists for payment {payment_id} — skipping")
        else:
            _create_invoice_for_subscription(subscription, payment_id, payment_data)

        logger.info(
            f"[Webhook] Subscription charged: {sub_id} — payment: {payment_id}"
        )

    def _handle_subscription_cancelled(self, entity: dict):
        """Subscription cancelled — update status."""
        subscription_data = entity.get("subscription", {}).get("entity", {})
        sub_id = subscription_data.get("id")

        if not sub_id:
            return

        from apps.plans.models import Subscription
        from apps.core.constants import SubscriptionStatus

        try:
            subscription = Subscription.objects.get(razorpay_subscription_id=sub_id)
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.cancelled_at = timezone.now()
            subscription.save(update_fields=["status", "cancelled_at"])
            logger.info(f"[Webhook] Subscription cancelled: {sub_id}")
        except Subscription.DoesNotExist:
            logger.warning(f"[Webhook] Subscription not found for cancel: {sub_id}")

    def _handle_subscription_halted(self, entity: dict):
        """Subscription halted (payment failed repeatedly) — mark past_due."""
        subscription_data = entity.get("subscription", {}).get("entity", {})
        sub_id = subscription_data.get("id")

        if not sub_id:
            return

        from apps.plans.models import Subscription
        from apps.core.constants import SubscriptionStatus

        try:
            subscription = Subscription.objects.get(razorpay_subscription_id=sub_id)
            subscription.status = SubscriptionStatus.PAST_DUE
            subscription.save(update_fields=["status"])

            # Update tenant status
            subscription.tenant.subscription_status = SubscriptionStatus.PAST_DUE
            subscription.tenant.save(update_fields=["subscription_status"])

            logger.warning(f"[Webhook] Subscription halted: {sub_id}")
        except Subscription.DoesNotExist:
            pass

    def _handle_payment_failed(self, entity: dict):
        """Payment failed — log for monitoring."""
        payment = entity.get("payment", {}).get("entity", {})
        payment_id = payment.get("id")
        error_code = payment.get("error_code")
        error_description = payment.get("error_description")

        logger.warning(
            f"[Webhook] Payment failed: {payment_id} — "
            f"{error_code}: {error_description}"
        )


def _create_invoice_for_subscription(subscription, payment_id: str, payment_data: dict):
    """Helper to create a GST invoice when a subscription charge succeeds."""
    from decimal import Decimal

    from apps.core.utils import gst_from_inclusive
    from apps.plans.models import Invoice

    tenant = subscription.tenant
    plan = subscription.plan

    # Razorpay reports the amount the customer was actually charged, in paise.
    # That figure is tax-INCLUSIVE, so the invoice has to split it, not add
    # tax on top of it — calculate_gst() did the latter and produced invoices
    # 18% larger than the payment they document.
    amount_paise = payment_data.get("amount", 0)
    gross_rupees = Decimal(str(amount_paise)) / Decimal("100")

    customer_state = tenant.state or ""
    gst = gst_from_inclusive(gross_rupees, customer_state)

    invoice = Invoice(
        tenant=tenant,
        subscription=subscription,
        invoice_number=Invoice.generate_invoice_number(),
        base_amount=gst["base_amount"],
        cgst_rate=gst["cgst_rate"],
        sgst_rate=gst["sgst_rate"],
        igst_rate=gst["igst_rate"],
        cgst_amount=gst["cgst_amount"],
        sgst_amount=gst["sgst_amount"],
        igst_amount=gst["igst_amount"],
        total_amount=gst["total_amount"],
        is_interstate=gst["is_interstate"],
        customer_gstin=tenant.gstin,
        customer_state=customer_state,
        billing_name=tenant.company_name,
        billing_address_snapshot=f"{tenant.billing_address}, {tenant.city}, {tenant.state}",
        payment_status="paid",
        razorpay_payment_id=payment_id,
        paid_at=timezone.now(),
    )
    if subscription.current_period_start:
        invoice.billing_period_start = subscription.current_period_start.date()
    if subscription.current_period_end:
        invoice.billing_period_end = subscription.current_period_end.date()

    # invoice_number is unique and generated by reading the highest existing
    # one, so two webhooks landing together pick the same value and one of them
    # dies on the constraint. Retry with a freshly-read number rather than
    # losing the invoice for a payment that has already been taken.
    from django.db import IntegrityError

    for attempt in range(5):
        try:
            invoice.save()
            break
        except IntegrityError:
            if attempt == 4:
                logger.error(
                    f"[Invoice] Could not allocate a number for payment {payment_id}"
                )
                raise
            invoice.pk = None
            invoice.invoice_number = Invoice.generate_invoice_number()

    logger.info(f"[Invoice] Created: {invoice.invoice_number}")
    return invoice
