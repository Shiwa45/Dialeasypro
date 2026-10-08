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

    # From the two places of supply, not from the lines: a quotation with no
    # lines yet used to say "Intra-state" for an out-of-state buyer.
    interstate = gst.is_interstate(seller_state, buyer_state)
    lines = []
    for item in items_qs:
        price_line(item, seller_state=seller_state, buyer_state=buyer_state)
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
    buyer_state = (customer.state_code or "").upper()
    # Leave out anything not given so model defaults apply: passing
    # quotation_date=None explicitly overrode the default and violated NOT
    # NULL — every quotation created from the web app failed with a 500.
    fields = {k: v for k, v in fields.items() if v is not None}
    return Quotation.objects.create(
        number=next_number(DocumentType.QUOTATION, on=fields.get("quotation_date")),
        customer=customer,
        created_by=created_by,
        seller_state=seller_state,
        buyer_state=buyer_state,
        is_interstate=gst.is_interstate(seller_state, buyer_state),
        **fields,
    )


def draft_number() -> str:
    """
    A placeholder number for a DRAFT invoice.

    GST invoice numbers must run without gaps, and a draft can be deleted. So
    the real number is taken from the sequence only when the invoice is
    ISSUED (issue_invoice); a draft carries this until then. Drafts raised
    from an order used to take a real number, and deleting one left a hole.
    """
    import uuid

    return f"DRAFT-{uuid.uuid4().hex[:12].upper()}"


def is_draft_number(number: str) -> bool:
    return (number or "").startswith("DRAFT-")


