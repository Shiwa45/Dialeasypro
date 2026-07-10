"""
TeleCRM Backend — apps/erp/serializers.py

Line-item pricing fields (taxable_value, tax amounts, line_total) and document
totals are ALWAYS read-only: they are recomputed server-side from quantity,
price, discount and GST rate. A client must never be able to state its own tax.
"""
from decimal import Decimal

from rest_framework import serializers

from apps.erp.gst import VALID_GST_RATES
from apps.erp.models import (
    Customer,
    CustomerInvoice,
    CustomerInvoiceItem,
    Payment,
    Product,
    Quotation,
    QuotationItem,
    SalesOrder,
    SalesOrderItem,
)

COMPUTED_LINE_FIELDS = [
    "taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "line_total",
]
COMPUTED_DOC_FIELDS = [
    "number", "subtotal", "cgst_amount", "sgst_amount", "igst_amount",
    "total_tax", "round_off", "total_amount", "is_interstate",
    "seller_state", "buyer_state",
]


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            "id", "name", "lead", "email", "phone", "gstin", "state_code",
            "billing_address", "shipping_address", "is_active",
        ]

    def validate_gstin(self, value):
        if value and len(value) != 15:
            raise serializers.ValidationError("A GSTIN is exactly 15 characters.")
        return value.upper()

    def validate_state_code(self, value):
        return value.upper()


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "id", "name", "sku", "description", "hsn_sac", "is_service", "unit",
            "unit_price", "gst_rate", "track_stock", "stock_quantity", "is_active",
        ]

    def validate_gst_rate(self, value):
        if Decimal(value) not in VALID_GST_RATES:
            raise serializers.ValidationError(
                f"GST rate must be one of {[str(r) for r in VALID_GST_RATES]}."
            )
        return value


class _LineItemSerializer(serializers.ModelSerializer):
    """Shared line behaviour: computed fields are read-only."""

    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        fields = [
            "id", "product", "product_name", "description", "hsn_sac",
            "quantity", "unit_price", "discount_percent", "gst_rate",
        ] + COMPUTED_LINE_FIELDS
        read_only_fields = COMPUTED_LINE_FIELDS

    def validate_discount_percent(self, value):
        if not (Decimal("0") <= Decimal(value) <= Decimal("100")):
            raise serializers.ValidationError("Discount must be between 0 and 100.")
        return value


class QuotationItemSerializer(_LineItemSerializer):
    class Meta(_LineItemSerializer.Meta):
        model = QuotationItem


class SalesOrderItemSerializer(_LineItemSerializer):
    class Meta(_LineItemSerializer.Meta):
        model = SalesOrderItem


class CustomerInvoiceItemSerializer(_LineItemSerializer):
    class Meta(_LineItemSerializer.Meta):
        model = CustomerInvoiceItem


class QuotationSerializer(serializers.ModelSerializer):
    items = QuotationItemSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = Quotation
        fields = [
            "id", "number", "customer", "customer_name", "quotation_date", "valid_until",
            "status", "notes", "items", "created_by",
        ] + COMPUTED_DOC_FIELDS[1:]
        read_only_fields = COMPUTED_DOC_FIELDS + ["status", "created_by"]


class SalesOrderSerializer(serializers.ModelSerializer):
    items = SalesOrderItemSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = SalesOrder
        fields = [
            "id", "number", "customer", "customer_name", "order_date", "quotation",
            "expected_delivery", "status", "notes", "items", "created_by",
        ] + COMPUTED_DOC_FIELDS[1:]
        read_only_fields = COMPUTED_DOC_FIELDS + ["status", "created_by", "quotation"]


class CustomerInvoiceSerializer(serializers.ModelSerializer):
    items = CustomerInvoiceItemSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    amount_due = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = CustomerInvoice
        fields = [
            "id", "number", "customer", "customer_name", "invoice_date", "due_date",
            "sales_order", "status", "notes", "items",
            "seller_gstin", "buyer_gstin", "billing_address_snapshot",
            "amount_paid", "amount_due", "issued_at", "cancelled_at",
            "cancellation_reason", "created_by",
        ] + COMPUTED_DOC_FIELDS[1:]
        read_only_fields = COMPUTED_DOC_FIELDS + [
            "status", "created_by", "sales_order", "amount_paid", "issued_at",
            "cancelled_at", "cancellation_reason", "seller_gstin", "buyer_gstin",
            "billing_address_snapshot",
        ]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "invoice", "amount", "paid_on", "mode", "reference", "recorded_by"]
        read_only_fields = ["id", "recorded_by"]
