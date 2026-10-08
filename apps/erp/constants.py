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
    # Lines change only on a draft: once sent, the record must match what the
    # customer received (revise = move it back to draft).
    EDITABLE = [DRAFT]


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
    PCS = "pcs"
    BOX = "box"
    SET = "set"
    PACK = "pack"
    DOZEN = "dozen"
    PAIR = "pair"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    JOB = "job"
    KG = "kg"
    GRAM = "gram"
    TON = "ton"
    LITRE = "litre"
    ML = "ml"
    METER = "meter"
    SQFT = "sqft"
    SQM = "sqm"

    CHOICES = [
        (NOS, "Nos"), (PCS, "Pieces"), (BOX, "Box"), (SET, "Set"), (PACK, "Pack"),
        (DOZEN, "Dozen"), (PAIR, "Pair"),
        (HOUR, "Hour"), (DAY, "Day"), (MONTH, "Month"), (YEAR, "Year"), (JOB, "Job"),
        (KG, "Kg"), (GRAM, "Gram"), (TON, "Tonne"), (LITRE, "Litre"), (ML, "ml"),
        (METER, "Meter"), (SQFT, "Sq. ft"), (SQM, "Sq. m"),
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
