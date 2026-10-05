"""The data migration that adds the Agent Web Panel feature to existing plans."""
import importlib

import pytest
from django.apps import apps as django_apps
from django.db import connection

from apps.plans.models import Plan, PlanFeature

pytestmark = pytest.mark.django_db

migration = importlib.import_module("apps.plans.migrations.0005_agent_web_access_feature")


def _plan(slug):
    return Plan.objects.get_or_create(slug=slug, defaults={"name": slug.title()})[0]


def test_on_for_top_plans_off_for_the_rest_and_idempotent():
    connection.set_schema_to_public()
    PlanFeature.objects.filter(feature_key="agent_web_access").delete()
    plans = {slug: _plan(slug) for slug in ("starter", "growth", "business", "enterprise")}

    migration.add_feature(django_apps, None)
    migration.add_feature(django_apps, None)  # a re-run changes nothing

    rows = {
        row.plan.slug: row.is_enabled
        for row in PlanFeature.objects.filter(feature_key="agent_web_access", plan__in=plans.values())
    }
    assert rows == {"starter": False, "growth": False, "business": True, "enterprise": True}


def test_does_nothing_inside_a_tenant_schema():
    # The autouse fixture has already pointed the connection at the tenant schema.
    assert connection.schema_name != "public"
    before = PlanFeature.objects.filter(feature_key="agent_web_access").count()
    migration.add_feature(django_apps, None)
    assert PlanFeature.objects.filter(feature_key="agent_web_access").count() == before
