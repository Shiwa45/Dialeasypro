"""
TeleCRM Backend — apps/erp/services/documents.py

Line pricing, document totals, and the quote → order → invoice lifecycle.

Every document's totals are recomputed from its lines rather than trusted from
the client. Once an invoice is ISSUED it becomes a legal record: it can be
cancelled, but never edited or renumbered.
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.erp import gst
from apps.erp.constants import (
    DocumentType,
    InvoiceStatus,
    QuotationStatus,
    SalesOrderStatus,
)
from apps.erp.models import (
    CustomerInvoice,
    CustomerInvoiceItem,
    Payment,
    Quotation,
    QuotationItem,
    SalesOrder,
    SalesOrderItem,
)
from apps.erp.services.numbering import next_number

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")


def seller_state_for_tenant() -> tuple[str, str]:
    """(state_code, gstin) of the tenant issuing the document."""
    from django.db import connection

    from apps.tenants.models import Tenant

    try:
        tenant = Tenant.objects.get(schema_name=connection.schema_name)
        return (tenant.state or "").upper(), tenant.gstin or ""
    except Tenant.DoesNotExist:
        return "", ""


def price_line(item, *, seller_state: str, buyer_state: str):
    """Compute one line's taxable value and tax split, in place. Does not save."""
    item.taxable_value = gst.line_taxable_value(
        item.quantity, item.unit_price, item.discount_percent
    )
    split = gst.split_gst(
        item.taxable_value, item.gst_rate,
        seller_state=seller_state, buyer_state=buyer_state,
    )
    item.cgst_amount = split["cgst_amount"]
    item.sgst_amount = split["sgst_amount"]
    item.igst_amount = split["igst_amount"]
    item.line_total = gst.q2(item.taxable_value + split["tax_amount"])
    return split["is_interstate"]


def recalculate(document, items_qs) -> None:
    """
    Re-price every line and roll totals up onto the document. Saves both.
    The document's stored seller/buyer state is authoritative.
    """
    seller_state = document.seller_state or ""
    buyer_state = document.buyer_state or ""

    interstate = False
    lines = []
    for item in items_qs:
        interstate = price_line(item, seller_state=seller_state, buyer_state=buyer_state) or interstate
        item.save(update_fields=[
            "taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "line_total"
        ])
        lines.append({
            "taxable_value": item.taxable_value,
            "cgst_amount": item.cgst_amount,
            "sgst_amount": item.sgst_amount,
            "igst_amount": item.igst_amount,
        })

    totals = gst.summarize(lines) if lines else {
        "subtotal": ZERO, "cgst_amount": ZERO, "sgst_amount": ZERO, "igst_amount": ZERO,
        "total_tax": ZERO, "round_off": ZERO, "total_amount": ZERO,
    }

    document.is_interstate = interstate
    document.subtotal = totals["subtotal"]
    document.cgst_amount = totals["cgst_amount"]
    document.sgst_amount = totals["sgst_amount"]
    document.igst_amount = totals["igst_amount"]
    document.total_tax = totals["total_tax"]
    document.round_off = totals["round_off"]
    document.total_amount = totals["total_amount"]
    document.save(update_fields=[
        "is_interstate", "subtotal", "cgst_amount", "sgst_amount", "igst_amount",
        "total_tax", "round_off", "total_amount", "updated_at",
    ])


def _snapshot_item(source, target_cls, **fk):
    """Copy a line from one document type to another, preserving pricing."""
    return target_cls(
        product=source.product,
        description=source.description,
        hsn_sac=source.hsn_sac,
        quantity=source.quantity,
        unit_price=source.unit_price,
        discount_percent=source.discount_percent,
        gst_rate=source.gst_rate,
        **fk,
    )


# ============================================================
# Creation
# ============================================================

@transaction.atomic
def create_quotation(*, customer, created_by=None, **fields) -> Quotation:
    seller_state, _ = seller_state_for_tenant()
    return Quotation.objects.create(
        number=next_number(DocumentType.QUOTATION),
        customer=customer,
        created_by=created_by,
        seller_state=seller_state,
        buyer_state=(customer.state_code or "").upper(),
        **fields,
    )


# ============================================================
# Conversions
# ============================================================

