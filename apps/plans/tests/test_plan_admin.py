"""
Managing plans and plan features from the super admin panel.

Found by reviewing the panel against the live plans:

  * The plan page listed only features that already had a row. A feature
    added to the product later could not be switched on from it — which is
    how Enterprise, the top plan, ended up without the four Recruitment
    features that Business has. A new plan opened with 64 blank rows.
  * The "Features" column read enabled/rows: Starter showed "9/10" while it
    has 9 of the 64 features.
  * "Delete selected" on plan features or tenant entitlements skipped the
    cache clear, so tenants kept a removed feature for up to five minutes.
  * The tenant form offered retired (inactive) plans.
  * The tenant's Billing tab ignored add-ons: a customer who bought HRMS saw
    it marked as not included.
"""
import pytest
from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.core.constants import FeatureKey, SubscriptionStatus
from apps.plans.admin import (
    PlanAdmin,
    PlanFeatureAdmin,
    PlanFeatureInline,
    TenantEntitlementAdmin,
)
from apps.plans.api_views import TenantBillingAPIView
from apps.plans.models import Plan, PlanFeature, Subscription, TenantEntitlement
from apps.tenants.admin import TenantAdmin
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db


class Boss:
    is_active = is_staff = is_superuser = True
    pk = id = 1
    email = "boss@platform.test"

    def has_perm(self, *a, **k):
        return True


@pytest.fixture
def tenant():
    return Tenant.objects.get(schema_name=connection.schema_name)


@pytest.fixture
def plan():
    p = Plan.objects.create(name="QA Plan", slug="qa-plan")
    PlanFeature.objects.create(plan=p, feature_key=FeatureKey.LEAD_IMPORT, is_enabled=True)
    PlanFeature.objects.create(plan=p, feature_key=FeatureKey.BULK_SMS, is_enabled=False)
    return p


def _req(method="get", data=None):
    r = getattr(RequestFactory(), method)("/superadmin/", data or {})
    r.user = Boss()
    return r


def _formset(plan, data=None):
    model_admin = PlanAdmin(Plan, admin.site)
    inline = PlanFeatureInline(Plan, admin.site)
    request = _req("post" if data is not None else "get", data)
    FormSet = inline.get_formset(request, plan)
    kwargs = model_admin.get_formset_kwargs(request, plan, inline, FormSet.get_default_prefix())
    return FormSet(**kwargs)


def _post_data(fs, plan, tick=()):
    """What the browser sends back for an untouched page, plus `tick`ed rows."""
    p = fs.prefix
    data = {
        f"{p}-TOTAL_FORMS": str(fs.total_form_count()),
        f"{p}-INITIAL_FORMS": str(fs.initial_form_count()),
        f"{p}-MIN_NUM_FORMS": "0",
        f"{p}-MAX_NUM_FORMS": "1000",
    }
    for form in fs.forms:
        fp = form.prefix
        if form.instance.pk:
            data[f"{fp}-id"] = str(form.instance.pk)
            data[f"{fp}-plan"] = str(plan.pk)
            data[f"{fp}-feature_key"] = form.instance.feature_key
            if form.instance.is_enabled:
                data[f"{fp}-is_enabled"] = "on"
        else:
            key = form.initial["feature_key"]
            data[f"{fp}-feature_key"] = key
            if key in tick:
                data[f"{fp}-is_enabled"] = "on"
    return data


# ---- The plan page lists every feature --------------------------------

def test_the_plan_page_lists_every_feature(plan):
    fs = _formset(plan)
    keys = [f.instance.feature_key if f.instance.pk else f.initial["feature_key"] for f in fs.forms]
    assert sorted(keys) == sorted(FeatureKey.ALL)
    missing = [f for f in fs.forms if not f.instance.pk]
    assert all(f.initial["is_enabled"] is False for f in missing)


def test_a_new_plan_lists_every_feature_prefilled():
    fs = _formset(None)
    assert sorted(f.initial["feature_key"] for f in fs.forms) == sorted(FeatureKey.ALL)


