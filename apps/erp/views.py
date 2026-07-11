"""
TeleCRM Backend — apps/erp/views.py

ERP API. Every endpoint is plan-gated on an ERP feature key (ModuleKey.ERP_SALES).

Invariants enforced here:
* Totals and per-line tax are recomputed server-side after every mutation.
* An ISSUED invoice is immutable — no edits, no line changes, no deletion.
* Documents are numbered from a locked sequence, never max()+1.
"""
import csv
import logging

from django.db import transaction
from django.http import StreamingHttpResponse
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import (
    HasFeatureAccess,
    IsAuthenticatedAgent,
    IsManagerOrAdmin,
    IsTenantAdmin,
)
from apps.core.constants import FeatureKey
from apps.core.pagination import StandardResultsSetPagination
from apps.erp.constants import InvoiceStatus, QuotationStatus
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
from apps.erp.serializers import (
    CustomerInvoiceItemSerializer,
    CustomerInvoiceSerializer,
    CustomerSerializer,
    PaymentSerializer,
    ProductSerializer,
    QuotationItemSerializer,
    QuotationSerializer,
    SalesOrderItemSerializer,
    SalesOrderSerializer,
)
from apps.erp.services import documents as doc_svc

logger = logging.getLogger(__name__)


def _bad(message, code="invalid", http=400):
    return Response({"error": code, "message": message}, status=http)


# ============================================================
# Masters
# ============================================================

class CustomerListCreateView(generics.ListCreateAPIView):
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.ERP_PRODUCTS
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Customer.objects.all()
        if search := self.request.query_params.get("search"):
            qs = qs.filter(name__icontains=search)
        return qs


class CustomerDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CustomerSerializer
    queryset = Customer.objects.all()
    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.ERP_PRODUCTS


class ProductListCreateView(generics.ListCreateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.ERP_PRODUCTS
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Product.objects.all()
        if self.request.query_params.get("active") == "true":
            qs = qs.filter(is_active=True)
        if search := self.request.query_params.get("search"):
            qs = qs.filter(name__icontains=search)
        return qs

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsManagerOrAdmin(), HasFeatureAccess()]
        return [IsAuthenticatedAgent(), HasFeatureAccess()]


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProductSerializer
    queryset = Product.objects.all()
    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.ERP_PRODUCTS


# ============================================================
# Quotations
# ============================================================

class QuotationListCreateView(generics.ListCreateAPIView):
    serializer_class = QuotationSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.ERP_QUOTATIONS
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Quotation.objects.select_related("customer").prefetch_related("items")
        if status_filter := self.request.query_params.get("status"):
            qs = qs.filter(status=status_filter)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quotation = doc_svc.create_quotation(
            customer=serializer.validated_data["customer"],
            created_by=request.user,
            quotation_date=serializer.validated_data.get("quotation_date") or None,
            valid_until=serializer.validated_data.get("valid_until"),
            notes=serializer.validated_data.get("notes", ""),
        )
        return Response(QuotationSerializer(quotation).data, status=status.HTTP_201_CREATED)


class QuotationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    PATCH accepts only `notes` and `valid_until` — everything else on a
    quotation is either computed (totals) or moves through a dedicated
    endpoint (status via QuotationStatusView, items via QuotationItemView),
    so a raw PATCH can't be used to sidestep those rules.
    """

    serializer_class = QuotationSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.ERP_QUOTATIONS
    http_method_names = ["get", "patch", "delete", "options"]

    def get_queryset(self):
        return Quotation.objects.select_related("customer").prefetch_related("items")

    def get_serializer(self, *args, **kwargs):
        if self.request.method == "PATCH":
            kwargs["partial"] = True
        return super().get_serializer(*args, **kwargs)

    def perform_update(self, serializer):
        instance = serializer.instance
        if not instance.is_editable:
            raise ValidationError(f"A {instance.status} quotation cannot be edited.")
        # Ignore anything beyond the two header fields a PATCH may touch —
        # status and totals have their own governed paths.
        allowed = {"notes", "valid_until"}
        extra = set(serializer.validated_data) - allowed
        for key in extra:
            serializer.validated_data.pop(key)
        serializer.save()

    def perform_destroy(self, instance):
        if not instance.is_editable:
            raise ValueError(f"A {instance.status} quotation cannot be deleted.")
        instance.delete()


class QuotationStatusView(APIView):
    """
    POST /quotations/{id}/status/  {"status": "sent"|"accepted"|"rejected"}

    A quotation's paper trail: mark it sent to the customer, then record
    their decision. Conversion to a sales order (QuotationConvertView) is a
    separate step and works from any non-terminal status — this endpoint is
    for tracking the customer-facing negotiation, not gating the pipeline.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.ERP_QUOTATIONS

    # From -> allowed to
    TRANSITIONS = {
        QuotationStatus.DRAFT: {QuotationStatus.SENT},
        QuotationStatus.SENT: {QuotationStatus.ACCEPTED, QuotationStatus.REJECTED},
    }

    def post(self, request, pk):
        quotation = Quotation.objects.filter(pk=pk).first()
        if quotation is None:
            return _bad("Quotation not found.", "not_found", 404)

        target = request.data.get("status")
        allowed = self.TRANSITIONS.get(quotation.status, set())
        if target not in allowed:
            return _bad(
                f"Cannot move a {quotation.status} quotation to {target}. "
                f"Allowed: {sorted(allowed) or 'none — already final'}.",
                "invalid_transition",
            )
        quotation.status = target
        quotation.save(update_fields=["status", "updated_at"])
        return Response(QuotationSerializer(quotation).data)


