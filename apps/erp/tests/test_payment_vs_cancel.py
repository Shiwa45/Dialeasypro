"""
A payment cannot land on an invoice cancelled a moment earlier (LOW-13).

record_payment checked "cancelled?" on the caller's copy of the invoice,
before taking the row lock. A cancellation in between was missed and the
cancelled invoice took the payment.
"""
from decimal import Decimal

import pytest

from apps.erp.constants import InvoiceStatus
from apps.erp.models import Customer, CustomerInvoice
from apps.erp.services.documents import cancel_invoice, record_payment

pytestmark = pytest.mark.django_db


@pytest.fixture
def invoice():
    customer = Customer.objects.create(name="Acme")
    return CustomerInvoice.objects.create(
        number="INV-1", customer=customer, status=InvoiceStatus.ISSUED,
        total_amount=Decimal("1000.00"),
    )


def test_a_payment_after_a_concurrent_cancellation_is_refused(invoice):
    stale = CustomerInvoice.objects.get(pk=invoice.pk)  # the payment request's copy
    cancel_invoice(CustomerInvoice.objects.get(pk=invoice.pk), reason="duplicate")

    with pytest.raises(ValueError, match="cancelled"):
        record_payment(stale, amount=Decimal("500.00"))

    invoice.refresh_from_db()
    assert invoice.amount_paid == Decimal("0")


def test_a_cancellation_after_a_concurrent_payment_is_refused(invoice):
    stale = CustomerInvoice.objects.get(pk=invoice.pk)  # the cancel request's copy
    record_payment(CustomerInvoice.objects.get(pk=invoice.pk), amount=Decimal("500.00"))

    with pytest.raises(ValueError, match="payments recorded"):
        cancel_invoice(stale)

    invoice.refresh_from_db()
    assert invoice.status != InvoiceStatus.CANCELLED
