"""
Locked features are shown, not hidden.

The CRM used to drop a feature from the navigation when the plan lacked it,
so a customer never learned it existed. Every feature is now shown, and one
the plan doesn't include opens an upgrade screen — which needs to say what
the feature is, which plans include it and who to ask, before the feature's
own endpoints (which answer 402) have been called.
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.authentication.views import TenantFeaturesAPIView
from apps.core.constants import FeatureKey, ModuleKey
from apps.plans.models import Plan, PlanFeature
from apps.plans.upgrade import upgrade_catalog

pytestmark = pytest.mark.django_db


def _plan(slug, name, keys, *, price, public=True, active=True):
    plan = Plan.objects.create(
        slug=slug, name=name, price_monthly=Decimal(price), price_yearly=Decimal(price) * 10,
        is_public=public, is_active=active,
    )
    for key in keys:
        PlanFeature.objects.create(plan=plan, feature_key=key, is_enabled=True)
    return plan


@pytest.fixture
def plans():
    hrms = ModuleKey.FEATURES[ModuleKey.HRMS]
    _plan("upg-pro", "Upg Pro", [FeatureKey.AGENT_MONITORING, *hrms], price="4999")
    _plan("upg-plus", "Upg Plus", [FeatureKey.AGENT_MONITORING, hrms[0]], price="2999")
    _plan("upg-hidden", "Upg Hidden", [FeatureKey.AGENT_MONITORING, *hrms], price="1", public=False)
    _plan("upg-retired", "Upg Retired", [FeatureKey.AGENT_MONITORING, *hrms], price="2", active=False)


def test_a_locked_feature_says_what_it_is_and_which_plans_have_it(plans):
    catalog = upgrade_catalog({})

    entry = catalog["features"][FeatureKey.AGENT_MONITORING]
    assert entry["label"] == FeatureKey.LABELS[FeatureKey.AGENT_MONITORING]
    upg = [p for p in entry["plans"] if p.startswith("Upg ")]
    assert upg == ["Upg Plus", "Upg Pro"], "cheapest first; hidden and retired plans are not offered"


def test_features_the_tenant_has_are_not_listed(plans):
    catalog = upgrade_catalog({FeatureKey.AGENT_MONITORING: True})

    assert FeatureKey.AGENT_MONITORING not in catalog["features"]


def test_a_module_is_offered_only_on_plans_with_all_of_it(plans):
    catalog = upgrade_catalog({})

    module = catalog["modules"][ModuleKey.HRMS]
    assert module["label"] == "HRMS"
    assert [p for p in module["plans"] if p.startswith("Upg ")] == ["Upg Pro"]


def test_an_active_module_is_not_listed(plans):
    enabled = {k: True for k in ModuleKey.FEATURES[ModuleKey.HRMS]}

    assert ModuleKey.HRMS not in upgrade_catalog(enabled)["modules"]


def test_the_features_endpoint_carries_the_upgrade_details(plans):
    agent = Agent.objects.create_agent(email="u@example.com", name="U", password="Pw@12345678")
    request = APIRequestFactory().get("/api/v1/auth/features/")
    request.tenant_features = {FeatureKey.LEAD_IMPORT: True}
    force_authenticate(request, user=agent)

    r = TenantFeaturesAPIView.as_view()(request)

    assert r.status_code == 200
    upgrade = r.data["upgrade"]
    assert FeatureKey.LEAD_IMPORT not in upgrade["features"]
    assert "Upg Pro" in upgrade["features"][FeatureKey.AGENT_MONITORING]["plans"]
    assert set(upgrade["support"]) == {"platform_name", "email", "phone", "whatsapp"}