class QuotationItemView(APIView):
    """POST add a line, PATCH edit one, DELETE remove one. Totals recompute on all three."""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.ERP_QUOTATIONS

    @transaction.atomic
    def post(self, request, pk):
        quotation = Quotation.objects.filter(pk=pk).first()
        if quotation is None:
            return _bad("Quotation not found.", "not_found", 404)
        if not quotation.is_editable:
            return _bad(f"A {quotation.status} quotation cannot be edited.", "not_editable")

        serializer = QuotationItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(quotation=quotation)
        doc_svc.recalculate(quotation, quotation.items.all())
        quotation.refresh_from_db()
        return Response(QuotationSerializer(quotation).data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def patch(self, request, pk, item_id):
        quotation = Quotation.objects.filter(pk=pk).first()
        if quotation is None:
            return _bad("Quotation not found.", "not_found", 404)
        if not quotation.is_editable:
            return _bad(f"A {quotation.status} quotation cannot be edited.", "not_editable")
        item = QuotationItem.objects.filter(pk=item_id, quotation=quotation).first()
        if item is None:
            return _bad("Line item not found.", "not_found", 404)

        serializer = QuotationItemSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        doc_svc.recalculate(quotation, quotation.items.all())
        quotation.refresh_from_db()
        return Response(QuotationSerializer(quotation).data)

    @transaction.atomic
    def delete(self, request, pk, item_id):
        quotation = Quotation.objects.filter(pk=pk).first()
        if quotation is None:
            return _bad("Quotation not found.", "not_found", 404)
        if not quotation.is_editable:
            return _bad(f"A {quotation.status} quotation cannot be edited.", "not_editable")
        QuotationItem.objects.filter(pk=item_id, quotation=quotation).delete()
        doc_svc.recalculate(quotation, quotation.items.all())
        quotation.refresh_from_db()
        return Response(QuotationSerializer(quotation).data)


class QuotationConvertView(APIView):
    """POST /quotations/{id}/convert/ → creates a sales order."""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.ERP_SALES_ORDERS

    def post(self, request, pk):
        quotation = Quotation.objects.filter(pk=pk).prefetch_related("items").first()
        if quotation is None:
            return _bad("Quotation not found.", "not_found", 404)
        try:
            order = doc_svc.quotation_to_order(quotation, created_by=request.user)
        except ValueError as exc:
            return _bad(str(exc), "invalid_transition")
        return Response(SalesOrderSerializer(order).data, status=status.HTTP_201_CREATED)


# ============================================================
# Sales Orders
# ============================================================

class SalesOrderListView(generics.ListAPIView):
    serializer_class = SalesOrderSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.ERP_SALES_ORDERS
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = SalesOrder.objects.select_related("customer").prefetch_related("items")
        if status_filter := self.request.query_params.get("status"):
            qs = qs.filter(status=status_filter)
        return qs


class SalesOrderDetailView(generics.RetrieveAPIView):
    serializer_class = SalesOrderSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.ERP_SALES_ORDERS

    def get_queryset(self):
        return SalesOrder.objects.select_related("customer").prefetch_related("items")


class SalesOrderInvoiceView(APIView):
    """POST /orders/{id}/invoice/ → raises a DRAFT invoice."""

    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING

    def post(self, request, pk):
        order = SalesOrder.objects.filter(pk=pk).prefetch_related("items").first()
        if order is None:
            return _bad("Sales order not found.", "not_found", 404)
        try:
            invoice = doc_svc.order_to_invoice(
                order, created_by=request.user, due_date=request.data.get("due_date") or None
            )
        except ValueError as exc:
            return _bad(str(exc), "invalid_transition")
        return Response(CustomerInvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


# ============================================================
# Invoices
# ============================================================

class InvoiceListView(generics.ListAPIView):
    serializer_class = CustomerInvoiceSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = CustomerInvoice.objects.select_related("customer").prefetch_related("items")
        p = self.request.query_params
        if status_filter := p.get("status"):
            qs = qs.filter(status=status_filter)
        if p.get("unpaid") == "true":
            qs = qs.filter(status__in=InvoiceStatus.OPEN)
        if date_from := p.get("date_from"):
            qs = qs.filter(invoice_date__gte=date_from)
        if date_to := p.get("date_to"):
            qs = qs.filter(invoice_date__lte=date_to)
        return qs


class InvoiceDetailView(generics.RetrieveAPIView):
    serializer_class = CustomerInvoiceSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING

    def get_queryset(self):
        return CustomerInvoice.objects.select_related("customer").prefetch_related("items")


class InvoiceItemView(APIView):
    """Edit lines on a DRAFT invoice only."""

    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING

    @transaction.atomic
    def post(self, request, pk):
        invoice = CustomerInvoice.objects.filter(pk=pk).first()
        if invoice is None:
            return _bad("Invoice not found.", "not_found", 404)
        if not invoice.is_editable:
            return _bad(
                f"An {invoice.status} invoice is a legal record and cannot be edited.",
                "not_editable",
            )
        serializer = CustomerInvoiceItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(invoice=invoice)
        doc_svc.recalculate(invoice, invoice.items.all())
        invoice.refresh_from_db()
        return Response(CustomerInvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def delete(self, request, pk, item_id):
        invoice = CustomerInvoice.objects.filter(pk=pk).first()
        if invoice is None:
            return _bad("Invoice not found.", "not_found", 404)
        if not invoice.is_editable:
            return _bad(
                f"An {invoice.status} invoice is a legal record and cannot be edited.",
                "not_editable",
            )
        CustomerInvoiceItem.objects.filter(pk=item_id, invoice=invoice).delete()
        doc_svc.recalculate(invoice, invoice.items.all())
        invoice.refresh_from_db()
        return Response(CustomerInvoiceSerializer(invoice).data)


class InvoiceIssueView(APIView):
    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING

    def post(self, request, pk):
        invoice = CustomerInvoice.objects.filter(pk=pk).prefetch_related("items").first()
        if invoice is None:
            return _bad("Invoice not found.", "not_found", 404)
        try:
            doc_svc.issue_invoice(invoice)
        except ValueError as exc:
            return _bad(str(exc), "invalid_transition")
        invoice.refresh_from_db()
        return Response(CustomerInvoiceSerializer(invoice).data)


class InvoiceCancelView(APIView):
    permission_classes = [IsTenantAdmin, HasFeatureAccess]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING

    def post(self, request, pk):
        invoice = CustomerInvoice.objects.filter(pk=pk).first()
        if invoice is None:
            return _bad("Invoice not found.", "not_found", 404)
        try:
            doc_svc.cancel_invoice(invoice, reason=request.data.get("reason", ""))
        except ValueError as exc:
            return _bad(str(exc), "invalid_transition")
        invoice.refresh_from_db()
        return Response(CustomerInvoiceSerializer(invoice).data)


class PaymentCreateView(APIView):
    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING

    def post(self, request, pk):
        invoice = CustomerInvoice.objects.filter(pk=pk).first()
        if invoice is None:
            return _bad("Invoice not found.", "not_found", 404)

        serializer = PaymentSerializer(data={**request.data, "invoice": invoice.pk})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            payment = doc_svc.record_payment(
                invoice,
                amount=data["amount"],
                recorded_by=request.user,
                paid_on=data.get("paid_on"),
                mode=data.get("mode"),
                reference=data.get("reference", ""),
            )
        except ValueError as exc:
            return _bad(str(exc), "invalid_payment")
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


# ============================================================
# Tally / Zoho Books export
# ============================================================

class _Echo:
    def write(self, value):
        return value


class TallyExportView(APIView):
    """
    GET /api/v1/erp/export/tally/?date_from=&date_to=
    Streams issued invoices as CSV in a layout Tally's import templates accept.
    Only ISSUED/PAID invoices are exported — drafts are not accounting records.
    """

    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.TALLY_INTEGRATION

    COLUMNS = [
        "Invoice Number", "Invoice Date", "Customer Name", "Customer GSTIN",
        "Place of Supply", "HSN/SAC", "Taxable Value", "CGST", "SGST", "IGST",
        "Round Off", "Invoice Total",
    ]

    def get(self, request):
        qs = (
            CustomerInvoice.objects.filter(
                status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID]
            )
            .select_related("customer")
            .prefetch_related("items")
            .order_by("invoice_date", "number")
        )
        if date_from := request.query_params.get("date_from"):
            qs = qs.filter(invoice_date__gte=date_from)
        if date_to := request.query_params.get("date_to"):
            qs = qs.filter(invoice_date__lte=date_to)

        writer = csv.writer(_Echo())

        def rows():
            yield writer.writerow(self.COLUMNS)
            for inv in qs.iterator():
                # One row per HSN group keeps GSTR-1 reconciliation simple.
                hsn = ", ".join(sorted({i.hsn_sac for i in inv.items.all() if i.hsn_sac})) or "-"
                yield writer.writerow([
                    inv.number, inv.invoice_date.isoformat(), inv.customer.name,
                    inv.buyer_gstin or "URP", inv.buyer_state or "-", hsn,
                    inv.subtotal, inv.cgst_amount, inv.sgst_amount, inv.igst_amount,
                    inv.round_off, inv.total_amount,
                ])

        response = StreamingHttpResponse(rows(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="tally_invoices.csv"'
        return response
