"""
TeleCRM Backend — apps/core/middleware.py

Custom middleware for TeleCRM:

1. TenantSchemaFromTokenMiddleware
   - Reads the JWT Bearer token and corrects the DB schema for API requests.
   - Runs BEFORE TenantFeatureFlagMiddleware so feature-flag checks use the
     right schema even when subdomain routing cannot resolve the tenant domain
     (e.g. demo.localhost in development, or a misconfigured domain entry).

2. TenantFeatureFlagMiddleware
   - Loads the current tenant's plan features into request
   - Caches feature flags in Redis to avoid DB hit on every request
   - Used in templates via {{ request.tenant_features }}
   - Used in views via request.has_feature(FeatureKey.BULK_WHATSAPP)

3. RequestTimingMiddleware
   - Logs slow requests (> 2 seconds)
   - Adds X-Response-Time header in debug mode

4. MaintenanceModeMiddleware
   - Returns 503 if MAINTENANCE_MODE=True in settings
"""
import base64
import json
import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.utils.functional import SimpleLazyObject

from apps.core.constants import CacheTimeout, SubscriptionStatus

logger = logging.getLogger(__name__)


class TenantSchemaFromTokenMiddleware(MiddlewareMixin):
    """
    Corrects the active PostgreSQL schema for API requests by reading the
    tenant_schema claim from the JWT Bearer token.

    Why: TenantMainMiddleware sets the schema by looking up the request hostname
    in the Domain table.  In development the frontend hits demo.localhost:8000
    but the Domain table only has demo.telecrm.in, so the lookup fails and the
    connection defaults to the public schema.  Every subsequent check
    (TenantFeatureFlagMiddleware, AgentJWTAuthentication) then runs against the
    wrong schema, producing cascading 401 / 403 errors even for admin users.

    Fix: Before any per-tenant middleware runs, peek at the JWT payload
    (no signature verification needed here — AgentJWTAuthentication does the
    full verification) and switch the connection to the schema stated in the
    token.  Also accepts X-Tenant-Schema header as a fallback for requests
    that arrive before a token is available (e.g. the initial token-refresh
    call after a cold page load).

    Security: Switching schema based on an unverified claim is safe because:
      - AgentJWTAuthentication verifies signature + expiry and confirms the
        agent exists in that schema — a forged token is rejected at that layer.
      - The public schema is never targeted via this path.
    """

    def process_request(self, request):
        if not request.path.startswith('/api/'):
            return None

        schema_name = (
            self._schema_from_bearer(request)
            or self._schema_from_header(request)
        )

        if not schema_name or schema_name == 'public':
            return None

        if connection.schema_name == schema_name:
            # Schema is already correct; make sure URL routing also uses
            # the tenant conf (could be public if TenantMainMiddleware set it).
            self._ensure_tenant_urlconf(request)
            return None

        try:
            connection.set_schema(schema_name)
            # Keep request.tenant in sync so TenantFeatureFlagMiddleware
            # loads features for the correct tenant.
            self._sync_request_tenant(request, schema_name)
            # Critical: switch URL routing away from the public conf so that
            # tenant API endpoints (e.g. /api/v1/auth/login/) are reachable.
            self._ensure_tenant_urlconf(request)
        except Exception as exc:
            logger.warning(
                f"[TenantSchemaFromToken] Could not switch to schema "
                f"'{schema_name}': {exc}"
            )

        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _schema_from_bearer(request) -> str | None:
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return None
        token_string = auth_header[7:].strip()
        return TenantSchemaFromTokenMiddleware._decode_jwt_schema(token_string)

    @staticmethod
    def _schema_from_header(request) -> str | None:
        """
        Reads X-Tenant-Schema or X-Workspace-ID headers to determine the schema.
        This is critical for mobile apps hitting IP addresses directly.
        """
        schema = request.META.get('HTTP_X_TENANT_SCHEMA', '').strip()
        if schema and schema != 'public':
            try:
                from apps.tenants.models import Domain
                if Domain.objects.filter(tenant__schema_name=schema).exists():
                    return schema
            except Exception:
                pass
                
        workspace = request.META.get('HTTP_X_WORKSPACE_ID', '').strip()
        if workspace:
            try:
                from apps.tenants.models import Domain, Tenant
                # 1. Try subdomain prefix: "demo" → matches "demo.localhost"
                domain_obj = Domain.objects.filter(
                    domain__startswith=f"{workspace}."
                ).exclude(tenant__schema_name='public').select_related('tenant').first()
                if domain_obj:
                    return domain_obj.tenant.schema_name
                # 2. Try exact schema name: "demo_corp" → matches schema directly
                if Tenant.objects.filter(schema_name=workspace).exclude(schema_name='public').exists():
                    return workspace
            except Exception:
                pass

        return None

    @staticmethod
    def _decode_jwt_schema(token_string: str) -> str | None:
        """
        Extracts the tenant_schema claim from a JWT without verifying the
        signature or checking expiry.  Full verification is AgentJWTAuthentication's
        responsibility.
        """
        try:
            parts = token_string.split('.')
            if len(parts) != 3:
                return None
            payload_b64 = parts[1]
            # JWT uses URL-safe base64 without padding; add padding back.
            payload_b64 += '=' * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            schema = payload.get('tenant_schema', '')
            return schema if schema and schema != 'public' else None
        except Exception:
            return None

    @staticmethod
    def _sync_request_tenant(request, schema_name: str):
        """Updates request.tenant to match the corrected schema."""
        try:
            from apps.tenants.models import Tenant
            tenant = Tenant.objects.get(schema_name=schema_name)
            request.tenant = tenant
        except Exception:
            pass

    @staticmethod
    def _ensure_tenant_urlconf(request):
        """
        Switches URL routing from the public schema conf to the tenant conf.

        When TenantMainMiddleware resolves a request to the public tenant
        (e.g. because the Host header is 'localhost' or an Android emulator IP),
        it sets request.urlconf = PUBLIC_SCHEMA_URLCONF.  That conf has no
        /api/v1/auth/ etc., so those endpoints return 404.  After we correct
        the DB schema we must also correct the URL routing.
        """
        from django.conf import settings
        from django.urls import set_urlconf

        public_urlconf = getattr(settings, 'PUBLIC_SCHEMA_URLCONF', None)
        current = getattr(request, 'urlconf', None)
        if current == public_urlconf or current is None:
            request.urlconf = settings.ROOT_URLCONF
            set_urlconf(settings.ROOT_URLCONF)