def create_invoice(*, customer, created_by=None, **fields) -> CustomerInvoice:
    """
    Open a DRAFT invoice with no sales order behind it.

    Not every sale walks the quotation → order → invoice path: an over-the-
    counter sale, a one-off service charge or a correction invoice starts here.
    Until this existed, an invoice could ONLY be born from an order, so those
    cases had to be faked by raising a throwaway quotation and converting it
    twice — which left two bogus documents in the numbering sequence.

    GSTIN and the billing address are snapshotted the same way order_to_invoice
    does it, so a reissued PDF still matches what the customer received even if
    the customer master is edited later.
    """
    seller_state, seller_gstin = seller_state_for_tenant()
    buyer_state = (customer.state_code or "").upper()
    fields = {k: v for k, v in fields.items() if v is not None or k == "due_date"}
    return CustomerInvoice.objects.create(
        number=draft_number(),
        customer=customer,
        created_by=created_by,
        seller_state=seller_state,
        buyer_state=buyer_state,
        is_interstate=gst.is_interstate(seller_state, buyer_state),
        seller_gstin=seller_gstin,
        buyer_gstin=customer.gstin,
        billing_address_snapshot=customer.billing_address,
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
    if (
        quotation.status != QuotationStatus.ACCEPTED
        and quotation.valid_until and quotation.valid_until < timezone.localdate()
    ):
        raise ValueError(
            f"This quotation lapsed on {quotation.valid_until:%d %b %Y}. Revise its validity, "
            "or record the customer's acceptance first."
        )

    order = SalesOrder.objects.create(
        number=next_number(DocumentType.SALES_ORDER),
        is_interstate=quotation.is_interstate,
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
        number=draft_number(),
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
    invoice = CustomerInvoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != InvoiceStatus.DRAFT:
        raise ValueError(f"Only a draft invoice can be issued (this one is {invoice.status}).")
    if not invoice.items.exists():
        raise ValueError("Cannot issue an invoice with no line items.")

    # A tax invoice must carry the supplier's GSTIN. One was issued with none
    # because nothing checked; take it from the company profile now, at issue.
    seller_state, seller_gstin = seller_state_for_tenant()
    if not seller_gstin:
        raise ValueError(
            "Add your company's GSTIN (Settings → Company profile) before issuing a tax invoice."
        )
    invoice.seller_gstin = seller_gstin
    if not invoice.seller_state:
        invoice.seller_state = seller_state
    if not invoice.buyer_state and invoice.buyer_gstin:
        from apps.erp.gstin import state_from_gstin
        invoice.buyer_state = state_from_gstin(invoice.buyer_gstin)
    invoice.save(update_fields=["seller_gstin", "seller_state", "buyer_state", "updated_at"])

    # Freeze the figures against the lines as they stand right now.
    recalculate(invoice, invoice.items.all())
    invoice.refresh_from_db()

    if invoice.total_amount <= 0:
        raise ValueError("Cannot issue a zero-value invoice.")

    # The GST number is taken only now (see draft_number).
    if is_draft_number(invoice.number):
        invoice.number = next_number(DocumentType.INVOICE, on=invoice.invoice_date)
    invoice.status = InvoiceStatus.ISSUED
    invoice.issued_at = timezone.now()
    invoice.save(update_fields=["number", "status", "issued_at", "updated_at"])
    _move_stock(invoice, direction=-1)
    return invoice


def _move_stock(invoice: CustomerInvoice, *, direction: int) -> None:
    """
    Take stock out when an invoice is issued (direction -1), put it back when
    an issued invoice is cancelled (+1). Only stock-tracked goods move.
    Nothing used to touch stock_quantity, so stock never went down.
    """
    from django.db.models import F

    from apps.erp.models import Product

    for item in invoice.items.select_related("product"):
        product = item.product
        if product is None or not product.track_stock or product.is_service:
            continue
        Product.objects.filter(pk=product.pk).update(
            stock_quantity=F("stock_quantity") + direction * item.quantity
        )


@transaction.atomic
def cancel_invoice(invoice: CustomerInvoice, reason: str = "") -> CustomerInvoice:
    # The same lock record_payment takes, so a payment and a cancellation
    # cannot both pass their checks on stale copies of the invoice.
    invoice = CustomerInvoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status == InvoiceStatus.CANCELLED:
        return invoice
    if invoice.status == InvoiceStatus.DRAFT:
        raise ValueError("A draft has no GST number yet — delete it instead of cancelling.")
    if invoice.amount_paid > 0:
        raise ValueError(
            "This invoice has payments recorded. Remove them first (open the invoice → "
            "Payments received → Remove), then cancel."
        )
    if not (reason or "").strip():
        raise ValueError("Give a reason for cancelling — it is kept with the invoice.")
    was_issued = invoice.issued_at is not None
    invoice.status = InvoiceStatus.CANCELLED
    invoice.cancelled_at = timezone.now()
    invoice.cancellation_reason = reason.strip()[:300]
    invoice.save(update_fields=["status", "cancelled_at", "cancellation_reason", "updated_at"])
    if was_issued:
        _move_stock(invoice, direction=+1)
    # The order it came from can be invoiced again, so it is open again — it
    # used to keep saying INVOICED.
    order = invoice.sales_order
    if order is not None and order.status == SalesOrderStatus.INVOICED and not order.invoices.exclude(
        status=InvoiceStatus.CANCELLED
    ).exists():
        order.status = SalesOrderStatus.OPEN
        order.save(update_fields=["status", "updated_at"])
    return invoice


@transaction.atomic
def delete_draft_invoice(invoice: CustomerInvoice) -> None:
    """Delete a draft and reopen the order it was raised from."""
    if invoice.status != InvoiceStatus.DRAFT:
        raise ValueError(
            f"An {invoice.status} invoice cannot be deleted — cancel it instead, "
            "which keeps its number in the GST sequence."
        )
    order = invoice.sales_order
    invoice.delete()
    if order is not None and order.status == SalesOrderStatus.INVOICED and not order.invoices.exclude(
        status=InvoiceStatus.CANCELLED
    ).exists():
        order.status = SalesOrderStatus.OPEN
        order.save(update_fields=["status", "updated_at"])


@transaction.atomic
def cancel_order(order: SalesOrder, reason: str = "") -> SalesOrder:
    order = SalesOrder.objects.select_for_update().get(pk=order.pk)
    if order.status == SalesOrderStatus.CANCELLED:
        return order
    if order.invoices.exclude(status=InvoiceStatus.CANCELLED).exists():
        raise ValueError("This order has an invoice. Cancel or delete the invoice first.")
    order.status = SalesOrderStatus.CANCELLED
    if reason:
        order.notes = (order.notes + f"\n[Cancelled] {reason}").strip()[:2000]
    order.save(update_fields=["status", "notes", "updated_at"])
    return order


@transaction.atomic
def reverse_payment(payment: Payment) -> CustomerInvoice:
    """
    Remove a wrongly recorded payment and put the invoice's balance back.
    There was no way to undo a payment at all.
    """
    invoice = CustomerInvoice.objects.select_for_update().get(pk=payment.invoice_id)
    if invoice.status == InvoiceStatus.CANCELLED:
        raise ValueError("The invoice is cancelled; its payments can't be changed.")
    amount = payment.amount
    payment.delete()
    invoice.amount_paid = max(ZERO, gst.q2(invoice.amount_paid - amount))
    if invoice.amount_paid <= 0:
        invoice.status = InvoiceStatus.ISSUED
    elif invoice.amount_due > 0:
        invoice.status = InvoiceStatus.PARTIALLY_PAID
    else:
        invoice.status = InvoiceStatus.PAID
    invoice.save(update_fields=["amount_paid", "status", "updated_at"])
    return invoice


@transaction.atomic
def record_payment(invoice: CustomerInvoice, *, amount: Decimal, recorded_by=None, **fields) -> Payment:
    """Record a receipt and advance the invoice's payment status."""
    amount = gst.q2(amount)
    if amount <= 0:
        raise ValueError("Payment amount must be positive.")
    paid_on = fields.get("paid_on")
    if paid_on and paid_on > timezone.localdate():
        raise ValueError("A payment can't be dated in the future.")

    # Lock the invoice so two concurrent payments can't both see the old balance
    # and jointly overshoot the total — and check its status on the LOCKED row.
    # The checks used to run on the caller's copy before the lock, so a
    # cancellation landing in between was missed and a cancelled invoice took
    # a payment.
    locked = CustomerInvoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status == InvoiceStatus.CANCELLED:
        raise ValueError("Cannot record a payment against a cancelled invoice.")
    if locked.status == InvoiceStatus.DRAFT:
        raise ValueError("Issue the invoice before recording payments.")
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
