"""
The platform panel's per-client field page (Tenants → Import fields).

It now also sets the client's lead form — whether Budget / Deal Value show and
what they are called (app item #10) — and a dropdown field can be given its
options, without which it rendered as an empty picker in the app.
"""
import pytest
from django.contrib.admin.sites import site
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import connection
from django.test import RequestFactory
from django_tenants.utils import schema_context

from apps.leads.models import CustomField
from apps.tenants.admin import TenantAdmin
from apps.tenants.models import Tenant

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_public")]


class _Staff:
    is_active = is_staff = is_superuser = True
    pk = 1

    def has_perm(self, *a, **k):
        return True


def _post(tenant, data):
    request = RequestFactory().post("/", data)
    request.user = _Staff()
    request.session = {}
    request._messages = FallbackStorage(request)
    schema = connection.schema_name
    connection.set_schema_to_public()
    try:
        return TenantAdmin(Tenant, site).import_fields_view(request, tenant.pk)
    finally:
        connection.set_schema(schema)


@pytest.fixture
def tenant():
    return Tenant.objects.get(schema_name=connection.schema_name)


def test_the_lead_form_can_hide_and_rename_money_fields(tenant):
    _post(tenant, {
        "action": "lead_form",
        "budget_show": "on", "budget_label": "Order Value",
        "deal_value_label": "Deal Value",  # checkbox unticked -> hidden
    })

    tenant.refresh_from_db()
    assert tenant.lead_form() == {
        "budget": {"show": True, "label": "Order Value"},
        "deal_value": {"show": False, "label": "Deal Value"},
    }


def test_a_dropdown_field_gets_its_options(tenant):
    _post(tenant, {"action": "add", "name": "Property Type", "field_type": "dropdown",
                   "options": "1BHK, 2BHK , ,3BHK"})

    with schema_context(tenant.schema_name):
        field = CustomField.objects.get(name="Property Type")
    assert field.options == ["1BHK", "2BHK", "3BHK"]
