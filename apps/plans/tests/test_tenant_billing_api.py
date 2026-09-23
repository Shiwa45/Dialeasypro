"""
What a tenant can see about their own subscription.

The CRM's Billing tab had nothing behind it. It told the paying customer to
visit `/superadmin/` — the platform operator's panel, which no tenant can sign
into — beside placeholder phone numbers of the form +91-1800-XXX-XXXX. There
was no API a tenant could call to learn which plan they were on, what it
allows, how much of it they had used, or when it renews.
"""
from decimal import Decimal

import pytest
from django.db import connection
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.core.constants import FeatureKey, SubscriptionStatus
from apps.plans.api_views import TenantBillingAPIView
from apps.plans.models import Invoice, Plan, PlanFeature, Subscription
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    t = Tenant.objects.get(schema_name=connection.schema_name)
    t.max_agents_override = None
    t.save(update_fields=["max_agents_override"])
    Subscription.objects.filter(tenant=t).delete()
    Invoice.objects.filter(tenant=t).delete()
    return t


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(
        email="owner@example.com", name="Owner", password="Pw@12345678",
    )


@pytest.fixture
def agent():
    return Agent.objects.create_agent(
        email="floor@example.com", name="Floor Agent", password="Pw@12345678",
    )


@pytest.fixture
def plan(tenant):
    plan, _ = Plan.objects.get_or_create(
        slug="billing-test",
        defaults={
            "name": "Growth",
            "description": "For growing teams.",
            "price_monthly": Decimal("2999.00"),
            "price_yearly": Decimal("28790.00"),
            "max_agents": 20,
            "max_leads": 50000,
            "max_leads_per_day": 2000,
            "custom_fields_limit": 30,
        },
    )
    PlanFeature.objects.get_or_create(
        plan=plan, feature_key=FeatureKey.BULK_WHATSAPP, defaults={"is_enabled": True},
    )
    tenant.plan = plan
    tenant.save(update_fields=["plan"])
    return plan


def _subscribe(tenant, plan, **overrides):
    fields = {
        "tenant": tenant, "plan": plan,
        "status": SubscriptionStatus.ACTIVE, "billing_cycle": "monthly",
    }
    fields.update(overrides)
    sub = Subscription.objects.create(**fields)
    from django.core.cache import cache
    cache.delete(f"tenant_plan_id:{connection.schema_name}")
    return sub


def _get(user):
    request = APIRequestFactory().get("/api/v1/billing/")
    force_authenticate(request, user=user)
    response = TenantBillingAPIView.as_view()(request)
    response.render()
    return response


# ---- The plan they are on ----------------------------------------------

def test_an_admin_sees_the_plan_they_are_paying_for(tenant, admin, plan):
    _subscribe(tenant, plan)

    r = _get(admin)

    assert r.status_code == 200, r.data
    assert r.data["plan"]["name"] == "Growth"
    assert r.data["plan"]["price_monthly"] == "2999.00"


def test_the_subscription_plan_wins_over_the_tenant_copy(tenant, admin, plan):
    """
    Billing runs on the subscription. The tenant's own plan field is a
    convenience copy, and showing it would tell a customer they are on a plan
    they are not being charged for.
    """
    other = Plan.objects.create(slug="stale-copy", name="Starter", price_monthly=Decimal("999"))
    tenant.plan = other
    tenant.save(update_fields=["plan"])
    _subscribe(tenant, plan)

    assert _get(admin).data["plan"]["name"] == "Growth"


def test_renewal_and_status_are_reported(tenant, admin, plan):
    from django.utils import timezone
    from datetime import timedelta

    _subscribe(
        tenant, plan,
        # Plus an hour: days_until_renewal truncates, so a period ending in
        # exactly 9 days minus a microsecond of test runtime reads as 8.
        current_period_end=timezone.now() + timedelta(days=9, hours=1),
    )

    sub = _get(admin).data["subscription"]
    assert sub["status"] == SubscriptionStatus.ACTIVE
    assert sub["billing_cycle"] == "monthly"
    assert sub["days_until_renewal"] == 9
    assert sub["is_active"] is True


def test_a_trial_with_no_subscription_row_still_reports_itself(tenant, admin, plan):
    """
    Onboarding puts the trial dates on the tenant. Rendering nothing here
    would read to the customer as "you have no account".
    """
    r = _get(admin)

    assert r.data["subscription"]["status"] == tenant.subscription_status
    assert r.data["plan"]["name"] == "Growth", "from the tenant's own plan"


