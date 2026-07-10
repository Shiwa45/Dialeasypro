"""
TeleCRM Backend — apps/erp/api_urls.py
Mounted at: /api/v1/erp/
"""
from django.urls import path

from apps.erp.views import (
    CustomerDetailView,
    CustomerListCreateView,
    InvoiceCancelView,
    InvoiceDetailView,
    InvoiceIssueView,
    InvoiceItemView,
    InvoiceListView,
    PaymentCreateView,
    ProductDetailView,
    ProductListCreateView,
    QuotationConvertView,
    QuotationDetailView,
    QuotationItemView,
    QuotationListCreateView,
    SalesOrderDetailView,
    SalesOrderInvoiceView,
    SalesOrderListView,
    TallyExportView,
)

urlpatterns = [
    # Masters
    path("customers/", CustomerListCreateView.as_view(), name="api_erp_customers"),
    path("customers/<int:pk>/", CustomerDetailView.as_view(), name="api_erp_customer_detail"),
    path("products/", ProductListCreateView.as_view(), name="api_erp_products"),
    path("products/<int:pk>/", ProductDetailView.as_view(), name="api_erp_product_detail"),

    # Quotations
    path("quotations/", QuotationListCreateView.as_view(), name="api_erp_quotations"),
    path("quotations/<int:pk>/", QuotationDetailView.as_view(), name="api_erp_quotation_detail"),
    path("quotations/<int:pk>/items/", QuotationItemView.as_view(), name="api_erp_quotation_items"),
    path("quotations/<int:pk>/items/<int:item_id>/", QuotationItemView.as_view(), name="api_erp_quotation_item"),
    path("quotations/<int:pk>/convert/", QuotationConvertView.as_view(), name="api_erp_quotation_convert"),

    # Sales orders
    path("orders/", SalesOrderListView.as_view(), name="api_erp_orders"),
    path("orders/<int:pk>/", SalesOrderDetailView.as_view(), name="api_erp_order_detail"),
    path("orders/<int:pk>/invoice/", SalesOrderInvoiceView.as_view(), name="api_erp_order_invoice"),

    # Invoices
    path("invoices/", InvoiceListView.as_view(), name="api_erp_invoices"),
    path("invoices/<int:pk>/", InvoiceDetailView.as_view(), name="api_erp_invoice_detail"),
    path("invoices/<int:pk>/items/", InvoiceItemView.as_view(), name="api_erp_invoice_items"),
    path("invoices/<int:pk>/items/<int:item_id>/", InvoiceItemView.as_view(), name="api_erp_invoice_item"),
    path("invoices/<int:pk>/issue/", InvoiceIssueView.as_view(), name="api_erp_invoice_issue"),
    path("invoices/<int:pk>/cancel/", InvoiceCancelView.as_view(), name="api_erp_invoice_cancel"),
    path("invoices/<int:pk>/payments/", PaymentCreateView.as_view(), name="api_erp_invoice_payment"),

    # Accounting export
    path("export/tally/", TallyExportView.as_view(), name="api_erp_tally_export"),
]
