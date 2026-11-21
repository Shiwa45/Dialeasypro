"""
The super admin sidebar is a hand-written list (UNFOLD["SIDEBAR"], with
show_all_applications off), so a screen registered in the admin but left
out of it can only be reached by typing its URL. Tenant Entitlements — how
add-on modules are sold — was missing this way.

Every admin screen for a shared-schema model must be in the sidebar.
Tenant-schema models are deliberately left out: on the platform's own
(public) domain they only say "Not available for global schema".
"""
import pytest
from django.conf import settings
from django.contrib import admin
from django.urls import reverse, set_urlconf


@pytest.fixture(autouse=True)
def platform_urls():
    """The admin lives on the platform's (public) URLconf."""
    set_urlconf(settings.PUBLIC_SCHEMA_URLCONF)
    yield
    set_urlconf(None)


def _sidebar_links() -> set[str]:
    links = set()
    for group in settings.UNFOLD["SIDEBAR"]["navigation"]:
        for item in group.get("items", []):
            links.add(str(item["link"]))
    return links


def _shared(model) -> bool:
    return model._meta.app_config.name in settings.SHARED_APPS


def test_every_platform_screen_is_in_the_sidebar():
    links = _sidebar_links()
    missing = [
        f"{m._meta.app_label}.{m._meta.model_name}"
        for m in admin.site._registry
        if _shared(m)
        and reverse(f"admin:{m._meta.app_label}_{m._meta.model_name}_changelist") not in links
    ]
    assert not missing, f"Add these to UNFOLD['SIDEBAR']: {sorted(missing)}"


def test_the_sidebar_has_no_tenant_only_screens():
    tenant_only = {
        reverse(f"admin:{m._meta.app_label}_{m._meta.model_name}_changelist")
        for m in admin.site._registry
        if not _shared(m)
    }
    assert not (_sidebar_links() & tenant_only)
