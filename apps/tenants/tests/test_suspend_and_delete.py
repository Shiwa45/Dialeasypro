"""
Suspending and deleting a tenant from the super admin panel.

  * A tenant suspended from the panel kept working: its admin signed in and
    every screen ran. Unticking "Is active" (or setting the status to
    Suspended) changed that one field; the middleware then trusted a 60 s
    cache and the subscription row, which still said "active".
  * Re-saving a suspended tenant's plan re-saved its active subscription,
    whose signal flipped the tenant back to "active".
  * Deleting a tenant left its PostgreSQL schema — all its data — behind.
"""
from datetime import timedelta

import pytest
from django.contrib import admin
from django.db import connection
from django.test import RequestFactory
from django.utils import timezone

from apps.core.constants import SubscriptionStatus
from apps.core.middleware import TenantFeatureFlagMiddleware
from apps.plans.models import Subscription
from apps.tenants.admin import TenantAdmin
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    t = Tenant.objects.get(schema_name=connection.schema_name)
    t.activate()
    return t


def _api(tenant, path="/api/v1/leads/"):
    req = RequestFactory().get(path)
    req.tenant = Tenant.objects.get(pk=tenant.pk)  # fresh, as django-tenants loads it
    return TenantFeatureFlagMiddleware(lambda r: None).process_request(req)


def _blocked(tenant, path="/api/v1/leads/"):
    resp = _api(tenant, path)
    return resp is not None and resp.status_code == 403 and b"plan_expired" in resp.content


def test_an_active_tenant_works(tenant):
    assert _api(tenant) is None


def test_the_suspend_action_blocks_every_api_call_including_sign_in(tenant):
    assert _api(tenant) is None  # warms any cache, as a live tenant would
    tenant.suspend(reason="test")
    assert _blocked(tenant)
    assert _blocked(tenant, "/api/v1/auth/login/")
    assert _blocked(tenant, "/api/v1/auth/refresh/")
    assert not Subscription.objects.filter(
        tenant=tenant, status__in=SubscriptionStatus.ACTIVE_STATUSES).exists()
    tenant.activate()
    assert _api(tenant) is None


def _form_save(tenant, **changes):
    request = RequestFactory().post("/superadmin/")
    request.user = type("U", (), {"email": "boss@platform.test"})()
    obj = Tenant.objects.get(pk=tenant.pk)
    for k, v in changes.items():
        setattr(obj, k, v)
    TenantAdmin(Tenant, admin.site).save_model(request, obj, form=None, change=True)
    return Tenant.objects.get(pk=tenant.pk)


def test_unticking_is_active_on_the_form_suspends(tenant):
    t = _form_save(tenant, is_active=False)
    assert t.subscription_status == SubscriptionStatus.SUSPENDED
    assert t.suspension_kind == Tenant.SUSPENDED_ADMIN
    assert _blocked(t)


def test_setting_the_status_to_suspended_on_the_form_suspends(tenant):
    t = _form_save(tenant, subscription_status=SubscriptionStatus.SUSPENDED)
    assert t.is_active is False and _blocked(t)


def test_saving_a_suspended_tenants_plan_does_not_reactivate_it(tenant):
    from apps.plans.models import Plan

    tenant.suspend(reason="abuse")
    other = Plan.objects.exclude(pk=tenant.plan_id).first() or tenant.plan
    t = _form_save(tenant, plan=other)
    assert t.is_active is False and t.subscription_status == SubscriptionStatus.SUSPENDED
    assert _blocked(t)


def test_switching_back_on_from_the_form_reopens(tenant):
    tenant.suspend(reason="x")
    t = _form_save(tenant, is_active=True, subscription_status=SubscriptionStatus.ACTIVE)
    assert t.suspension_kind == "" and _api(t) is None
    assert not Subscription.objects.filter(tenant=t, status=SubscriptionStatus.SUSPENDED).exists()


def test_an_expired_trial_is_blocked_before_the_nightly_job(tenant):
    Tenant.objects.filter(pk=tenant.pk).update(
        subscription_status=SubscriptionStatus.TRIAL,
        trial_ends_at=timezone.now() - timedelta(hours=1),
    )
    assert _blocked(tenant)


def test_the_health_check_stays_open(tenant):
    tenant.suspend(reason="x")
    assert _api(tenant, "/api/v1/health/") is None


# ---- Delete ----------------------------------------------------

def _schema_exists(name):
    with connection.cursor() as cur:
        cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", [name])
        return cur.fetchone() is not None


@pytest.fixture
def public():
    previous = connection.schema_name
    connection.set_schema_to_public()
    yield
    connection.set_schema(previous)


def _throwaway(name):
    t = Tenant(schema_name=name, company_name=name, primary_contact_name="X",
               primary_contact_email=f"{name}@x.test", primary_contact_phone="+919876543210")
    t.auto_create_schema = False  # an empty schema is enough to prove the drop
    t.save()
    with connection.cursor() as cur:
        cur.execute(f'CREATE SCHEMA "{name}"')
    return t


def test_deleting_a_tenant_drops_its_schema(public):
    t = _throwaway("qa_delete_one")
    assert _schema_exists("qa_delete_one")
    request = RequestFactory().post("/superadmin/")
    TenantAdmin(Tenant, admin.site).delete_model(request, t)
    assert not Tenant.objects.filter(schema_name="qa_delete_one").exists()
    assert not _schema_exists("qa_delete_one")


def test_bulk_delete_drops_every_schema(public):
    _throwaway("qa_delete_a")
    _throwaway("qa_delete_b")
    request = RequestFactory().post("/superadmin/")
    TenantAdmin(Tenant, admin.site).delete_queryset(
        request, Tenant.objects.filter(schema_name__in=["qa_delete_a", "qa_delete_b"]))
    assert not _schema_exists("qa_delete_a") and not _schema_exists("qa_delete_b")


def test_the_public_schema_is_never_deleted(public):
    with pytest.raises(ValueError):
        Tenant(schema_name="public").delete()