class TenantFeatureFlagMiddleware(MiddlewareMixin):
    """
    Injects tenant plan features into every request.

    After this middleware runs, request has:
      - request.tenant_features: dict {feature_key: bool}
      - request.has_feature(key): helper method
      - request.tenant_plan: Plan instance (or None for public schema)
    """

    def process_request(self, request):
        # Skip for public schema (super admin)
        if not hasattr(request, "tenant"):
            request.tenant_features = {}
            request.tenant_plan = None
            return None

        tenant = request.tenant
        if tenant.schema_name == "public":
            request.tenant_features = {}
            request.tenant_plan = None
            # Inject helper method that always returns True for super admin
            request.has_feature = lambda key: True
            return None

        # Load features from cache or DB
        features = self._get_tenant_features(tenant)
        request.tenant_features = features

        # Resolve the plan lazily: `_cached_plan` is only populated on a cache
        # MISS, so reading it directly left tenant_plan None on nearly every
        # request. SimpleLazyObject costs nothing unless something reads it.
        # NOTE: it is never `is None` — test it for truthiness instead.
        request.tenant_plan = SimpleLazyObject(lambda: self._get_tenant_plan(tenant))

        # Inject helper method
        def has_feature(feature_key):
            return bool(features.get(feature_key, False))

        request.has_feature = has_feature

        # Check if tenant is active (not suspended/cancelled)
        if not self._is_tenant_active(tenant):
            # For API requests, return JSON error
            if request.path.startswith("/api/"):
                return JsonResponse(
                    {
                        "error": "account_suspended",
                        "message": "Your account is suspended. Please contact support.",
                    },
                    status=403,
                )
            # For web requests, redirect to suspended page
            # (let views handle this; just set a flag)
            request.tenant_suspended = True

        return None

    def _get_tenant_features(self, tenant) -> dict:
        """
        Load feature flags from Redis cache, falling back to DB.
        Cache key is per-tenant to ensure isolation.
        """
        cache_key = f"tenant_features:{tenant.schema_name}"
        cached = cache.get(cache_key)

        if cached is not None:
            return cached

        # Load from DB
        features = self._load_features_from_db(tenant)
        cache.set(cache_key, features, timeout=CacheTimeout.FEATURE_FLAGS)
        return features

    def _get_tenant_plan(self, tenant):
        """Resolve the tenant's active Plan (id cached; 0 means 'no plan')."""
        cache_key = f"tenant_plan_id:{tenant.schema_name}"
        plan_id = cache.get(cache_key)

        if plan_id is None:
            from apps.plans.models import Subscription
            subscription = (
                Subscription.objects.filter(
                    tenant=tenant, status__in=SubscriptionStatus.ACTIVE_STATUSES
                )
                .select_related("plan")
                .first()
            )
            plan = subscription.plan if subscription else None
            cache.set(cache_key, plan.pk if plan else 0, timeout=CacheTimeout.FEATURE_FLAGS)
            return plan

        if not plan_id:
            return None

        from apps.plans.models import Plan
        return Plan.objects.filter(pk=plan_id).first()

    def _load_features_from_db(self, tenant) -> dict:
        """
        Resolve the tenant's EFFECTIVE feature map from the public schema:

            plan's PlanFeature set, then TenantEntitlement applied over it

        Entitlements are how add-on modules (HRMS/ERP/AI) are sold independently
        of the plan tier. A grant adds a feature; is_enabled=False explicitly
        revokes one the plan would otherwise allow. Expired rows are ignored.
        A tenant with no subscription can still hold entitlements.
        """
        from django.db.models import Q
        from django.utils import timezone

        features: dict = {}
        try:
            from apps.plans.models import PlanFeature, Subscription, TenantEntitlement

            subscription = (
                Subscription.objects.filter(
                    tenant=tenant,
                    status__in=SubscriptionStatus.ACTIVE_STATUSES,
                )
                .select_related("plan")
                .first()
            )

            if subscription:
                # Cache plan reference on tenant object
                tenant._cached_plan = subscription.plan
                features = {
                    pf["feature_key"]: pf["is_enabled"]
                    for pf in PlanFeature.objects.filter(
                        plan=subscription.plan
                    ).values("feature_key", "is_enabled")
                }

            # Layer per-tenant entitlements (add-ons / bespoke grants) on top.
            now = timezone.now()
            entitlements = TenantEntitlement.objects.filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now),
                tenant=tenant,
            ).values("feature_key", "is_enabled")
            for ent in entitlements:
                features[ent["feature_key"]] = ent["is_enabled"]

            return features

        except Exception as exc:
            logger.warning(
                f"Failed to load features for tenant {tenant.schema_name}: {exc}"
            )
            return features

    def _is_tenant_active(self, tenant) -> bool:
        """
        Check if tenant's subscription allows platform access.

        Uses the denormalized subscription_status field on the Tenant model as
        the primary signal — this is always set by set_trial() / activate() /
        suspend(), including for tenants whose Subscription row hasn't been
        created yet (e.g. when create_tenant ran before setup_initial_data).
        Falls back to querying the Subscription table only when the tenant
        status itself indicates the account is not in an active state.
        """
        cache_key = f"tenant_active:{tenant.schema_name}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # Fast path: trust the denormalized status kept in sync by
        # the sync_subscription_to_tenant signal and the tenant lifecycle methods.
        if tenant.subscription_status in SubscriptionStatus.ACTIVE_STATUSES:
            cache.set(cache_key, True, timeout=60)
            return True

        # Slow path: status says inactive — double-check the Subscription table
        # in case the denormalized field is stale (e.g. direct DB edits).
        from apps.plans.models import Subscription
        is_active = Subscription.objects.filter(
            tenant=tenant,
            status__in=SubscriptionStatus.ACTIVE_STATUSES,
        ).exists()

        cache.set(cache_key, is_active, timeout=60)
        return is_active

    @staticmethod
    def invalidate_cache(schema_name: str):
        """
        Call this when a tenant's plan, entitlements or status change.
        Clears the cached feature map for immediate effect.
        """
        cache.delete(f"tenant_features:{schema_name}")
        cache.delete(f"tenant_active:{schema_name}")
        cache.delete(f"tenant_plan_id:{schema_name}")


