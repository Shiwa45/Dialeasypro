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
        from apps.erp.gstin import gstin_problem

        value = (value or "").strip().upper()
        if problem := gstin_problem(value):
            raise serializers.ValidationError(problem)
        return value

    def validate_state_code(self, value):
        from apps.core.constants import INDIAN_STATE_CODES, canonical_state_code

        code = canonical_state_code(value)
        if code and code not in INDIAN_STATE_CODES:
            raise serializers.ValidationError(f'"{value}" is not an Indian state or UT code.')
        return code

    def validate_phone(self, value):
        value = (value or "").strip()
        if not value:
            return ""
        from apps.core.utils import normalize_indian_phone

        normalized = normalize_indian_phone(value)
        if not normalized:
            raise serializers.ValidationError("Enter a valid phone number, e.g. +919876543210.")
        return normalized

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Give the customer a name.")
        return value

    def validate(self, attrs):
        """
        The GSTIN decides the place of supply. A registered customer's state is
        taken from it when left blank, and refused when it disagrees — a Delhi
        GSTIN (07…) saved under Maharashtra taxed every invoice wrongly.
        """
        from apps.erp.gstin import state_from_gstin

        instance = self.instance
        gstin = attrs.get("gstin", instance.gstin if instance else "")
        state = attrs.get("state_code", instance.state_code if instance else "")
        if gstin:
            from_gstin = state_from_gstin(gstin)
            if from_gstin and not state:
                attrs["state_code"] = from_gstin
            elif from_gstin and state and state != from_gstin:
                raise serializers.ValidationError({"state_code": (
                    f"This GSTIN is registered in {from_gstin} (its first two digits are "
                    f"{gstin[:2]}), but the state chosen is {state}."
                )})
            clash = Customer.objects.filter(gstin=gstin)
            if instance:
                clash = clash.exclude(pk=instance.pk)
            if (other := clash.first()):
                raise serializers.ValidationError({"gstin": f"{other.name} already has this GSTIN."})
        name = attrs.get("name", instance.name if instance else "")
        if name and not gstin:
            clash = Customer.objects.filter(name__iexact=name, gstin="")
            if instance:
                clash = clash.exclude(pk=instance.pk)
            if clash.exists():
                raise serializers.ValidationError({"name": (
                    f'A customer called "{name}" already exists. Use that one, or add a GSTIN '
                    "or a distinguishing detail to the name."
                )})
        return attrs


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "id", "name", "sku", "description", "hsn_sac", "is_service", "unit",
            "unit_price", "gst_rate", "track_stock", "stock_quantity", "is_active",
        ]

    def validate_gst_rate(self, value):
        return _valid_gst_rate(value)

    def validate_hsn_sac(self, value):
        return _valid_hsn(value)

    def validate_unit_price(self, value):
        if value is None or Decimal(value) <= 0:
            raise serializers.ValidationError("Enter a price above ₹0.")
        return value


def _valid_gst_rate(value):
    if Decimal(value) not in VALID_GST_RATES:
        raise serializers.ValidationError(
            "GST rate must be 0, 5, 12, 18 or 28 %."
        )
    return value


def _valid_hsn(value):
    """HSN (goods) or SAC (services): 4, 6 or 8 digits. Blank is allowed on a line."""
    value = (value or "").strip()
    if value and (not value.isdigit() or len(value) not in (4, 6, 8)):
        raise serializers.ValidationError("HSN/SAC must be 4, 6 or 8 digits.")
    return value


class _LineItemSerializer(serializers.ModelSerializer):
    """Shared line behaviour: computed fields are read-only."""

    # A custom line (freight, packing, a one-off charge) has no product.
    product_name = serializers.CharField(source="product.name", read_only=True, default=None)

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

    def validate_gst_rate(self, value):
        # Lines took any rate (7 % was saved on an invoice); only GST slabs are legal.
        return _valid_gst_rate(value)

    def validate_hsn_sac(self, value):
        return _valid_hsn(value)

    def validate_unit_price(self, value):
        if value is None or Decimal(value) < 0:
            raise serializers.ValidationError("The price can't be negative.")
        return value

    def validate(self, attrs):
        product = attrs.get("product", getattr(self.instance, "product", None))
        description = (attrs.get("description", getattr(self.instance, "description", "")) or "").strip()
        if product is None and not description:
            raise serializers.ValidationError(
                {"description": "Describe a custom line (it has no product to take a name from)."}
            )
        if product is None and attrs.get("unit_price") is None and self.instance is None:
            raise serializers.ValidationError({"unit_price": "Enter a price for a custom line."})
        return attrs


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

    # A quotation is sent to the customer, so it has to name them properly.
    # An invoice freezes the address into billing_address_snapshot because it
    # is a legal record; a quotation carries no such snapshot, so these read
    # live off the customer. The view already select_related("customer").
    customer_gstin = serializers.CharField(source="customer.gstin", read_only=True)
    customer_billing_address = serializers.CharField(
        source="customer.billing_address", read_only=True
    )
    customer_email = serializers.CharField(source="customer.email", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)

    class Meta:
        model = Quotation
        fields = [
            "id", "number", "customer", "customer_name", "quotation_date", "valid_until",
            "status", "notes", "items", "created_by",
            "customer_gstin", "customer_billing_address", "customer_email", "customer_phone",
        ] + COMPUTED_DOC_FIELDS[1:]
        read_only_fields = COMPUTED_DOC_FIELDS + [
            "status", "created_by",
            "customer_gstin", "customer_billing_address", "customer_email", "customer_phone",
        ]

    def validate(self, attrs):
        from django.utils import timezone

        instance = self.instance
        start = attrs.get("quotation_date") or (instance.quotation_date if instance else timezone.localdate())
        until = attrs.get("valid_until", instance.valid_until if instance else None)
        if until and start and until < start:
            raise serializers.ValidationError(
                {"valid_until": "\"Valid until\" can't be before the quotation date."}
            )
        return attrs


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

    def validate(self, attrs):
        from django.utils import timezone

        instance = self.instance
        start = attrs.get("invoice_date") or (instance.invoice_date if instance else timezone.localdate())
        due = attrs.get("due_date", instance.due_date if instance else None)
        if due and start and due < start:
            raise serializers.ValidationError({"due_date": "The due date can't be before the invoice date."})
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    # A payments ledger is unreadable without knowing which invoice and which
    # customer each row belongs to, and the client should not have to fetch
    # every invoice to find out.
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    customer_name = serializers.CharField(source="invoice.customer.name", read_only=True)
    recorded_by_name = serializers.CharField(source="recorded_by.name", read_only=True, default=None)

    class Meta:
        model = Payment
        fields = [
            "id", "invoice", "invoice_number", "customer_name", "amount", "paid_on",
            "mode", "reference", "recorded_by", "recorded_by_name", "created_at",
        ]
        read_only_fields = ["id", "recorded_by", "created_at"]

    def validate_paid_on(self, value):
        from django.utils import timezone

        if value and value > timezone.localdate():
            raise serializers.ValidationError("A payment can't be dated in the future.")
        return value
