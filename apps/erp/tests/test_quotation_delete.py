"""Deleting a locked quotation is a 400, not a 500 (LOW-11)."""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.erp.models import Customer, Quotation
from apps.erp.views import QuotationDetailView

pytestmark = pytest.mark.django_db


def _delete(quotation):
    admin = Agent.objects.create_tenant_admin(email="own@x.com", name="Own", password="Pw@12345678")
    request = APIRequestFactory().delete(f"/api/v1/erp/quotations/{quotation.pk}/")
    force_authenticate(request, user=admin)
    request.has_feature = lambda key: True
    response = QuotationDetailView.as_view()(request, pk=quotation.pk)
    response.render()
    return response


@pytest.fixture
def customer():
    return Customer.objects.create(name="Acme")


def test_a_converted_quotation_cannot_be_deleted_and_says_why(customer):
    quotation = Quotation.objects.create(number="Q-1", customer=customer, status="converted")

    response = _delete(quotation)

    assert response.status_code == 400
    assert Quotation.objects.filter(pk=quotation.pk).exists()


def test_a_draft_quotation_can_be_deleted(customer):
    quotation = Quotation.objects.create(number="Q-2", customer=customer, status="draft")

    assert _delete(quotation).status_code == 204
