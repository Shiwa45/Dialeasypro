"""
TeleCRM Backend — apps/erp/admin.py

ERP models live in the TENANT schema, so these appear in the per-tenant admin.
Issued invoices are read-only here too — the ledger must not be editable by
hand once a document has been given to a customer.
"""
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.erp.constants import InvoiceStatus
from apps.erp.models import (
    Customer,
    CustomerInvoice,
    CustomerInvoiceItem,
    DocumentSequence,
    Payment,
    Product,
    Quotation,
    QuotationItem,
    SalesOrder,
    SalesOrderItem,
)

COMPUTED = ["taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "line_total"]
DOC_TOTALS = [
    "subtotal", "cgst_amount", "sgst_amount", "igst_amount",
    "total_tax", "round_off", "total_amount", "is_interstate",
]


@admin.register(Customer)
class CustomerAdmin(ModelAdmin):
    list_display = ["name", "gstin", "state_code", "phone", "is_active"]
    search_fields = ["name", "gstin", "phone", "email"]
    list_filter = ["is_active", "state_code"]
    raw_id_fields = ["lead"]


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ["sku", "name", "hsn_sac", "unit_price", "gst_rate", "is_service", "is_active"]
    search_fields = ["sku", "name", "hsn_sac"]
    list_filter = ["is_active", "is_service", "gst_rate"]


class QuotationItemInline(TabularInline):
    model = QuotationItem
    extra = 0
    readonly_fields = COMPUTED


@admin.register(Quotation)
class QuotationAdmin(ModelAdmin):
    list_display = ["number", "customer", "quotation_date", "status", "total_amount"]
    list_filter = ["status", "quotation_date"]
    search_fields = ["number", "customer__name"]
    readonly_fields = ["number"] + DOC_TOTALS
    inlines = [QuotationItemInline]
    raw_id_fields = ["customer", "created_by"]


class SalesOrderItemInline(TabularInline):
    model = SalesOrderItem
    extra = 0
    readonly_fields = COMPUTED


@admin.register(SalesOrder)
class SalesOrderAdmin(ModelAdmin):
    list_display = ["number", "customer", "order_date", "status", "total_amount"]
    list_filter = ["status", "order_date"]
    search_fields = ["number", "customer__name"]
    readonly_fields = ["number"] + DOC_TOTALS
    inlines = [SalesOrderItemInline]
    raw_id_fields = ["customer", "quotation", "created_by"]


class CustomerInvoiceItemInline(TabularInline):
    model = CustomerInvoiceItem
    extra = 0
    readonly_fields = COMPUTED


class PaymentInline(TabularInline):
    model = Payment
    extra = 0


@admin.register(CustomerInvoice)
class CustomerInvoiceAdmin(ModelAdmin):
    list_display = [
        "number", "customer", "invoice_date", "status",
        "total_amount", "amount_paid", "amount_due",
    ]
    list_filter = ["status", "invoice_date", "is_interstate"]
    search_fields = ["number", "customer__name", "buyer_gstin"]
    inlines = [CustomerInvoiceItemInline, PaymentInline]
    raw_id_fields = ["customer", "sales_order", "created_by"]

    def get_readonly_fields(self, request, obj=None):
        base = ["number", "amount_paid", "issued_at", "cancelled_at"] + DOC_TOTALS
        if obj and obj.status != InvoiceStatus.DRAFT:
            # An issued invoice is a legal record: freeze the whole form.
            return base + [f.name for f in obj._meta.fields if f.name != "id"]
        return base

    def has_delete_permission(self, request, obj=None):
        # Never delete a GST invoice — cancel it instead.
        return obj is None or obj.status == InvoiceStatus.DRAFT


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(ModelAdmin):
    list_display = ["doc_type", "financial_year", "last_number"]
    readonly_fields = ["doc_type", "financial_year", "last_number"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # Deleting a counter would restart numbering and emit duplicates.
        return False
