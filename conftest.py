"""
TeleCRM Backend — conftest.py

Shared pytest fixtures.

This is a django-tenants project: every CRM table (leads, communications,
integrations, ...) lives in a TENANT schema, and the `public` schema pytest
migrates by default has none of them. So the suite creates one real tenant
schema once per session and runs each test inside it — the same way a request
runs, with `connection.schema_name` pointing at a tenant.
"""
import pytest
from django.db import connection

TEST_SCHEMA = "test_tenant"
TEST_DOMAIN = "testtenant.localhost"


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """
    Create the tenant schema once, after pytest-django has built the test DB.

    Saving a Tenant with auto_create_schema=True runs every TENANT_APPS
    migration into the new schema, which is slow — hence session scope. The
    post_schema_sync signal that normally seeds a tenant admin and subscription
    is allowed to run: tests should exercise the same schema a real tenant has.
    """
    with django_db_blocker.unblock():
        from apps.tenants.models import Domain, Tenant

        tenant = Tenant.objects.filter(schema_name=TEST_SCHEMA).first()
        if tenant is None:
            tenant = Tenant(
                schema_name=TEST_SCHEMA,
                company_name="Test Realty",
                primary_contact_name="Test Admin",
                primary_contact_email="admin@testrealty.test",
                primary_contact_phone="+919876543210",
            )
            tenant.save()
            Domain.objects.get_or_create(
                domain=TEST_DOMAIN, tenant=tenant, defaults={"is_primary": True},
            )


@pytest.fixture(autouse=True)
def tenant_schema(request):
    """
    Point every DB-using test at the tenant schema.

    Autouse and cheap: it only issues a `SET search_path` for tests that
    actually touch the database, and restores the previous schema afterwards so
    a test cannot leak its search_path into the next one.
    """
    if "django_db" not in request.keywords and "db" not in request.fixturenames:
        yield
        return

    previous = connection.schema_name
    connection.set_schema(TEST_SCHEMA)
    try:
        yield TEST_SCHEMA
    finally:
        connection.set_schema(previous)


@pytest.fixture
def client(client):
    """
    The test client, addressed to the tenant's own domain.

    django-tenants routes on the Host header: without it the request lands on
    the PUBLIC urlconf, where none of the tenant API routes exist and every
    call 404s. Real traffic always carries the tenant subdomain, so the tests
    do too.
    """
    client.defaults["HTTP_HOST"] = TEST_DOMAIN
    return client
