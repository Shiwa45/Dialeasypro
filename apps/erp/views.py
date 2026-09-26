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
from rest_framework.renderers import JSONRenderer

from apps.core.renderers import CSVRenderer
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import HasFeatureAccess, IsAuthenticatedAgent
from apps.core.capabilities import Cap
from apps.core.constants import FeatureKey
from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import HasCapability
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
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_PRODUCTS
    required_capability = Cap.ERP_VIEW
    capability_by_method = {"POST": Cap.ERP_MANAGE}
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Customer.objects.all()
        if search := self.request.query_params.get("search"):
            qs = qs.filter(name__icontains=search)
        return qs


class CustomerDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CustomerSerializer
    queryset = Customer.objects.all()
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_PRODUCTS
    required_capability = Cap.ERP_MANAGE


class ProductListCreateView(generics.ListCreateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_PRODUCTS
    required_capability = Cap.ERP_VIEW
    capability_by_method = {"POST": Cap.ERP_MANAGE}
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Product.objects.all()
        if self.request.query_params.get("active") == "true":
            qs = qs.filter(is_active=True)
        if search := self.request.query_params.get("search"):
            qs = qs.filter(name__icontains=search)
        return qs


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProductSerializer
    queryset = Product.objects.all()
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_PRODUCTS
    required_capability = Cap.ERP_MANAGE


# ============================================================
# Quotations
# ============================================================

class QuotationListCreateView(generics.ListCreateAPIView):
    serializer_class = QuotationSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_QUOTATIONS
    required_capability = Cap.ERP_VIEW
    capability_by_method = {"POST": Cap.ERP_MANAGE}
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
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_QUOTATIONS
    required_capability = Cap.ERP_VIEW
    capability_by_method = {"PATCH": Cap.ERP_MANAGE, "PUT": Cap.ERP_MANAGE, "DELETE": Cap.ERP_MANAGE}
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

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_QUOTATIONS
    required_capability = Cap.ERP_MANAGE

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

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_QUOTATIONS
    required_capability = Cap.ERP_MANAGE

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

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_SALES_ORDERS
    required_capability = Cap.ERP_MANAGE

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
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_SALES_ORDERS
    required_capability = Cap.ERP_VIEW
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = SalesOrder.objects.select_related("customer").prefetch_related("items")
        if status_filter := self.request.query_params.get("status"):
            qs = qs.filter(status=status_filter)
        return qs


class SalesOrderDetailView(generics.RetrieveAPIView):
    serializer_class = SalesOrderSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_SALES_ORDERS
    required_capability = Cap.ERP_VIEW

    def get_queryset(self):
        return SalesOrder.objects.select_related("customer").prefetch_related("items")


class SalesOrderInvoiceView(APIView):
    """POST /orders/{id}/invoice/ → raises a DRAFT invoice."""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING
    required_capability = Cap.ERP_MANAGE

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
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING
    required_capability = Cap.ERP_VIEW
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


class InvoiceDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE one invoice.

    PATCH and DELETE apply to DRAFTS ONLY. An issued invoice carries a GST
    number from a locked sequence and has been sent to a customer — deleting it
    would leave a hole in that sequence, which is exactly what a tax audit asks
    about. Cancel it instead (/invoices/{id}/cancel/): that keeps the number
    and records why.
    """

    serializer_class = CustomerInvoiceSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING
    required_capability = Cap.ERP_VIEW
    capability_by_method = {
        "PATCH": Cap.ERP_MANAGE, "PUT": Cap.ERP_MANAGE, "DELETE": Cap.ERP_MANAGE,
    }

    def get_queryset(self):
        return CustomerInvoice.objects.select_related("customer").prefetch_related("items")

    def update(self, request, *args, **kwargs):
        invoice = self.get_object()
        if not invoice.is_editable:
            return _bad(
                f"An {invoice.status} invoice is a legal record and cannot be edited.",
                "not_editable",
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        invoice = self.get_object()
        if not invoice.is_editable:
            return _bad(
                f"An {invoice.status} invoice cannot be deleted — cancel it instead, "
                f"which keeps its number in the GST sequence.",
                "not_editable",
            )
        return super().destroy(request, *args, **kwargs)


class InvoiceItemView(APIView):
    """Edit lines on a DRAFT invoice only."""

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING
    required_capability = Cap.ERP_MANAGE

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
    def patch(self, request, pk, item_id):
        """
        Edit one line on a draft. Without this, fixing a typo in a quantity
        meant deleting the line and retyping it — which is fine until the line
        is the tenth on a long invoice and reappears at the bottom.
        """
        invoice = CustomerInvoice.objects.filter(pk=pk).first()
        if invoice is None:
            return _bad("Invoice not found.", "not_found", 404)
        if not invoice.is_editable:
            return _bad(
                f"An {invoice.status} invoice is a legal record and cannot be edited.",
                "not_editable",
            )
        item = CustomerInvoiceItem.objects.filter(pk=item_id, invoice=invoice).first()
        if item is None:
            return _bad("Line item not found on this invoice.", "not_found", 404)

        serializer = CustomerInvoiceItemSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        doc_svc.recalculate(invoice, invoice.items.all())
        invoice.refresh_from_db()
        return Response(CustomerInvoiceSerializer(invoice).data)

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
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING
    required_capability = Cap.ERP_INVOICE_ISSUE

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
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING
    required_capability = Cap.ERP_INVOICE_CANCEL

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
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING
    required_capability = Cap.ERP_PAYMENTS

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

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.TALLY_INTEGRATION
    required_capability = Cap.ERP_EXPORT
    # So a client that asks for `Accept: text/csv` on a CSV endpoint is not
    # refused with 406 during negotiation, before this view runs. JSON stays
    # first so errors still render as JSON.
    renderer_classes = [JSONRenderer, CSVRenderer]

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


# ============================================================
# Payments ledger
# ============================================================

class PaymentListView(generics.ListAPIView):
    """
    GET /api/v1/erp/payments/

    Payments could be recorded from the day the module shipped but never read
    back anywhere — the only way to see what a customer had paid was to open
    each of their invoices in turn and add up the differences.
    """

    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING
    required_capability = Cap.ERP_VIEW
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Payment.objects.select_related("invoice", "invoice__customer", "recorded_by")
        p = self.request.query_params
        if customer := p.get("customer"):
            qs = qs.filter(invoice__customer_id=customer)
        if invoice := p.get("invoice"):
            qs = qs.filter(invoice_id=invoice)
        if mode := p.get("mode"):
            qs = qs.filter(mode=mode)
        if date_from := p.get("date_from"):
            qs = qs.filter(paid_on__gte=date_from)
        if date_to := p.get("date_to"):
            qs = qs.filter(paid_on__lte=date_to)
        return qs


# ============================================================
# Dashboard & reports
# ============================================================

class ErpDashboardView(APIView):
    """
    GET /api/v1/erp/dashboard/?month=YYYY-MM

    Revenue, outstanding, receivables ageing and top customers in one call.

    Ageing buckets are counted from the DUE date where one is set, falling back
    to the invoice date. An invoice with no due date is not overdue on the day
    it is raised, and bucketing it from the invoice date would report it as
    31-60 days overdue a month later while the customer is still inside
    perfectly normal payment terms.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.ERP_CUSTOMER_INVOICING
    required_capability = Cap.ERP_VIEW

    def get(self, request):
        from datetime import datetime

        from django.db.models import Count, F, Sum

        raw = request.query_params.get("month")
        today = timezone.localdate()
        try:
            month_start = (
                datetime.strptime(raw, "%Y-%m").date() if raw else today
            ).replace(day=1)
        except ValueError:
            return _bad("Invalid month. Use YYYY-MM.", "invalid_month")

        next_month = (month_start.replace(day=28) + timezone.timedelta(days=4)).replace(day=1)

        issued = CustomerInvoice.objects.exclude(status=InvoiceStatus.DRAFT).exclude(
            status=InvoiceStatus.CANCELLED
        )

        month_invoices = issued.filter(
            invoice_date__gte=month_start, invoice_date__lt=next_month
        )
        month_totals = month_invoices.aggregate(
            revenue=Sum("total_amount"), taxable=Sum("subtotal"),
            tax=Sum("total_tax"), n=Count("id"),
        )

        collected = Payment.objects.filter(
            paid_on__gte=month_start, paid_on__lt=next_month
        ).aggregate(total=Sum("amount"))["total"] or 0

        # Ageing over every open invoice, not just this month's.
        open_invoices = issued.filter(status__in=InvoiceStatus.OPEN)
        buckets = {"current": 0, "1_30": 0, "31_60": 0, "61_90": 0, "90_plus": 0}
        outstanding = 0
        for inv in open_invoices.only(
            "total_amount", "amount_paid", "due_date", "invoice_date"
        ):
            due = inv.amount_due
            if due <= 0:
                continue
            outstanding += due
            reference = inv.due_date or inv.invoice_date
            overdue_days = (today - reference).days
            if overdue_days <= 0:
                buckets["current"] += due
            elif overdue_days <= 30:
                buckets["1_30"] += due
            elif overdue_days <= 60:
                buckets["31_60"] += due
            elif overdue_days <= 90:
                buckets["61_90"] += due
            else:
                buckets["90_plus"] += due

        top_customers = list(
            month_invoices.values("customer_id", name=F("customer__name"))
            .annotate(total=Sum("total_amount"), invoices=Count("id"))
            .order_by("-total")[:5]
        )

        return Response({
            "month": month_start.isoformat(),
            "revenue": {
                "total": str(month_totals["revenue"] or 0),
                "taxable": str(month_totals["taxable"] or 0),
                "tax": str(month_totals["tax"] or 0),
                "invoices": month_totals["n"] or 0,
            },
            "collected_this_month": str(collected),
            "outstanding": str(outstanding),
            "ageing": {k: str(v) for k, v in buckets.items()},
            "open_invoices": open_invoices.count(),
            "top_customers": [
                {"id": c["customer_id"], "name": c["name"],
                 "total": str(c["total"]), "invoices": c["invoices"]}
                for c in top_customers
            ],
            "counts": {
                "customers": Customer.objects.filter(is_active=True).count(),
                "products": Product.objects.filter(is_active=True).count(),
                "draft_invoices": CustomerInvoice.objects.filter(status=InvoiceStatus.DRAFT).count(),
                "open_quotations": Quotation.objects.filter(
                    status__in=[QuotationStatus.DRAFT, QuotationStatus.SENT]
                ).count(),
            },
        })


class GstSummaryView(APIView):
    """
    GET /api/v1/erp/reports/gst-summary/?month=YYYY-MM

    A GSTR-1-shaped summary of the month's issued invoices: B2B (buyer has a
    GSTIN) versus B2C, split by rate, with CGST/SGST/IGST separated.

    This is a filing AID, not a return. It reports what was invoiced in the
    system; it does not know about credit notes raised outside it, advances,
    or reverse charge. Cross-check before filing.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.TALLY_INTEGRATION
    required_capability = Cap.ERP_EXPORT

    def get(self, request):
        from collections import defaultdict
        from datetime import datetime
        from decimal import Decimal

        raw = request.query_params.get("month")
        try:
            month_start = (
                datetime.strptime(raw, "%Y-%m").date() if raw else timezone.localdate()
            ).replace(day=1)
        except ValueError:
            return _bad("Invalid month. Use YYYY-MM.", "invalid_month")
        next_month = (month_start.replace(day=28) + timezone.timedelta(days=4)).replace(day=1)

        invoices = (
            CustomerInvoice.objects
            .exclude(status__in=[InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED])
            .filter(invoice_date__gte=month_start, invoice_date__lt=next_month)
            .select_related("customer").prefetch_related("items")
        )

        def bucket():
            return {"taxable": Decimal("0"), "cgst": Decimal("0"),
                    "sgst": Decimal("0"), "igst": Decimal("0"), "invoices": set()}

        b2b, b2c = defaultdict(bucket), defaultdict(bucket)
        for inv in invoices:
            target = b2b if inv.buyer_gstin else b2c
            for item in inv.items.all():
                row = target[str(item.gst_rate)]
                row["taxable"] += item.taxable_value
                row["cgst"] += item.cgst_amount
                row["sgst"] += item.sgst_amount
                row["igst"] += item.igst_amount
                row["invoices"].add(inv.id)

        def render(data):
            return [
                {
                    "gst_rate": rate,
                    "taxable": str(v["taxable"]),
                    "cgst": str(v["cgst"]), "sgst": str(v["sgst"]), "igst": str(v["igst"]),
                    "total_tax": str(v["cgst"] + v["sgst"] + v["igst"]),
                    "invoices": len(v["invoices"]),
                }
                for rate, v in sorted(data.items(), key=lambda kv: float(kv[0]))
            ]

        return Response({
            "month": month_start.isoformat(),
            "b2b": render(b2b),
            "b2c": render(b2c),
            "invoice_count": invoices.count(),
            "note": (
                "Filing aid only. Credit notes raised outside this system, advances "
                "and reverse-charge supplies are not included — reconcile before filing."
            ),
        })
