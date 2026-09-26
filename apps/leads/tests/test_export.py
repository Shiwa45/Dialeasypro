"""
Exporting leads as CSV.

The CRM's Export button asks for what it wants — `Accept: text/csv` — and DRF
negotiates content BEFORE a view's own code runs. No renderer declared that
media type, so the request was refused with 406 and the export never reached
the code that writes the file. It failed for every tenant, every time, while
the same URL fetched by hand (no Accept header) returned the CSV happily,
which is why it survived being "fixed" twice.

The filters are the other half: the file has to match the screen it was
exported from, or the numbers an admin reports are not the ones they were
looking at.
"""
import pytest
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.core.constants import LeadSource, LeadStatus
from apps.leads.models import Lead
from apps.leads.views import LeadExportView

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(
        email="owner@example.com", name="Owner", password="Pw@12345678",
    )


@pytest.fixture
def leads():
    Lead.objects.create(name="Asha Rao", phone="+919812300001", city="Pune",
                        status=LeadStatus.NEW, source=LeadSource.CSV_IMPORT)
    Lead.objects.create(name="Bilal Khan", phone="+919812300002", city="Nashik",
                        status=LeadStatus.CONTACTED, source=LeadSource.INDIAMART)
    Lead.objects.create(name="Chitra Nair", phone="+919812300003", city="Pune",
                        status=LeadStatus.CONTACTED, source=LeadSource.CSV_IMPORT)


def _export(user, accept=None, **params):
    request = APIRequestFactory().get(
        "/api/v1/leads/export/", params, **({"HTTP_ACCEPT": accept} if accept else {}),
    )
    force_authenticate(request, user=user)
    # The view is plan-gated; middleware does not run on a factory request.
    request.has_feature = lambda key: True
    return LeadExportView.as_view()(request)


def _body(response):
    return b"".join(response.streaming_content).decode("utf-8")


# ---- It has to answer at all ------------------------------------------

def test_a_client_asking_for_csv_is_not_refused(admin, leads):
    """The bug: 406, before a single row was written."""
    response = _export(admin, accept="text/csv")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")


def test_a_browser_style_accept_header_works_too(admin, leads):
    response = _export(admin, accept="text/csv,application/json;q=0.9,*/*;q=0.8")

    assert response.status_code == 200


def test_no_accept_header_still_works(admin, leads):
    """This is the path that always worked, and must keep working."""
    assert _export(admin).status_code == 200


def test_it_is_sent_as_a_download(admin, leads):
    response = _export(admin, accept="text/csv")

    assert "attachment" in response["Content-Disposition"]
    assert ".csv" in response["Content-Disposition"]


# ---- And say what is on the screen ------------------------------------

def test_every_lead_when_nothing_is_filtered(admin, leads):
    body = _body(_export(admin, accept="text/csv"))

    for name in ("Asha Rao", "Bilal Khan", "Chitra Nair"):
        assert name in body


def test_the_status_filter_is_applied(admin, leads):
    body = _body(_export(admin, accept="text/csv", status=LeadStatus.CONTACTED))

    assert "Bilal Khan" in body
    assert "Asha Rao" not in body


def test_the_source_filter_is_applied(admin, leads):
    """
    Source was ignored by the export while the list filtered on it, so
    narrowing to one source and pressing Export produced every lead.
    """
    body = _body(_export(admin, accept="text/csv", source=LeadSource.INDIAMART))

    assert "Bilal Khan" in body
    assert "Chitra Nair" not in body


def test_the_search_box_is_applied(admin, leads):
    body = _body(_export(admin, accept="text/csv", search="Chitra"))

    assert "Chitra Nair" in body
    assert "Asha Rao" not in body


def test_filters_combine_the_way_the_list_combines_them(admin, leads):
    body = _body(_export(admin, accept="text/csv",
                         status=LeadStatus.CONTACTED, city="Pune"))

    assert "Chitra Nair" in body
    assert "Bilal Khan" not in body, "contacted, but not in Pune"


def test_the_header_row_names_the_columns(admin, leads):
    first_line = _body(_export(admin, accept="text/csv")).splitlines()[0]

    assert first_line.startswith("Name,Phone")


# ---- What the renderer does with an error -----------------------------

def test_an_error_under_accept_csv_is_still_readable(admin):
    """
    DRF renders a refusal with whatever renderer was negotiated. A dict cast
    to CSV would be unreadable; the client reads the body as text and parses
    it, so it goes out as JSON.
    """
    from apps.core.renderers import CSVRenderer

    rendered = CSVRenderer().render({"message": "Plan limit reached"})

    assert "Plan limit reached" in rendered
    assert JSONRenderer in LeadExportView.renderer_classes, "JSON stays the default"
