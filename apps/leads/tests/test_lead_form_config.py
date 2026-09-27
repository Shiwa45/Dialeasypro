"""
What the mobile Add Lead form shows, per client (app items #7 and #10).

Custom fields set for a client in the platform panel must appear on the app's
Add Lead form, and the standard Budget / Deal Value fields can be hidden or
renamed per client.
"""
import pytest
from django.db import connection
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.leads.models import CustomField
from apps.leads.views import LeadFormConfigView
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db


def _config():
    agent = Agent.objects.create_agent(email="a@x.com", name="A", password="Pw@12345678")
    request = APIRequestFactory().get("/api/v1/leads/form-config/")
    force_authenticate(request, user=agent)
    response = LeadFormConfigView.as_view()(request)
    response.render()
    return response.data


def test_defaults_show_both_money_fields():
    Tenant.objects.filter(schema_name=connection.schema_name).update(lead_form_settings={})

    standard = _config()["standard"]

    assert standard["budget"] == {"show": True, "label": "Budget (₹)"}
    assert standard["deal_value"] == {"show": True, "label": "Deal Value (₹)"}


def test_a_client_can_hide_and_rename_them():
    Tenant.objects.filter(schema_name=connection.schema_name).update(lead_form_settings={
        "budget": {"show": True, "label": "Order Value"},
        "deal_value": {"show": False, "label": ""},
    })

    standard = _config()["standard"]

    assert standard["budget"] == {"show": True, "label": "Order Value"}
    assert standard["deal_value"]["show"] is False


def test_active_custom_fields_are_included_in_order():
    CustomField.objects.create(name="Property Type", field_key="property_type",
                               field_type="dropdown", options=["1BHK", "2BHK"], sort_order=1)
    CustomField.objects.create(name="Site", field_key="site", sort_order=0)
    CustomField.objects.create(name="Old", field_key="old", is_active=False)

    fields = _config()["custom_fields"]

    assert [f["field_key"] for f in fields] == ["site", "property_type"]
    assert fields[1]["options"] == ["1BHK", "2BHK"]
