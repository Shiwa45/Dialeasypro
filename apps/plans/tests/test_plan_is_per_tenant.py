"""
Plan limits are read from THIS tenant's subscription.

Subscription lives in the shared schema. The bulk-campaign daily caps and the
lead-limit alert queried it with no tenant filter, so each tenant was held to
whichever tenant had subscribed most recently — too strict for some, unlimited
for others.
"""
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.db import connection

from apps.communications.tasks import _current_plan, _enforce_daily_limit
from apps.core.constants import SubscriptionStatus
from apps.core.exceptions import PlanLimitExceededException
from apps.leads.models import Lead
from apps.plans.models import Plan, Subscription
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def plans():
    """This tenant on a generous plan; a newer tenant on a tiny one."""
    cache.clear()
    ours = Tenant.objects.get(schema_name=connection.schema_name)
    generous = Plan.objects.create(
        name="Generous", slug="generous-t", max_leads=100_000, max_sms_per_day=10_000,
    )
    tiny = Plan.objects.create(name="Tiny", slug="tiny-t", max_leads=1, max_sms_per_day=1)

    Subscription.objects.filter(tenant=ours).update(status=SubscriptionStatus.CANCELLED)
    Subscription.objects.create(tenant=ours, plan=generous, status=SubscriptionStatus.ACTIVE)

    # Another tenant — no schema needed, only its shared-schema rows.
    other = Tenant(
        schema_name="other_tenant", company_name="Other",
        primary_contact_name="O", primary_contact_email="o@other.test",
        primary_contact_phone="+919800000000",
    )
    other.auto_create_schema = False
    schema = connection.schema_name
    connection.set_schema_to_public()  # django-tenants only creates tenants from public
    try:
        other.save()
    finally:
        connection.set_schema(schema)
    Subscription.objects.create(tenant=other, plan=tiny, status=SubscriptionStatus.ACTIVE)

    yield generous, tiny
    cache.clear()


def test_the_campaign_cap_comes_from_our_plan(plans):
    generous, _ = plans

    assert _current_plan() == generous
    _enforce_daily_limit("sms", 50)  # the other tenant's cap of 1 must not apply


def test_our_own_cap_is_still_enforced(plans):
    with pytest.raises(PlanLimitExceededException):
        _enforce_daily_limit("sms", 10_001)


def test_the_lead_limit_alert_uses_our_plan(plans):
    with patch("apps.core.consumers.broadcast_to_monitors") as alert:
        Lead.objects.create(name="Ravi", phone="+919812300001")
        Lead.objects.create(name="Sita", phone="+919812300002")

    limit_alerts = [
        c for c in alert.call_args_list
        if c.kwargs.get("data", {}).get("alert_type") == "lead_limit_reached"
    ]
    assert not limit_alerts, "two leads is nowhere near our 100,000 limit"