class RequestTimingMiddleware(MiddlewareMixin):
    """
    Measures request processing time.
    - Logs requests that take > SLOW_REQUEST_THRESHOLD seconds
    - Adds X-Response-Time header in DEBUG mode
    """

    SLOW_REQUEST_THRESHOLD = 2.0  # seconds

    def process_request(self, request):
        request._start_time = time.monotonic()

    def process_response(self, request, response):
        if not hasattr(request, "_start_time"):
            return response

        elapsed = time.monotonic() - request._start_time
        elapsed_ms = int(elapsed * 1000)

        # Add timing header in debug mode
        if settings.DEBUG:
            response["X-Response-Time"] = f"{elapsed_ms}ms"

        # Log slow requests
        if elapsed > self.SLOW_REQUEST_THRESHOLD:
            tenant_schema = getattr(
                getattr(request, "tenant", None), "schema_name", "public"
            )
            logger.warning(
                f"[SlowRequest] {request.method} {request.path} "
                f"took {elapsed_ms}ms | tenant={tenant_schema}"
            )

        return response


class MaintenanceModeMiddleware(MiddlewareMixin):
    """
    Returns a 503 Service Unavailable response when MAINTENANCE_MODE is True.
    Exempts the super admin panel and health check endpoint.
    """

    EXEMPT_PATHS = [
        f"/{settings.ADMIN_URL}",
        "/health/",
        "/api/v1/health/",
    ]

    def process_request(self, request):
        if not getattr(settings, "MAINTENANCE_MODE", False):
            return None

        # Don't block admin or health check
        for path in self.EXEMPT_PATHS:
            if request.path.startswith(path):
                return None

        # API requests → JSON
        if request.path.startswith("/api/"):
            return JsonResponse(
                {
                    "error": "maintenance",
                    "message": (
                        "TeleCRM is currently under scheduled maintenance. "
                        "We'll be back shortly!"
                    ),
                },
                status=503,
            )

        # Web requests → HTML maintenance page
        return HttpResponse(
            """
            <!DOCTYPE html>
            <html>
            <head><title>TeleCRM — Maintenance</title></head>
            <body style="font-family:sans-serif;text-align:center;padding:100px">
                <h1>🔧 Under Maintenance</h1>
                <p>TeleCRM is undergoing scheduled maintenance. We'll be back soon!</p>
            </body>
            </html>
            """,
            status=503,
        )
