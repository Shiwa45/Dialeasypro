"""
TeleCRM Backend — apps/plans/services.py

Razorpay integration service.
Handles subscription creation, cancellation, payment verification,
and invoice generation for Indian GST compliance.
"""
import hashlib
import hmac
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class RazorpayService:
    """
    Wrapper around Razorpay Python SDK.
    All plan billing operations go through this class.

    Usage:
        from apps.plans.services import RazorpayService
        rp = RazorpayService()
        subscription_id = rp.create_subscription(plan, tenant, billing_cycle)
    """

    def __init__(self):
        import razorpay
        self.client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )

    def create_subscription(
        self,
        plan,
        tenant,
        billing_cycle: str = "monthly",
        total_count: int = 12,
    ) -> dict:
        """
        Create a Razorpay subscription for a tenant.

        Args:
            plan: Plan model instance
            tenant: Tenant model instance
            billing_cycle: 'monthly' or 'yearly'
            total_count: Number of billing cycles (12 = 1 year of monthly)

        Returns:
            dict with razorpay_subscription_id and short_url
        """
        razorpay_plan_id = (
            plan.razorpay_monthly_plan_id
            if billing_cycle == "monthly"
            else plan.razorpay_yearly_plan_id
        )

        if not razorpay_plan_id:
            raise ValueError(
                f"Razorpay plan ID not configured for {plan.name} ({billing_cycle}). "
                "Please set it in the admin panel."
            )

        try:
            subscription_data = {
                "plan_id": razorpay_plan_id,
                "total_count": total_count,
                "quantity": 1,
                "customer_notify": 1,
                "notes": {
                    "tenant_schema": tenant.schema_name,
                    "company_name": tenant.company_name,
                    "plan_name": plan.name,
                    "billing_cycle": billing_cycle,
                },
            }

            response = self.client.subscription.create(subscription_data)
            logger.info(
                f"[Razorpay] Subscription created: {response['id']} "
                f"for tenant {tenant.schema_name}"
            )
            return {
                "subscription_id": response["id"],
                "short_url": response.get("short_url", ""),
                "status": response["status"],
            }

        except Exception as exc:
            logger.error(
                f"[Razorpay] Failed to create subscription for {tenant.schema_name}: {exc}"
            )
            raise

    def cancel_subscription(
        self,
        razorpay_subscription_id: str,
        cancel_at_cycle_end: bool = True,
    ) -> dict:
        """
        Cancel a Razorpay subscription.

        Args:
            cancel_at_cycle_end: If True, cancel at end of current billing cycle.
                                 If False, cancel immediately.
        """
        try:
            response = self.client.subscription.cancel(
                razorpay_subscription_id,
                {"cancel_at_cycle_end": 1 if cancel_at_cycle_end else 0},
            )
            logger.info(f"[Razorpay] Subscription cancelled: {razorpay_subscription_id}")
            return response
        except Exception as exc:
            logger.error(
                f"[Razorpay] Failed to cancel subscription {razorpay_subscription_id}: {exc}"
            )
            raise

    def verify_payment_signature(
        self,
        razorpay_payment_id: str,
        razorpay_subscription_id: str,
        razorpay_signature: str,
    ) -> bool:
        """
        Verify the Razorpay payment signature to prevent forgery.
        Must be called before marking any payment as successful.
        """
        try:
            self.client.utility.verify_subscription_payment_signature(
                {
                    "razorpay_payment_id": razorpay_payment_id,
                    "razorpay_subscription_id": razorpay_subscription_id,
                    "razorpay_signature": razorpay_signature,
                }
            )
            return True
        except Exception:
            return False

    def verify_webhook_signature(
        self, body: bytes, signature: str, secret: str = None
    ) -> bool:
        """
        Verify Razorpay webhook signature.
        Called in RazorpayWebhookView before processing any webhook.
        """
        if secret is None:
            secret = settings.RAZORPAY_WEBHOOK_SECRET
        try:
            expected = hmac.new(
                secret.encode("utf-8"), body, hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(expected, signature)
        except Exception:
            return False

    def get_subscription(self, razorpay_subscription_id: str) -> dict:
        """Fetch subscription details from Razorpay."""
        return self.client.subscription.fetch(razorpay_subscription_id)

    def fetch_payment(self, razorpay_payment_id: str) -> dict:
        """Fetch payment details from Razorpay."""
        return self.client.payment.fetch(razorpay_payment_id)

    def create_customer(self, tenant) -> str:
        """Create or fetch a Razorpay customer for a tenant."""
        try:
            response = self.client.customer.create(
                {
                    "name": tenant.primary_contact_name,
                    "email": tenant.primary_contact_email,
                    "contact": tenant.primary_contact_phone.replace("+91", ""),
                    "notes": {
                        "tenant_schema": tenant.schema_name,
                        "gstin": tenant.gstin,
                    },
                }
            )
            return response["id"]
        except Exception as exc:
            logger.error(f"[Razorpay] Failed to create customer: {exc}")
            raise