def test_saving_untouched_rows_adds_nothing(plan):
    data = _post_data(_formset(plan), plan)
    fs = _formset(plan, data)
    assert fs.is_valid(), fs.errors
    fs.save()
    assert plan.features.count() == 2


def test_ticking_a_missing_feature_switches_it_on(plan):
    data = _post_data(_formset(plan), plan, tick={FeatureKey.ATS_CANDIDATES})
    fs = _formset(plan, data)
    assert fs.is_valid(), fs.errors
    fs.save()
    assert plan.features.count() == 3
    assert plan.features.get(feature_key=FeatureKey.ATS_CANDIDATES).is_enabled


# ---- The list column ----------------------------------------------------

def test_the_feature_column_counts_out_of_every_feature(plan):
    model_admin = PlanAdmin(Plan, admin.site)
    obj = model_admin.get_queryset(_req()).get(pk=plan.pk)
    assert f"1/{len(FeatureKey.ALL)}" in str(model_admin.feature_count(obj))


# ---- Bulk deletes take effect at once ---------------------------------

def test_bulk_deleting_plan_features_clears_tenant_caches(tenant, plan):
    Subscription.objects.create(tenant=tenant, plan=plan, status=SubscriptionStatus.ACTIVE)
    cache.set(f"tenant_features:{tenant.schema_name}", {FeatureKey.LEAD_IMPORT: True})
    PlanFeatureAdmin(PlanFeature, admin.site).delete_queryset(
        _req("post"), PlanFeature.objects.filter(plan=plan, feature_key=FeatureKey.LEAD_IMPORT),
    )
    assert cache.get(f"tenant_features:{tenant.schema_name}") is None


def test_bulk_deleting_entitlements_clears_the_tenant_cache(tenant):
    TenantEntitlement.objects.create(tenant=tenant, feature_key=FeatureKey.HRMS_PAYROLL)
    cache.set(f"tenant_features:{tenant.schema_name}", {FeatureKey.HRMS_PAYROLL: True})
    TenantEntitlementAdmin(TenantEntitlement, admin.site).delete_queryset(
        _req("post"), TenantEntitlement.objects.filter(tenant=tenant),
    )
    assert cache.get(f"tenant_features:{tenant.schema_name}") is None


# ---- Tenant form --------------------------------------------------------

def test_the_tenant_form_offers_only_active_plans_plus_the_current_one(tenant, plan):
    retired = Plan.objects.create(name="Retired", slug="retired", is_active=False)
    current = Plan.objects.create(name="Legacy", slug="legacy", is_active=False)
    Tenant.objects.filter(pk=tenant.pk).update(plan=current)
    tenant.refresh_from_db()
    form = TenantAdmin(Tenant, admin.site).get_form(_req(), tenant, change=True)
    offered = set(form.base_fields["plan"].queryset)
    assert plan in offered and current in offered and retired not in offered


# ---- Billing tab shows add-ons -----------------------------------------

def test_the_billing_tab_includes_add_ons(tenant, plan):
    Subscription.objects.filter(tenant=tenant).delete()
    Subscription.objects.create(tenant=tenant, plan=plan, status=SubscriptionStatus.ACTIVE)
    owner = Agent.objects.create_tenant_admin(email="own@b.t", name="Own", password="Pw@12345678")
    request = APIRequestFactory().get("/api/v1/billing/")
    force_authenticate(request, user=owner)
    request.tenant_features = {FeatureKey.LEAD_IMPORT: True, FeatureKey.HRMS_PAYROLL: True}
    r = TenantBillingAPIView.as_view()(request)
    features = {f["key"]: f["enabled"] for f in r.data["features"]}
    assert features[FeatureKey.HRMS_PAYROLL] is True
    assert features[FeatureKey.LEAD_IMPORT] is True
    assert features[FeatureKey.BULK_SMS] is False