@transaction.atomic
def quotation_to_order(quotation: Quotation, *, created_by=None) -> SalesOrder:
    """Accept a quotation and open a sales order from it."""
    if quotation.status == QuotationStatus.CONVERTED:
        raise ValueError(f"{quotation.number} has already been converted.")
    if quotation.status in (QuotationStatus.REJECTED, QuotationStatus.EXPIRED):
        raise ValueError(f"Cannot convert a {quotation.status} quotation.")
    if not quotation.items.exists():
        raise ValueError("Cannot convert a quotation with no line items.")

    order = SalesOrder.objects.create(
        number=next_number(DocumentType.SALES_ORDER),
        customer=quotation.customer,
        quotation=quotation,
        created_by=created_by,
        seller_state=quotation.seller_state,
        buyer_state=quotation.buyer_state,
        notes=quotation.notes,
    )
    SalesOrderItem.objects.bulk_create([
        _snapshot_item(i, SalesOrderItem, order=order) for i in quotation.items.all()
    ])
    recalculate(order, order.items.all())

    quotation.status = QuotationStatus.CONVERTED
    quotation.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def order_to_invoice(order: SalesOrder, *, created_by=None, due_date=None) -> CustomerInvoice:
    """Raise a DRAFT invoice from a sales order. Issue it separately."""
    if order.status == SalesOrderStatus.CANCELLED:
        raise ValueError("Cannot invoice a cancelled order.")
    if order.invoices.exclude(status=InvoiceStatus.CANCELLED).exists():
        raise ValueError(f"{order.number} already has an active invoice.")
    if not order.items.exists():
        raise ValueError("Cannot invoice an order with no line items.")

    customer = order.customer
    _, seller_gstin = seller_state_for_tenant()

    invoice = CustomerInvoice.objects.create(
        number=next_number(DocumentType.INVOICE),
        customer=customer,
        sales_order=order,
        created_by=created_by,
        seller_state=order.seller_state,
        buyer_state=order.buyer_state,
        seller_gstin=seller_gstin,
        buyer_gstin=customer.gstin,
        billing_address_snapshot=customer.billing_address,
        due_date=due_date,
        notes=order.notes,
    )
    CustomerInvoiceItem.objects.bulk_create([
        _snapshot_item(i, CustomerInvoiceItem, invoice=invoice) for i in order.items.all()
    ])
    recalculate(invoice, invoice.items.all())

    order.status = SalesOrderStatus.INVOICED
    order.save(update_fields=["status", "updated_at"])
    return invoice


# ============================================================
# Invoice lifecycle
# ============================================================

@transaction.atomic
def issue_invoice(invoice: CustomerInvoice) -> CustomerInvoice:
    """
    Move DRAFT → ISSUED. After this the invoice is a legal document: no edits,
    no renumbering, no deletion — only cancellation.
    """
    if invoice.status != InvoiceStatus.DRAFT:
        raise ValueError(f"Only a draft invoice can be issued (this one is {invoice.status}).")
    if not invoice.items.exists():
        raise ValueError("Cannot issue an invoice with no line items.")

    # Freeze the figures against the lines as they stand right now.
    recalculate(invoice, invoice.items.all())
    invoice.refresh_from_db()

    if invoice.total_amount <= 0:
        raise ValueError("Cannot issue a zero-value invoice.")

    invoice.status = InvoiceStatus.ISSUED
    invoice.issued_at = timezone.now()
    invoice.save(update_fields=["status", "issued_at", "updated_at"])
    return invoice


@transaction.atomic
def cancel_invoice(invoice: CustomerInvoice, reason: str = "") -> CustomerInvoice:
    if invoice.status == InvoiceStatus.CANCELLED:
        return invoice
    if invoice.amount_paid > 0:
        raise ValueError(
            "Cannot cancel an invoice with payments recorded — refund and issue a credit note."
        )
    invoice.status = InvoiceStatus.CANCELLED
    invoice.cancelled_at = timezone.now()
    invoice.cancellation_reason = reason[:300]
    invoice.save(update_fields=["status", "cancelled_at", "cancellation_reason", "updated_at"])
    return invoice


@transaction.atomic
def record_payment(invoice: CustomerInvoice, *, amount: Decimal, recorded_by=None, **fields) -> Payment:
    """Record a receipt and advance the invoice's payment status."""
    if invoice.status == InvoiceStatus.CANCELLED:
        raise ValueError("Cannot record a payment against a cancelled invoice.")
    if invoice.status == InvoiceStatus.DRAFT:
        raise ValueError("Issue the invoice before recording payments.")

    amount = gst.q2(amount)
    if amount <= 0:
        raise ValueError("Payment amount must be positive.")

    # Lock the invoice so two concurrent payments can't both see the old balance
    # and jointly overshoot the total.
    locked = CustomerInvoice.objects.select_for_update().get(pk=invoice.pk)
    if amount > locked.amount_due:
        raise ValueError(
            f"Payment ₹{amount} exceeds the outstanding balance of ₹{locked.amount_due}."
        )

    payment = Payment.objects.create(
        invoice=locked, amount=amount, recorded_by=recorded_by, **fields
    )

    locked.amount_paid = gst.q2(locked.amount_paid + amount)
    locked.status = (
        InvoiceStatus.PAID if locked.amount_due <= 0 else InvoiceStatus.PARTIALLY_PAID
    )
    locked.save(update_fields=["amount_paid", "status", "updated_at"])
    return payment