# ---- Usage against the allowance ---------------------------------------

def test_usage_counts_what_a_tenant_runs_out_of(tenant, admin, plan):
    _subscribe(tenant, plan)

    usage = _get(admin).data["usage"]

    assert usage["agents"]["used"] == 1, "the admin holds a seat"
    assert usage["agents"]["limit"] == 20
    assert usage["leads"]["limit"] == 50000
    assert usage["custom_fields"]["limit"] == 30


def test_the_seat_bar_follows_the_tenants_own_cap(tenant, admin, plan):
    """
    The number that matters is the one the API enforces. A tenant given extra
    seats by hand would otherwise see their bar against the plan's figure.
    """
    _subscribe(tenant, plan)
    tenant.max_agents_override = 3
    tenant.save(update_fields=["max_agents_override"])

    assert _get(admin).data["usage"]["agents"]["limit"] == 3


def test_an_unmetered_resource_reports_unknown_not_zero(tenant, admin, plan):
    """Storage is not metered yet; "0 GB used" would be a made-up number."""
    _subscribe(tenant, plan)

    assert _get(admin).data["usage"]["storage_gb"]["used"] is None


# ---- Features and invoices ---------------------------------------------

def test_the_plans_features_are_listed_with_readable_labels(tenant, admin, plan):
    _subscribe(tenant, plan)

    features = _get(admin).data["features"]

    entry = next(f for f in features if f["key"] == FeatureKey.BULK_WHATSAPP)
    assert entry["enabled"] is True
    assert entry["label"] != FeatureKey.BULK_WHATSAPP, "a key is not a label"


def test_invoices_are_listed_newest_first(tenant, admin, plan):
    from datetime import date

    sub = _subscribe(tenant, plan)
    for day, number in ((1, "INV-001"), (15, "INV-002")):
        Invoice.objects.create(
            tenant=tenant, subscription=sub, invoice_number=number,
            invoice_date=date(2026, 8, day), base_amount=Decimal("2999"),
            total_amount=Decimal("3538.82"),
        )

    invoices = _get(admin).data["invoices"]

    assert [i["invoice_number"] for i in invoices] == ["INV-002", "INV-001"]


def test_another_tenants_invoices_are_never_shown(tenant, admin, plan):
    from django_tenants.utils import schema_context

    # django-tenants refuses to create a Tenant from inside a tenant schema,
    # and auto_create_schema is a class attribute rather than a field — this
    # row exists only to own an invoice, so it needs no PostgreSQL schema.
    with schema_context("public"):
        other = Tenant(
            schema_name="other_tenant_billing", company_name="Someone Else",
            primary_contact_name="X", primary_contact_email="x@example.com",
            primary_contact_phone="+919999999999",
        )
        other.auto_create_schema = False
        other.save()
        Invoice.objects.create(
            tenant=other, invoice_number="INV-OTHER",
            base_amount=Decimal("999"), total_amount=Decimal("1178.82"),
        )

    _subscribe(tenant, plan)

    numbers = [i["invoice_number"] for i in _get(admin).data["invoices"]]

    assert "INV-OTHER" not in numbers


# ---- Who may look ------------------------------------------------------

def test_an_agent_cannot_read_the_companys_billing(tenant, agent, plan):
    """Invoice amounts and GST totals are not floor-level information."""
    _subscribe(tenant, plan)

    assert _get(agent).status_code == 403


# ---- Support details ---------------------------------------------------

def test_support_contact_comes_from_platform_settings(tenant, admin, plan):
    from apps.superadmin.models import GlobalSettings
    from django.core.cache import cache

    GlobalSettings.objects.update_or_create(
        key="support_email", defaults={"value": "help@example.com"},
    )
    cache.delete("global_setting:support_email")

    assert _get(admin).data["support"]["email"] == "help@example.com"


def test_an_unconfigured_phone_number_is_blank_not_a_placeholder(tenant, admin, plan):
    """
    The tab used to print "+91-1800-XXX-XXXX" to customers. A blank renders as
    nothing; a placeholder renders as a number someone dials.
    """
    support = _get(admin).data["support"]

    assert support["phone"] == ""
    assert "XXX" not in str(support)
