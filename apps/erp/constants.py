"""
TeleCRM Backend — apps/erp/constants.py
"""


class DocumentType:
    QUOTATION = "quotation"
    SALES_ORDER = "sales_order"
    INVOICE = "invoice"

    CHOICES = [
        (QUOTATION, "Quotation"),
        (SALES_ORDER, "Sales Order"),
        (INVOICE, "Invoice"),
    ]

    # Prefix used in the document number: PREFIX/FY/NNNNN
    PREFIXES = {QUOTATION: "QUO", SALES_ORDER: "SO", INVOICE: "INV"}


class QuotationStatus:
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONVERTED = "converted"  # became a sales order

    CHOICES = [
        (DRAFT, "Draft"), (SENT, "Sent"), (ACCEPTED, "Accepted"),
        (REJECTED, "Rejected"), (EXPIRED, "Expired"), (CONVERTED, "Converted"),
    ]
    EDITABLE = [DRAFT, SENT]


class SalesOrderStatus:
    OPEN = "open"
    FULFILLED = "fulfilled"
    INVOICED = "invoiced"
    CANCELLED = "cancelled"

    CHOICES = [
        (OPEN, "Open"), (FULFILLED, "Fulfilled"),
        (INVOICED, "Invoiced"), (CANCELLED, "Cancelled"),
    ]
    EDITABLE = [OPEN]


class InvoiceStatus:
    DRAFT = "draft"
    ISSUED = "issued"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    CANCELLED = "cancelled"

    CHOICES = [
        (DRAFT, "Draft"), (ISSUED, "Issued"), (PARTIALLY_PAID, "Partially Paid"),
        (PAID, "Paid"), (CANCELLED, "Cancelled"),
    ]
    # Once issued, a GST invoice is a legal document: it may not be edited or
    # deleted, only cancelled or credit-noted.
    EDITABLE = [DRAFT]
    OPEN = [ISSUED, PARTIALLY_PAID]


class UnitOfMeasure:
    NOS = "nos"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"
    KG = "kg"
    LITRE = "litre"
    METER = "meter"

    CHOICES = [
        (NOS, "Nos"), (HOUR, "Hour"), (DAY, "Day"), (MONTH, "Month"),
        (KG, "Kg"), (LITRE, "Litre"), (METER, "Meter"),
    ]


class PaymentMode:
    CASH = "cash"
    BANK = "bank_transfer"
    UPI = "upi"
    CHEQUE = "cheque"
    CARD = "card"
    OTHER = "other"

    CHOICES = [
        (CASH, "Cash"), (BANK, "Bank Transfer"), (UPI, "UPI"),
        (CHEQUE, "Cheque"), (CARD, "Card"), (OTHER, "Other"),
    ]
