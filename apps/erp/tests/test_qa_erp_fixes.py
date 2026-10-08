"""
Regressions for ERP_QA_REPORT.md (Sales & Billing tested on the live site).
Each test names the report item it pins.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.erp.constants import InvoiceStatus, QuotationStatus, SalesOrderStatus
from apps.erp.models import Customer, CustomerInvoice, Payment, Product, Quotation
from apps.erp.services import documents as doc_svc
from apps.tenants.models import Tenant
from conftest import TEST_SCHEMA

pytestmark = pytest.mark.django_db
factory = APIRequestFactory()
VALID_MH = "27AAPFU0939F1ZV"     # a well-formed Maharashtra GSTIN (check digit valid)
VALID_KA = "29AAGCB7383J1Z4"


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(email="erp-admin@x.com", name="Admin", password="Pw@12345678")


@pytest.fixture
def seller():
    t = Tenant.objects.get(schema_name=TEST_SCHEMA)
    old = (t.gstin, t.state, t.company_name)
    Tenant.objects.filter(pk=t.pk).update(gstin="09AAACH7409R1ZZ", state="UP")
    yield
    Tenant.objects.filter(pk=t.pk).update(gstin=old[0], state=old[1], company_name=old[2])


def _call(view, method, user, data=None, **kwargs):
    request = getattr(factory, method)("/x/", data, format="json")
    force_authenticate(request, user=user)
    request.has_feature = lambda key: True
    response = view.as_view()(request, **kwargs)
    response.render()
    return response


def _customer(name="Buyer", state="MH", gstin=""):
    return Customer.objects.create(name=name, state_code=state, gstin=gstin)


def _product(**kw):
    defaults = dict(name="Laptop", sku=f"SKU{Product.objects.count()+1}", hsn_sac="8471",
                    unit_price=Decimal("1000"), gst_rate=Decimal("18"))
    defaults.update(kw)
    return Product.objects.create(**defaults)


# ---- E11 quotation create ---------------------------------------------------

def test_e11_a_quotation_can_be_created_without_a_date(admin):
    from apps.erp.views import QuotationListCreateView
    c = _customer()
    r = _call(QuotationListCreateView, "post", admin, {"customer": c.pk})
    assert r.status_code == 201, r.data
    assert r.data["quotation_date"] == timezone.localdate().isoformat()


def test_e13_valid_until_cannot_precede_the_quotation(admin):
    from apps.erp.views import QuotationListCreateView
    c = _customer()
    r = _call(QuotationListCreateView, "post", admin,
              {"customer": c.pk, "valid_until": (timezone.localdate() - timedelta(days=3)).isoformat()})
    assert r.status_code == 400


# ---- E12 stand-alone invoice -----------------------------------------------

def test_e12_new_invoice_can_be_created(admin):
    from apps.erp.views import InvoiceListView
    c = _customer()
    r = _call(InvoiceListView, "post", admin, {"customer": c.pk})
    assert r.status_code == 201, r.data
    assert r.data["status"] == "draft"
    assert r.data["number"].startswith("DRAFT-")


def test_e36_invoice_customer_filter(admin):
    from apps.erp.views import InvoiceListView
    a, b = _customer("A"), _customer("B")
    doc_svc.create_invoice(customer=a)
    doc_svc.create_invoice(customer=b)
    request = factory.get(f"/x/?customer={a.pk}")
    force_authenticate(request, user=admin); request.has_feature = lambda k: True
    r = InvoiceListView.as_view()(request); r.render()
    assert [row["customer"] for row in r.data["results"]] == [a.pk]


# ---- E25 draft numbers / issue ---------------------------------------------

def _draft_with_line(customer, product=None, qty="2"):
    inv = doc_svc.create_invoice(customer=customer)
    product = product or _product()
    from apps.erp.models import CustomerInvoiceItem
    CustomerInvoiceItem.objects.create(invoice=inv, product=product, description=product.name,
                                       hsn_sac=product.hsn_sac, quantity=Decimal(qty),
                                       unit_price=product.unit_price, gst_rate=product.gst_rate)
    doc_svc.recalculate(inv, inv.items.all())
    inv.refresh_from_db()
    return inv


def test_e25_gst_number_taken_only_at_issue_so_deleting_drafts_leaves_no_gap(seller):
    c = _customer()
    d1 = _draft_with_line(c)
    doc_svc.delete_draft_invoice(d1)
    d2 = _draft_with_line(c)
    doc_svc.issue_invoice(d2)
    d2.refresh_from_db()
    assert d2.number.startswith("INV/") and d2.number.endswith("/00001")


def test_e28_issue_needs_the_company_gstin():
    t = Tenant.objects.get(schema_name=TEST_SCHEMA)
    old = t.gstin
    Tenant.objects.filter(pk=t.pk).update(gstin="")
    try:
        inv = _draft_with_line(_customer())
        with pytest.raises(ValueError, match="GSTIN"):
            doc_svc.issue_invoice(inv)
    finally:
        Tenant.objects.filter(pk=t.pk).update(gstin=old)


def test_e29_stock_moves_on_issue_and_back_on_cancel(seller):
    p = _product(track_stock=True, stock_quantity=Decimal("10"))
    inv = _draft_with_line(_customer(), product=p, qty="3")
    doc_svc.issue_invoice(inv)
    p.refresh_from_db()
    assert p.stock_quantity == Decimal("7")
    doc_svc.cancel_invoice(CustomerInvoice.objects.get(pk=inv.pk), reason="wrong")
    p.refresh_from_db()
    assert p.stock_quantity == Decimal("10")


def test_e35_cancelling_the_invoice_reopens_its_order(seller):
    c = _customer()
    q = doc_svc.create_quotation(customer=c)
    from apps.erp.models import QuotationItem
    prod = _product()
    QuotationItem.objects.create(quotation=q, product=prod, quantity=1, unit_price=prod.unit_price, gst_rate=18)
    order = doc_svc.quotation_to_order(q)
    inv = doc_svc.order_to_invoice(order)
    assert inv.number.startswith("DRAFT-")
    doc_svc.issue_invoice(inv)
    doc_svc.cancel_invoice(CustomerInvoice.objects.get(pk=inv.pk), reason="customer cancelled")
    order.refresh_from_db()
    assert order.status == SalesOrderStatus.OPEN


def test_e24_an_order_can_be_cancelled_until_invoiced(seller):
    c = _customer()
    q = doc_svc.create_quotation(customer=c)
    from apps.erp.models import QuotationItem
    prod = _product()
    QuotationItem.objects.create(quotation=q, product=prod, quantity=1, unit_price=prod.unit_price, gst_rate=18)
    order = doc_svc.quotation_to_order(q)
    doc_svc.order_to_invoice(order)
    with pytest.raises(ValueError):
        doc_svc.cancel_order(order)
    doc_svc.delete_draft_invoice(order.invoices.first())
    assert doc_svc.cancel_order(order).status == SalesOrderStatus.CANCELLED


# ---- E26 / E17 line rules --------------------------------------------------

def test_e26_line_gst_must_be_a_slab():
    from apps.erp.serializers import CustomerInvoiceItemSerializer
    p = _product()
    s = CustomerInvoiceItemSerializer(data={"product": p.pk, "description": "x", "quantity": "1",
                                            "unit_price": "10", "gst_rate": "7"})
    assert not s.is_valid() and "gst_rate" in s.errors


def test_e17_custom_line_without_product(seller, admin):
    from apps.erp.views import InvoiceItemView
    inv = doc_svc.create_invoice(customer=_customer())
    r = _call(InvoiceItemView, "post", admin, {"description": "Freight", "hsn_sac": "996511",
                                               "quantity": "1", "unit_price": "750", "gst_rate": "18"}, pk=inv.pk)
    assert r.status_code == 201, r.data
    line = r.data["items"][0]
    assert line["product"] is None and line["product_name"] is None and line["line_total"] == "885.00"
    bad = _call(InvoiceItemView, "post", admin, {"quantity": "1", "unit_price": "10", "gst_rate": "18"}, pk=inv.pk)
    assert bad.status_code == 400


# ---- E1 / E4 / E3 / E5 customers --------------------------------------------

def test_e4_state_is_taken_from_the_gstin():
    from apps.erp.serializers import CustomerSerializer
    s = CustomerSerializer(data={"name": "Delhi Co", "gstin": "07AAGCB7383J1ZP"[:14] + "X"})
    s.is_valid()
    s = CustomerSerializer(data={"name": "KA Co", "gstin": VALID_KA})
    assert s.is_valid(), s.errors
    assert s.validated_data["state_code"] == "KA"


def test_e1_gstin_state_mismatch_and_bad_checksum_refused():
    from apps.erp.serializers import CustomerSerializer
    assert not CustomerSerializer(data={"name": "X", "gstin": VALID_MH, "state_code": "UP"}).is_valid()
    assert not CustomerSerializer(data={"name": "Y", "gstin": "27AAAAA0000A1Z5"}).is_valid()


def test_e3_customer_phone_normalised_and_e5_duplicates_refused():
    from apps.erp.serializers import CustomerSerializer
    s = CustomerSerializer(data={"name": "Dup", "phone": "98765 43210"})
    assert s.is_valid(), s.errors
    assert s.validated_data["phone"] == "+919876543210"
    s.save()
    assert not CustomerSerializer(data={"name": "dup"}).is_valid()
    _customer("G1", state="MH", gstin=VALID_MH)
    assert not CustomerSerializer(data={"name": "G2", "gstin": VALID_MH}).is_valid()


def test_e14_header_knows_interstate_before_any_line(seller):
    q = doc_svc.create_quotation(customer=_customer(state="MH"))
    assert q.is_interstate is True


# ---- E40 delete in use -------------------------------------------------------

def test_e40_deleting_a_used_customer_is_a_409_not_a_500(admin):
    from apps.erp.views import CustomerDetailView
    c = _customer()
    doc_svc.create_quotation(customer=c)
    r = _call(CustomerDetailView, "delete", admin, pk=c.pk)
    assert r.status_code == 409


# ---- E9 / E8 products --------------------------------------------------------

def test_e9_hsn_and_e8_units():
    from apps.erp.serializers import ProductSerializer
    assert not ProductSerializer(data={"name": "a", "sku": "a1", "hsn_sac": "ABCD", "unit_price": "1"}).is_valid()
    s = ProductSerializer(data={"name": "b", "sku": "b1", "hsn_sac": "4802", "unit_price": "1", "unit": "box"})
    assert s.is_valid(), s.errors


# ---- Quotation status rules (E19, E20, E21) -----------------------------------

def test_e19_empty_quotation_cannot_be_sent(admin):
    from apps.erp.views import QuotationStatusView
    q = doc_svc.create_quotation(customer=_customer())
    assert _call(QuotationStatusView, "post", admin, {"status": "sent"}, pk=q.pk).status_code == 400


def test_e21_expired_quotation_cannot_be_accepted(admin):
    from apps.erp.models import QuotationItem
    from apps.erp.views import QuotationStatusView
    q = doc_svc.create_quotation(customer=_customer(), quotation_date=timezone.localdate() - timedelta(days=10),
                                 valid_until=timezone.localdate() - timedelta(days=1))
    p = _product()
    QuotationItem.objects.create(quotation=q, product=p, quantity=1, unit_price=p.unit_price, gst_rate=18)
    r = _call(QuotationStatusView, "post", admin, {"status": "accepted"}, pk=q.pk)
    assert r.status_code == 400 and r.data["error"] == "expired"


def test_e20_lines_frozen_once_sent_and_revise_unfreezes(admin):
    from apps.erp.models import QuotationItem
    from apps.erp.views import QuotationItemView, QuotationStatusView
    q = doc_svc.create_quotation(customer=_customer())
    p = _product()
    QuotationItem.objects.create(quotation=q, product=p, quantity=1, unit_price=p.unit_price, gst_rate=18)
    assert _call(QuotationStatusView, "post", admin, {"status": "sent"}, pk=q.pk).status_code == 200
    add = {"product": p.pk, "description": "x", "quantity": "1", "unit_price": "10", "gst_rate": "18"}
    assert _call(QuotationItemView, "post", admin, add, pk=q.pk).status_code == 400
    assert _call(QuotationStatusView, "post", admin, {"status": "draft"}, pk=q.pk).status_code == 200
    assert _call(QuotationItemView, "post", admin, add, pk=q.pk).status_code == 201


# ---- Payments (E31, E33) -------------------------------------------------------

def test_e31_future_payment_refused_and_e33_payment_reversed(seller):
    inv = _draft_with_line(_customer())
    doc_svc.issue_invoice(inv)
    inv = CustomerInvoice.objects.get(pk=inv.pk)
    with pytest.raises(ValueError):
        doc_svc.record_payment(inv, amount=Decimal("10"), paid_on=timezone.localdate() + timedelta(days=5))
    pay = doc_svc.record_payment(inv, amount=inv.total_amount)
    assert CustomerInvoice.objects.get(pk=inv.pk).status == InvoiceStatus.PAID
    doc_svc.reverse_payment(pay)
    inv.refresh_from_db()
    assert inv.status == InvoiceStatus.ISSUED and inv.amount_paid == 0


# ---- E37 Tally export ----------------------------------------------------------

def test_e37_tally_export_streams_issued_invoices(seller, admin):
    from apps.erp.views import TallyExportView
    inv = _draft_with_line(_customer())
    doc_svc.issue_invoice(inv)
    request = factory.get("/x/")
    force_authenticate(request, user=admin); request.has_feature = lambda k: True
    r = TallyExportView.as_view()(request)
    body = b"".join(r.streaming_content).decode()
    assert "INV/" in body


# ---- Company profile -------------------------------------------------------------

def test_company_profile_can_be_edited_by_admin(admin):
    from apps.authentication.views import CompanyProfileAPIView
    t = Tenant.objects.get(schema_name=TEST_SCHEMA)
    old = (t.gstin, t.state, t.company_name)
    try:
        r = _call(CompanyProfileAPIView, "patch", admin, {"company_name": "Acme Realty", "gstin": VALID_MH, "state": ""})
        assert r.status_code == 200, r.data
        assert r.data["company_name"] == "Acme Realty" and r.data["state"] == "MH"
        bad = _call(CompanyProfileAPIView, "patch", admin, {"gstin": VALID_MH, "state": "UP"})
        assert bad.status_code == 400
    finally:
        Tenant.objects.filter(pk=t.pk).update(gstin=old[0], state=old[1], company_name=old[2])
