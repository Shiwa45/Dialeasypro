"""
TeleCRM Backend — apps/erp/models.py

ERP / Sales-ops add-on module. All models live in the TENANT schema.

Document lifecycle:  Quotation → SalesOrder → CustomerInvoice → Payment

Numbering
---------
GST law requires invoice numbers to be unique and consecutive within a
financial year. A naive `max(number) + 1` races under concurrency and can emit
duplicates, so numbers come from DocumentSequence rows taken under
`select_for_update()` — see services/numbering.py.

Money
-----
Totals are always derived from line items via apps/erp/gst.py and stored
denormalized on the document, so a historical invoice keeps the figures it was
issued with even if a product's price or GST rate later changes.
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.erp.constants import (
    DocumentType,
    InvoiceStatus,
    PaymentMode,
    QuotationStatus,
    SalesOrderStatus,
    UnitOfMeasure,
)

ZERO = Decimal("0.00")


class Customer(TimeStampedModel):
    """
    A billable buyer. Optionally linked to the CRM Lead it was won from, so a
    converted lead flows straight into quoting without re-keying.
    """

    name = models.CharField(max_length=200, db_index=True)
    lead = models.ForeignKey(
        "leads.Lead", on_delete=models.SET_NULL, null=True, blank=True, related_name="erp_customers"
    )
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=15, blank=True, default="")

    gstin = models.CharField(
        max_length=15, blank=True, default="", db_index=True,
        help_text="Buyer's GSTIN. Blank for unregistered (B2C) customers.",
    )
    state_code = models.CharField(
        max_length=2, blank=True, default="",
        help_text="2-letter state code — decides CGST+SGST vs IGST.",
    )
    billing_address = models.TextField(blank=True, default="")
    shipping_address = models.TextField(blank=True, default="")

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name}" + (f" ({self.gstin})" if self.gstin else "")


class Product(TimeStampedModel):
    """A sellable good or service. `gst_rate` drives the tax on every line."""

    name = models.CharField(max_length=200, db_index=True)
    sku = models.CharField(max_length=50, unique=True, db_index=True)
    description = models.TextField(blank=True, default="")

    hsn_sac = models.CharField(
        max_length=10, blank=True, default="",
        help_text="HSN code for goods, SAC for services. Required on GST invoices.",
    )
    is_service = models.BooleanField(default=False)
    unit = models.CharField(max_length=10, choices=UnitOfMeasure.CHOICES, default=UnitOfMeasure.NOS)

    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )
    gst_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("18.00"),
        help_text="GST slab: 0, 5, 12, 18 or 28.",
    )

    # Stock is tracked only for goods; services are always available.
    track_stock = models.BooleanField(default=False)
    stock_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.sku} — {self.name}"


class DocumentSequence(models.Model):
    """
    Per financial-year, per document-type counter. Locked with select_for_update
    when issuing a number so concurrent requests can never collide.
    """

    doc_type = models.CharField(max_length=20, choices=DocumentType.CHOICES)
    financial_year = models.CharField(max_length=7, help_text="e.g. 2026-27")
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("doc_type", "financial_year")

    def __str__(self):
        return f"{self.doc_type} {self.financial_year}: {self.last_number}"


# ============================================================
# Abstract bases
# ============================================================

class MoneyDocument(TimeStampedModel):
    """Denormalized totals shared by quotations, orders and invoices."""

    number = models.CharField(max_length=30, unique=True, db_index=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="+")

    # Snapshot of the seller/buyer place of supply at issue time.
    seller_state = models.CharField(max_length=2, blank=True, default="")
    buyer_state = models.CharField(max_length=2, blank=True, default="")
    is_interstate = models.BooleanField(default=False)

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    cgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    sgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    igst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    total_tax = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    round_off = models.DecimalField(max_digits=6, decimal_places=2, default=ZERO)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)

    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        abstract = True


class LineItem(models.Model):
    """A single priced row. Product details are snapshotted at add time."""

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    description = models.CharField(max_length=300, blank=True, default="")
    hsn_sac = models.CharField(max_length=10, blank=True, default="")

    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("18.00"))

    taxable_value = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    cgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    sgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    igst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.description or self.product_id} x{self.quantity}"


# ============================================================
# Quotation
# ============================================================

class Quotation(MoneyDocument):
    quotation_date = models.DateField(default=timezone.localdate)
    valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=15, choices=QuotationStatus.CHOICES, default=QuotationStatus.DRAFT, db_index=True
    )

    class Meta:
        ordering = ["-quotation_date", "-id"]

    def __str__(self):
        return self.number

    @property
    def is_editable(self) -> bool:
        return self.status in QuotationStatus.EDITABLE


class QuotationItem(LineItem):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="items")

    class Meta:
        ordering = ["id"]


# ============================================================
# Sales Order
# ============================================================

class SalesOrder(MoneyDocument):
    order_date = models.DateField(default=timezone.localdate)
    quotation = models.ForeignKey(
        Quotation, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales_orders"
    )
    status = models.CharField(
        max_length=15, choices=SalesOrderStatus.CHOICES, default=SalesOrderStatus.OPEN, db_index=True
    )
    expected_delivery = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-order_date", "-id"]

    def __str__(self):
        return self.number

    @property
    def is_editable(self) -> bool:
        return self.status in SalesOrderStatus.EDITABLE


class SalesOrderItem(LineItem):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="items")

    class Meta:
        ordering = ["id"]


# ============================================================
# Customer Invoice
# ============================================================

class CustomerInvoice(MoneyDocument):
    invoice_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices"
    )
    status = models.CharField(
        max_length=20, choices=InvoiceStatus.CHOICES, default=InvoiceStatus.DRAFT, db_index=True
    )

    # Snapshotted so a reissued PDF always matches what the customer received.
    seller_gstin = models.CharField(max_length=15, blank=True, default="")
    buyer_gstin = models.CharField(max_length=15, blank=True, default="")
    billing_address_snapshot = models.TextField(blank=True, default="")

    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    issued_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        ordering = ["-invoice_date", "-id"]
        indexes = [models.Index(fields=["status", "invoice_date"], name="erp_inv_status_date_idx")]

    def __str__(self):
        return self.number

    @property
    def is_editable(self) -> bool:
        return self.status in InvoiceStatus.EDITABLE

    @property
    def amount_due(self) -> Decimal:
        return max(ZERO, self.total_amount - self.amount_paid)


class CustomerInvoiceItem(LineItem):
    invoice = models.ForeignKey(CustomerInvoice, on_delete=models.CASCADE, related_name="items")

    class Meta:
        ordering = ["id"]


class Payment(TimeStampedModel):
    """A receipt against an invoice. Invoice status is recomputed on save."""

    invoice = models.ForeignKey(CustomerInvoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    paid_on = models.DateField(default=timezone.localdate)
    mode = models.CharField(max_length=20, choices=PaymentMode.CHOICES, default=PaymentMode.BANK)
    reference = models.CharField(max_length=100, blank=True, default="")
    recorded_by = models.ForeignKey(
        "authentication.Agent", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-paid_on", "-id"]

    def __str__(self):
        return f"{self.invoice.number} ₹{self.amount}"
