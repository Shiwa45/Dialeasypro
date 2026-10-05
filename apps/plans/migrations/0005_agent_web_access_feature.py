"""
Add the "Agent Web Panel" feature (FeatureKey.AGENT_WEB_ACCESS) to every plan.

On for Business and Enterprise — the plans that already carry every feature,
matching setup_initial_data and the admin's "sync all features" action — and
present but OFF on the others, so it shows as a ready-made checkbox on each
plan in the admin. Change it per plan there.

Existing tenants' feature maps are cached; they are cleared here so the new
feature takes effect immediately rather than after the cache expires.
"""
from django.db import connection, migrations

FEATURE = "agent_web_access"
ON_FOR = ("business", "enterprise")


def add_feature(apps, schema_editor):
    if connection.schema_name != "public":
        return
    Plan = apps.get_model("plans", "Plan")
    PlanFeature = apps.get_model("plans", "PlanFeature")
    Subscription = apps.get_model("plans", "Subscription")

    for plan in Plan.objects.all():
        PlanFeature.objects.get_or_create(
            plan=plan, feature_key=FEATURE,
            defaults={"is_enabled": plan.slug in ON_FOR},
        )

    try:
        from django.core.cache import cache

        schemas = set(Subscription.objects.values_list("tenant__schema_name", flat=True))
        cache.delete_many([f"tenant_features:{schema}" for schema in schemas])
    except Exception:  # pragma: no cover — a cold or absent cache is fine
        pass


def remove_feature(apps, schema_editor):
    if connection.schema_name != "public":
        return
    apps.get_model("plans", "PlanFeature").objects.filter(feature_key=FEATURE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("plans", "0004_alter_planfeature_feature_key_alter_tenantentitlement_feature_key"),
    ]

    operations = [
        migrations.RunPython(add_feature, remove_feature),
    ]
