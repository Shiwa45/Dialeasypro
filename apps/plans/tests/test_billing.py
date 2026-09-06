"""
TeleCRM Backend — apps/plans/tests/test_billing.py

Razorpay webhook handling. These are money and GST-filing paths, and their
failure mode was silence: the webhook returns 200 to stop Razorpay retrying, so
a handler that raised looked identical to one that succeeded.
"""
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

import pytest

from apps.core.utils import calculate_gst, gst_from_inclusive


# ============================================================
# GST split
# ============================================================

def test_inclusive_split_reconciles_with_the_amount_charged():
    """
    The invoice must document the payment, not exceed it. calculate_gst() adds
    tax on top of a pre-tax figure; feeding it a Razorpay charge produced an
    invoice 18% larger than the money actually taken.
    """
    gst = gst_from_inclusive(Decimal("2949.82"), "MH")
    assert gst["total_amount"] == Decimal("2949.82")
    assert gst["base_amount"] + gst["total_gst"] == Decimal("2949.82")


def test_intrastate_splits_cgst_and_sgst_to_the_paisa():
    gst = gst_from_inclusive(Decimal("1180.00"), "MH")
    assert gst["is_interstate"] is False
    assert gst["cgst_amount"] + gst["sgst_amount"] == gst["total_gst"]
    assert gst["igst_amount"] == Decimal("0.00")
    assert gst["base_amount"] == Decimal("1000.00")


def test_interstate_uses_igst_only():
    gst = gst_from_inclusive(Decimal("1180.00"), "DL")
    assert gst["is_interstate"] is True
    assert gst["igst_amount"] == Decimal("180.00")
    assert gst["cgst_amount"] == Decimal("0.00")
    assert gst["sgst_amount"] == Decimal("0.00")


def test_odd_paisa_never_breaks_the_reconciliation():
    """A split that does not sum back to the payment is a filing problem."""
    for amount in ["999.99", "1.01", "12345.67", "0.03"]:
        gst = gst_from_inclusive(Decimal(amount), "MH")
        assert gst["base_amount"] + gst["cgst_amount"] + gst["sgst_amount"] == Decimal(amount), amount


def test_the_two_directions_are_inverses():
    added = calculate_gst(Decimal("1000.00"), "MH")
    split = gst_from_inclusive(added["total_amount"], "MH")
    assert split["base_amount"] == Decimal("1000.00")


# ============================================================
# The crash that swallowed every recurring payment
# ============================================================

def test_period_timestamps_convert_without_django_utc():
    """
    django.utils.timezone.utc was removed in Django 5.0 and this runs 5.1, so
    the charge handler raised AttributeError before it could activate anything.
    Pinning the stdlib conversion the handler now uses.
    """
    from django.utils import timezone as django_tz

    assert not hasattr(django_tz, "utc"), (
        "Django re-added timezone.utc — revisit the webhook conversion"
    )
    converted = datetime.fromtimestamp(1767225600, tz=dt_timezone.utc)
    assert converted.tzinfo is not None


def test_webhook_module_does_not_use_the_removed_alias():
    import inspect

    from apps.plans import webhooks

    # Match the call, not the word: the module explains the bug in a comment
    # that necessarily names the removed alias.
    source = inspect.getsource(webhooks)
    assert "tz=timezone.utc" not in source, (
        "django.utils.timezone.utc does not exist in Django 5.x"
    )
    assert "timezone.datetime.fromtimestamp" not in source


# ============================================================
# Idempotency
# ============================================================

@pytest.fixture
def subscription(db):
    """A tenant on a plan with a Razorpay subscription id."""
    from apps.plans.models import Plan, Subscription
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(schema_name="test_tenant").first()
    tenant.state = "MH"
    tenant.save(update_fields=["state"])

    plan = Plan.objects.filter(slug="starter").first() or Plan.objects.create(
        name="Billing Test Plan", slug="starter", price_monthly=Decimal("2499.00"),
    )
    return Subscription.objects.create(
        tenant=tenant, plan=plan, status="active",
        razorpay_subscription_id="sub_test_1",
    )


@pytest.mark.django_db
def test_a_charge_invoices_exactly_what_was_paid(subscription):
    from apps.plans.webhooks import _create_invoice_for_subscription

    invoice = _create_invoice_for_subscription(
        subscription, "pay_1", {"amount": 294982},  # paise, tax-inclusive
    )
    assert invoice.total_amount == Decimal("2949.82")
    components = (
        invoice.base_amount + invoice.cgst_amount
        + invoice.sgst_amount + invoice.igst_amount
    )
    assert components == Decimal("2949.82")


@pytest.mark.django_db
def test_a_redelivered_charge_does_not_raise_a_second_invoice(subscription):
    """
    Razorpay retries until it gets a 2xx and redelivers besides. Each retry
    used to mint another sequential GST invoice for one payment — a filing
    problem that cannot be quietly deleted afterwards.
    """
    from apps.plans.models import Invoice
    from apps.plans.webhooks import RazorpayWebhookView

    entity = {
        "subscription": {"entity": {
            "id": "sub_test_1", "current_start": 1767225600, "current_end": 1769904000,
        }},
        "payment": {"entity": {"id": "pay_dup", "amount": 294982}},
    }

    view = RazorpayWebhookView()
    view._handle_subscription_charged(entity)
    view._handle_subscription_charged(entity)  # Razorpay retry

    assert Invoice.objects.filter(razorpay_payment_id="pay_dup").count() == 1


@pytest.mark.django_db
def test_a_charge_activates_the_subscription_and_the_tenant(subscription):
    """
    All of this sat behind the AttributeError: subscriptions were never marked
    active and suspended tenants were never re-enabled after paying.
    """
    from apps.core.constants import SubscriptionStatus
    from apps.plans.webhooks import RazorpayWebhookView

    subscription.status = SubscriptionStatus.PAST_DUE
    subscription.save(update_fields=["status"])
    subscription.tenant.is_active = False
    subscription.tenant.save(update_fields=["is_active"])

    RazorpayWebhookView()._handle_subscription_charged({
        "subscription": {"entity": {
            "id": "sub_test_1", "current_start": 1767225600, "current_end": 1769904000,
        }},
        "payment": {"entity": {"id": "pay_activate", "amount": 294982}},
    })

    subscription.refresh_from_db()
    subscription.tenant.refresh_from_db()
    assert subscription.status == SubscriptionStatus.ACTIVE
    assert subscription.tenant.is_active is True
    assert subscription.current_period_start is not None


@pytest.mark.django_db
def test_an_unsigned_webhook_is_rejected(client):
    """Fail closed: no signature, no processing."""
    response = client.post(
        "/webhooks/razorpay/", data="{}", content_type="application/json",
    )
    assert response.status_code in (400, 401, 404)
