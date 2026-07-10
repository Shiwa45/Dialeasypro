"""
TeleCRM Backend — apps/plans/management/commands/entitlements.py

Manage tenant feature entitlements, and safely roll out plan enforcement.

Enforcement only bites once features are actually checked. Two hazards exist
for EXISTING tenants at cutover:

  1. A tenant with no active Subscription row resolves to an EMPTY feature map
     (see TenantFeatureFlagMiddleware) → they lose everything.
  2. A tenant whose plan legitimately lacks a feature they've been using for
     free (because nothing was enforced) → they lose it abruptly.

`--ensure-subscriptions` fixes (1). `--grandfather` fixes (2) by granting the
newly-gated features as explicit TenantEntitlements, which an admin can revoke
later per-tenant.

Usage:
    # See what each tenant resolves to today (safe, read-only)
    python manage.py entitlements --report

    # Step 1: give every tenant an active subscription on their plan
    python manage.py entitlements --ensure-subscriptions

    # Step 2: grandfather the features we now enforce, so nobody is cut off
    python manage.py entitlements --grandfather

    # Sell / revoke an add-on module for one tenant
    python manage.py entitlements --tenant=demo --grant-module=hrms
    python manage.py entitlements --tenant=demo --revoke-module=hrms

    # Grant or revoke a single feature
    python manage.py entitlements --tenant=demo --grant=ai_call_transcription
    python manage.py entitlements --tenant=demo --revoke=lead_export

    # Preview any of the above
    python manage.py entitlements --grandfather --dry-run
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.constants import FeatureKey, ModuleKey, PlanSlug, SubscriptionStatus

# Gates applied imperatively (inside a handler or get_permissions), which cannot
# be discovered by walking the URLconf. Everything declared as
# `required_feature = ...` on a view IS discovered automatically — see
# discover_enforced_features() — so this list stays tiny and rarely changes.
#
# Deliberately EXCLUDED: the per-lead-source integration keys
# (LeadSource.FEATURE_MAP). A tenant must not silently gain every marketplace
# integration just because we switched enforcement on.
DYNAMIC_FEATURES = [
    FeatureKey.CUSTOM_FIELDS,        # CustomFieldListView.get_permissions()
    FeatureKey.AGENT_MONITORING,     # also gated on the WebSocket consumer
    # Bulk / one-click gates resolve from the request's channel at runtime.
    FeatureKey.BULK_WHATSAPP,
    FeatureKey.BULK_EMAIL,
    FeatureKey.BULK_SMS,
    FeatureKey.ONE_CLICK_WHATSAPP,
    FeatureKey.ONE_CLICK_EMAIL,
    FeatureKey.ONE_CLICK_SMS,
]


def discover_enforced_features() -> list:
    """
    The set of features actually enforced right now = every `required_feature`
    reachable from the URLconf, plus the imperative gates above.

    Deriving this from the code (rather than a hand-maintained list) means a
    newly-gated endpoint can never be forgotten by --grandfather, which would
    otherwise silently strip the feature from every existing tenant.
    """
    from django.conf import settings
    from django.urls import get_resolver

    found = set(DYNAMIC_FEATURES)

    def walk(patterns):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                walk(p.url_patterns)
                continue
            cb = getattr(p, "callback", None)
            view = getattr(cb, "cls", None) or getattr(cb, "view_class", None)
            if view is None:
                continue
            if key := getattr(view, "required_feature", None):
                found.add(key)
            for perm in getattr(view, "permission_classes", None) or []:
                if key := getattr(perm, "required_feature", None):
                    found.add(key)

    try:
        walk(get_resolver(settings.ROOT_URLCONF).url_patterns)
    except Exception:  # pragma: no cover - defensive
        pass

    return sorted(found)


class Command(BaseCommand):
    help = "Inspect and manage tenant feature entitlements; roll out plan enforcement."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=str, help="Tenant schema name")
        parser.add_argument("--report", action="store_true", help="Show effective features per tenant")
        parser.add_argument("--ensure-subscriptions", action="store_true",
                            help="Create an active Subscription for tenants missing one")
        parser.add_argument("--grandfather", action="store_true",
                            help="Grant currently-enforced features to all existing tenants")
        parser.add_argument("--grant-module", type=str, help=f"One of: {', '.join(ModuleKey.ALL)}")
        parser.add_argument("--revoke-module", type=str, help=f"One of: {', '.join(ModuleKey.ALL)}")
        parser.add_argument("--grant", type=str, help="Grant a single feature key")
        parser.add_argument("--revoke", type=str, help="Revoke a single feature key")
        parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")

    def handle(self, *args, **o):
        self.dry = o["dry_run"]

        if o["report"]:
            return self._report()
        if o["ensure_subscriptions"]:
            return self._ensure_subscriptions()
        if o["grandfather"]:
            return self._grandfather()
        if o["grant_module"] or o["revoke_module"] or o["grant"] or o["revoke"]:
            return self._mutate(o)

        raise CommandError("Nothing to do. See --help for actions.")

    # ---- Helpers ------------------------------------------------

    def _tenants(self, schema=None):
        from apps.tenants.models import Tenant
        qs = Tenant.objects.exclude(schema_name="public").filter(is_active=True)
        if schema:
            qs = qs.filter(schema_name=schema)
            if not qs.exists():
                raise CommandError(f"Tenant '{schema}' not found (or inactive).")
        return qs.order_by("schema_name")

    def _effective(self, tenant) -> dict:
        from apps.core.middleware import TenantFeatureFlagMiddleware
        mw = TenantFeatureFlagMiddleware(lambda r: None)
        return mw._load_features_from_db(tenant)

    # ---- Actions ------------------------------------------------

    def _report(self):
        from apps.plans.models import Subscription, TenantEntitlement

        for t in self._tenants():
            sub = Subscription.objects.filter(
                tenant=t, status__in=SubscriptionStatus.ACTIVE_STATUSES
            ).select_related("plan").first()
            features = self._effective(t)
            on = sorted(k for k, v in features.items() if v)
            ents = TenantEntitlement.objects.filter(tenant=t).count()

            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{t.schema_name} — {t.company_name}"))
            self.stdout.write(f"  plan          : {sub.plan.slug if sub else self.style.ERROR('NO ACTIVE SUBSCRIPTION')}")
            self.stdout.write(f"  entitlements  : {ents}")
            self.stdout.write(f"  features ON   : {len(on)}")
            missing = [f for f in discover_enforced_features() if not features.get(f)]
            if missing:
                self.stdout.write(self.style.WARNING(f"  would LOSE     : {', '.join(missing)}"))

    def _ensure_subscriptions(self):
        from apps.plans.models import Plan, Subscription

        created = 0
        for t in self._tenants():
            if Subscription.objects.filter(
                tenant=t, status__in=SubscriptionStatus.ACTIVE_STATUSES
            ).exists():
                continue

            plan = t.plan or Plan.objects.filter(slug=PlanSlug.STARTER, is_active=True).first()
            if not plan:
                self.stderr.write(self.style.ERROR(
                    f"  [{t.schema_name}] no plan on tenant and no Starter plan exists — "
                    f"run `setup_initial_data` first"
                ))
                continue

            status = (
                t.subscription_status
                if t.subscription_status in SubscriptionStatus.ACTIVE_STATUSES
                else SubscriptionStatus.TRIAL
            )
            self.stdout.write(f"  [{t.schema_name}] + Subscription({plan.slug}, {status})")
            if not self.dry:
                Subscription.objects.create(
                    tenant=t, plan=plan, status=status, trial_end=t.trial_ends_at
                )
                if not t.plan:
                    t.plan = plan
                    t.save(update_fields=["plan"])
            created += 1

        self._done(f"{created} subscription(s) created")

    def _grandfather(self):
        from apps.plans.models import TenantEntitlement

        enforced = discover_enforced_features()
        self.stdout.write(f"Enforced features discovered: {len(enforced)}")

        # Grandfathering exists to stop an existing tenant losing something they
        # already had when we switch a gate on. It must never *give* them
        # something they never bought — the add-on modules (HRMS, ERP, AI Suite)
        # are sold separately, and their endpoints are new, so no tenant can
        # have been relying on them. Sell them with --grant-module instead.
        addons = {k for m in ModuleKey.ALL for k in ModuleKey.FEATURES[m]}
        skipped = sorted(set(enforced) & addons)
        if skipped:
            self.stdout.write(
                f"Skipping {len(skipped)} paid add-on feature(s): {', '.join(skipped)}"
            )
        enforced = [k for k in enforced if k not in addons]

        granted = 0
        for t in self._tenants():
            features = self._effective(t)
            for key in enforced:
                if features.get(key):
                    continue  # plan already grants it
                self.stdout.write(f"  [{t.schema_name}] grant {key}")
                if not self.dry:
                    TenantEntitlement.objects.update_or_create(
                        tenant=t,
                        feature_key=key,
                        defaults={
                            "is_enabled": True,
                            "note": f"grandfathered {timezone.now():%Y-%m-%d}",
                        },
                    )
                granted += 1
            if not self.dry:
                TenantEntitlement._invalidate(t)

        self._done(f"{granted} entitlement(s) granted")

    def _mutate(self, o):
        from apps.plans.models import TenantEntitlement

        if not o["tenant"]:
            raise CommandError("--tenant=<schema> is required for grant/revoke.")
        tenant = self._tenants(o["tenant"]).first()

        if module := o["grant_module"]:
            if module not in ModuleKey.ALL:
                raise CommandError(f"Unknown module '{module}'. One of: {', '.join(ModuleKey.ALL)}")
            self.stdout.write(f"  grant module {module} → {', '.join(ModuleKey.FEATURES[module])}")
            if not self.dry:
                TenantEntitlement.grant_module(tenant, module, note="granted via CLI")

        if module := o["revoke_module"]:
            if module not in ModuleKey.ALL:
                raise CommandError(f"Unknown module '{module}'. One of: {', '.join(ModuleKey.ALL)}")
            self.stdout.write(f"  revoke module {module}")
            if not self.dry:
                TenantEntitlement.revoke_module(tenant, module)

        for key, enabled in ((o["grant"], True), (o["revoke"], False)):
            if not key:
                continue
            if key not in FeatureKey.ALL:
                raise CommandError(f"Unknown feature key '{key}'")
            self.stdout.write(f"  {'grant' if enabled else 'revoke'} {key}")
            if not self.dry:
                TenantEntitlement.objects.update_or_create(
                    tenant=tenant,
                    feature_key=key,
                    defaults={"is_enabled": enabled, "note": "set via CLI"},
                )
                TenantEntitlement._invalidate(tenant)

        self._done("entitlements updated")

    def _done(self, msg):
        suffix = " (dry-run, nothing written)" if self.dry else ""
        self.stdout.write(self.style.SUCCESS(f"\n✅ {msg}{suffix}"))
