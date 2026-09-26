"""
Rows an import used to lose without saying so.

MED-2: with "update duplicates", a new number appearing twice in one file sent
the second row looking for a saved lead that is not created until the end of
the run. It found none, and the row was counted as processed but as neither
success, duplicate nor failure — its data gone, unreported.

MED-3: only plain numbers parsed as a budget. "1.2 Cr", "50L" and "20 lakh" —
how real-estate sheets write budgets — became an empty budget, no error.
"""
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection

from apps.core.constants import LeadSource
from apps.core.utils import parse_indian_amount
from apps.leads.models import Lead, LeadImportJob
from apps.leads.tasks import process_lead_import

pytestmark = pytest.mark.django_db


def _import(csv_text, **kwargs):
    job = LeadImportJob.objects.create(
        file=SimpleUploadedFile("leads.csv", csv_text.encode()),
        original_filename="leads.csv",
        column_mapping={"name": "name", "phone": "phone", "city": "city",
                        "email": "email", "budget": "budget"},
        default_source=LeadSource.CSV_IMPORT,
        **kwargs,
    )
    process_lead_import(connection.schema_name, str(job.id))
    job.refresh_from_db()
    return job


# ---- MED-2 --------------------------------------------------------------

def test_a_repeated_new_number_is_merged_not_lost():
    job = _import(
        "name,phone,city,email,budget\n"
        "Asha,9876500001,Pune,,\n"
        "Asha,9876500001,,asha@example.com,\n",
        duplicate_action="update",
    )

    leads = Lead.objects.filter(phone="+919876500001")
    assert leads.count() == 1
    lead = leads.get()
    assert lead.city == "Pune"
    assert lead.email == "asha@example.com", "the second row's data was dropped"
    assert job.duplicate_rows == 1


def test_the_first_value_wins_when_both_rows_have_one():
    _import(
        "name,phone,city,email,budget\n"
        "Asha,9876500002,Pune,,\n"
        "Asha,9876500002,Mumbai,,\n",
        duplicate_action="update",
    )

    assert Lead.objects.get(phone="+919876500002").city == "Pune"


def test_skip_mode_still_skips_the_repeat():
    job = _import(
        "name,phone,city,email,budget\n"
        "Asha,9876500003,Pune,,\n"
        "Asha,9876500003,,asha@example.com,\n",
        duplicate_action="skip",
    )

    assert Lead.objects.filter(phone="+919876500003").count() == 1
    assert job.duplicate_rows == 1


# ---- MED-3 --------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("1.2 Cr", 12_000_000), ("1.2cr", 12_000_000), ("2 crore", 20_000_000),
    ("50L", 5_000_000), ("50 lakh", 5_000_000), ("20 Lakhs", 2_000_000), ("7.5 lac", 750_000),
    ("₹ 45,00,000", 4_500_000), ("Rs. 25000", 25_000), ("80k", 80_000), ("500000", 500_000),
])
def test_indian_amounts_parse(text, expected):
    assert parse_indian_amount(text) == Decimal(expected)


@pytest.mark.parametrize("text", ["", "   ", None])
def test_a_blank_budget_is_just_blank(text):
    assert parse_indian_amount(text) is None


@pytest.mark.parametrize("text", ["negotiable", "50L-1Cr", "1.2 million", "abc"])
def test_unreadable_amounts_are_refused(text):
    with pytest.raises(ValueError):
        parse_indian_amount(text)


def test_import_reads_lakh_and_crore_budgets():
    _import(
        "name,phone,city,email,budget\n"
        "Asha,9876500010,Pune,,1.2 Cr\n"
        "Bala,9876500011,Pune,,50L\n",
    )

    assert Lead.objects.get(phone="+919876500010").budget == Decimal("12000000")
    assert Lead.objects.get(phone="+919876500011").budget == Decimal("5000000")


def test_an_unreadable_budget_is_reported_and_the_lead_still_imported():
    job = _import(
        "name,phone,city,email,budget\n"
        "Asha,9876500012,Pune,,negotiable\n",
    )

    assert Lead.objects.get(phone="+919876500012").budget is None
    assert any("negotiable" in e["error"] for e in job.row_errors)
    assert job.successful_rows == 1
