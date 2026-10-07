"""
TeleCRM Backend — apps/plans/upgrade.py

What the web app needs to show a locked feature instead of hiding it.

Every feature appears in the CRM's navigation whatever the plan; opening one
the plan doesn't include shows an upgrade screen. That screen has to say what
the feature is, which plans include it, and who to ask — before any request
to the feature has been made, so it is sent with /auth/features/.
"""
from django.conf import settings

from apps.core.constants import FeatureKey, ModuleKey


def support_contacts() -> dict:
    """
    Who to contact about plans and billing. Read from the platform's own
    settings; a contact that has not been configured is left blank rather
    than invented.
    """
    from apps.superadmin.models import GlobalSettings

    def setting(key, default=""):
        try:
            return GlobalSettings.get(key, default) or default
        except Exception:  # noqa: BLE001 — a missing table must not 500 the caller
            return default

    return {
        "platform_name": setting("platform_name", "DialSathi"),
        "email": setting("support_email", settings.SUPPORT_EMAIL),
        "phone": setting("support_phone", ""),
        "whatsapp": setting("support_whatsapp", ""),
    }


def _plans_by_feature() -> dict[str, list[str]]:
    """{feature_key: [plan name, ...]} over the plans a customer can buy, cheapest first."""
    from apps.plans.models import PlanFeature

    rows = (
        PlanFeature.objects.filter(is_enabled=True, plan__is_active=True, plan__is_public=True)
        .order_by("plan__sort_order", "plan__price_monthly")
        .values_list("feature_key", "plan__name")
    )
    plans: dict[str, list[str]] = {}
    for key, name in rows:
        plans.setdefault(key, [])
        if name not in plans[key]:
            plans[key].append(name)
    return plans


def upgrade_catalog(features: dict[str, bool]) -> dict:
    """
    Upgrade details for everything this tenant can NOT use.

        {
          "features": {key: {"label": ..., "plans": [...]}},   # locked features only
          "modules":  {key: {"label": ..., "plans": [...]}},   # locked modules only
        }

    `plans` lists the public plans that include it. A module is also sold as
    an add-on on any plan; the client says so.
    """
    try:
        plans = _plans_by_feature()
    except Exception:  # noqa: BLE001 — upsell details are never worth a 500
        plans = {}

    locked_features = {
        key: {"label": FeatureKey.LABELS.get(key, key), "plans": plans.get(key, [])}
        for key in FeatureKey.ALL
        if not features.get(key)
    }

    module_labels = dict(ModuleKey.CHOICES)
    locked_modules = {}
    for module, keys in ModuleKey.FEATURES.items():
        if all(features.get(k) for k in keys):
            continue
        # A plan includes the module only when it includes every feature of it.
        candidates = None
        for key in keys:
            names = plans.get(key, [])
            candidates = names if candidates is None else [n for n in candidates if n in names]
        locked_modules[module] = {
            "label": module_labels.get(module, module),
            "plans": candidates or [],
        }

    return {"features": locked_features, "modules": locked_modules}
