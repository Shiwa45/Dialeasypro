"""
TeleCRM Backend — apps/leads/tests/test_import_custom_fields.py

The import preview offers a tenant's custom fields as mapping targets
("custom_<field_key>"), so a spreadsheet column can be pointed at one. These
tests hold the other half of that contract: what the mapping UI accepts, the
importer must actually store.

Before the fix, `process_lead_import` read a fixed set of standard keys off the
mapped row and dropped everything else, so a mapped custom column — and the
"Notes / Remarks" target beside it — was accepted and silently discarded. The
lead detail screen then showed the field labels with no values.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.leads.models import (
    CustomField, CustomFieldValue, Lead, LeadActivity, LeadImportJob,
)
from apps.leads.tasks import _extract_custom_values, process_lead_import


def _csv(rows: str) -> SimpleUploadedFile:
    return SimpleUploadedFile("leads.csv", rows.encode("utf-8"), content_type="text/csv")


def _run_import(csv_text: str, mapping: dict, **job_kwargs) -> LeadImportJob:
    """Create a job from an in-memory CSV and run the importer synchronously."""
    job = LeadImportJob.objects.create(
        file=_csv(csv_text),
        original_filename="leads.csv",
        column_mapping=mapping,
        total_rows=csv_text.strip().count("\n"),
        **job_kwargs,
    )
    process_lead_import(TEST_SCHEMA, str(job.pk))
    job.refresh_from_db()
    return job


TEST_SCHEMA = "test_tenant"


@pytest.fixture
def property_type():
    return CustomField.objects.create(
        name="Property Type", field_key="property_type", field_type="text",
    )


@pytest.fixture
def budget_range():
    return CustomField.objects.create(
        name="Budget Range", field_key="budget_range", field_type="text",
    )


# ============================================================
# The reported bug
# ============================================================

@pytest.mark.django_db
def test_mapped_custom_field_is_stored(property_type):
    """A column mapped to a custom field must end up on the lead."""
    _run_import(
        "Name,Mobile,Type\nRahul Sharma,9876543210,3BHK Apartment\n",
        {"name": "Name", "phone": "Mobile", "custom_property_type": "Type"},
    )

    lead = Lead.objects.get(phone="+919876543210")
    value = CustomFieldValue.objects.get(lead=lead, field=property_type)
    assert value.value == "3BHK Apartment"


@pytest.mark.django_db
def test_several_custom_fields_on_one_row(property_type, budget_range):
    _run_import(
        "Name,Mobile,Type,Budget\nPriya Nair,9876500011,Villa,50-60L\n",
        {
            "name": "Name", "phone": "Mobile",
            "custom_property_type": "Type", "custom_budget_range": "Budget",
        },
    )

    lead = Lead.objects.get(phone="+919876500011")
    stored = {v.field.field_key: v.value for v in lead.custom_field_values.all()}
    assert stored == {"property_type": "Villa", "budget_range": "50-60L"}


@pytest.mark.django_db
def test_lead_detail_serializer_returns_the_imported_values(property_type):
    """
    The value has to survive all the way to the payload the lead detail screen
    reads — that is where it was visibly missing.
    """
    from apps.leads.serializers import LeadDetailSerializer

    _run_import(
        "Name,Mobile,Type\nAmit Verma,9876500022,Plot\n",
        {"name": "Name", "phone": "Mobile", "custom_property_type": "Type"},
    )
    lead = Lead.objects.get(phone="+919876500022")

    values = LeadDetailSerializer(lead).data["custom_field_values"]
    assert len(values) == 1
    assert values[0]["field_key"] == "property_type"
    assert values[0]["value"] == "Plot"
    # The frontend matches on field_key first, then falls back to the field id.
    assert values[0]["field"] == property_type.pk


# ============================================================
# The two silent drops sitting beside it
# ============================================================

@pytest.mark.django_db
def test_mapped_notes_column_becomes_a_lead_note():
    """"Notes / Remarks" is offered by the same picker and was also dropped."""
    _run_import(
        # The remarks cell is quoted because it contains a comma — otherwise CSV
        # splits it and the assertion below is testing the parser, not the fix.
        'Name,Mobile,Remarks\nSunita Rao,9876500033,"Called twice, wants a callback"\n',
        {"name": "Name", "phone": "Mobile", "notes": "Remarks"},
    )

    lead = Lead.objects.get(phone="+919876500033")
    assert lead.notes.count() == 1
    assert "callback" in lead.notes.first().content


@pytest.mark.django_db
def test_import_writes_an_activity_row():
    """
    bulk_create(ignore_conflicts=True) leaves pk=None even on PostgreSQL, so the
    old `if lead.pk` guard filtered out every activity. The importer now re-reads
    the saved rows, which is also what gives custom values something to attach to.
    """
    _run_import("Name,Mobile\nVikram Singh,9876500044\n", {"name": "Name", "phone": "Mobile"})

    lead = Lead.objects.get(phone="+919876500044")
    assert LeadActivity.objects.filter(lead=lead, activity_type="imported").exists()


# ============================================================
# Rules that must not regress
# ============================================================

@pytest.mark.django_db
def test_blank_cells_do_not_create_empty_values(property_type):
    """An empty cell means "no answer", not an empty custom value."""
    _run_import(
        "Name,Mobile,Type\nNeha Gupta,9876500055,   \n",
        {"name": "Name", "phone": "Mobile", "custom_property_type": "Type"},
    )

    lead = Lead.objects.get(phone="+919876500055")
    assert not lead.custom_field_values.exists()


@pytest.mark.django_db
def test_mapping_to_a_deleted_field_is_ignored_not_fatal(property_type):
    """
    A field can be removed between choosing the mapping and running the import.
    That row must still import — losing 500 leads over one stale column would be
    far worse than losing the column.
    """
    property_type.delete()

    _run_import(
        "Name,Mobile,Type\nRohit Mehra,9876500066,Duplex\n",
        {"name": "Name", "phone": "Mobile", "custom_property_type": "Type"},
    )

    assert Lead.objects.filter(phone="+919876500066").exists()


@pytest.mark.django_db
def test_inactive_field_is_not_written(property_type):
    property_type.is_active = False
    property_type.save(update_fields=["is_active"])

    _run_import(
        "Name,Mobile,Type\nKavya Iyer,9876500077,Studio\n",
        {"name": "Name", "phone": "Mobile", "custom_property_type": "Type"},
    )

    lead = Lead.objects.get(phone="+919876500077")
    assert not lead.custom_field_values.exists()


@pytest.mark.django_db
def test_duplicate_update_fills_a_blank_custom_field(property_type):
    """Update mode should complete a lead that is missing the value."""
    lead = Lead.objects.create(name="Existing", phone="+919876500088")

    _run_import(
        "Name,Mobile,Type\nExisting,9876500088,Penthouse\n",
        {"name": "Name", "phone": "Mobile", "custom_property_type": "Type"},
        duplicate_action="update",
    )

    assert CustomFieldValue.objects.get(lead=lead, field=property_type).value == "Penthouse"


@pytest.mark.django_db
def test_duplicate_update_never_overwrites_an_entered_value(property_type):
    """
    A value someone typed into the CRM outranks a spreadsheet cell — the same
    fill-a-blank rule the standard columns already follow.
    """
    lead = Lead.objects.create(name="Existing", phone="+919876500099")
    CustomFieldValue.objects.create(lead=lead, field=property_type, value="Verified: Villa")

    _run_import(
        "Name,Mobile,Type\nExisting,9876500099,Stale sheet value\n",
        {"name": "Name", "phone": "Mobile", "custom_property_type": "Type"},
        duplicate_action="update",
    )

    assert CustomFieldValue.objects.get(lead=lead, field=property_type).value == "Verified: Villa"


# ============================================================
# The extractor in isolation
# ============================================================

def test_extractor_only_claims_the_custom_prefix():
    """Standard columns must not be mistaken for custom fields."""
    class Stub:
        field_key = "property_type"

    fields = {"property_type": Stub()}
    row = {
        "name": "Rahul", "phone": "9876543210", "city": "Pune",
        "custom_property_type": "3BHK",
    }
    out = _extract_custom_values(row, fields)
    assert list(out.values()) == ["3BHK"]
    assert len(out) == 1


def test_extractor_skips_unknown_and_blank():
    class Stub:
        field_key = "known"

    fields = {"known": Stub()}
    row = {"custom_known": "  ", "custom_gone": "value", "custom_other": None}
    assert _extract_custom_values(row, fields) == {}


# ============================================================
# Auto-detection of custom columns
# ============================================================

class _Field:
    """Stand-in for CustomField — auto_map_custom_fields only reads two attrs."""

    def __init__(self, name, field_key):
        self.name = name
        self.field_key = field_key


def test_header_matching_the_field_name_is_auto_mapped():
    from apps.leads.views import auto_map_custom_fields

    fields = [_Field("Loan Amount", "loan_amount")]
    assert auto_map_custom_fields(["Name", "Loan Amount"], fields) == {
        "custom_loan_amount": "Loan Amount",
    }


def test_matching_ignores_case_spaces_and_separators():
    from apps.leads.views import auto_map_custom_fields

    fields = [_Field("Rate of Interest", "rate_of_interest")]
    for header in ("RATE OF INTEREST", "rate_of_interest", "Rate-Of-Interest", "rateofinterest"):
        assert auto_map_custom_fields(["Name", header], fields) == {
            "custom_rate_of_interest": header,
        }, header


def test_a_near_miss_is_left_for_the_admin():
    """
    "Amount" is not "Loan Amount". Guessing here would silently write the wrong
    column into a field someone then has to find and correct — worse than making
    them choose from the dropdown.
    """
    from apps.leads.views import auto_map_custom_fields

    fields = [_Field("Loan Amount", "loan_amount")]
    assert auto_map_custom_fields(["Name", "Amount", "Disbursed"], fields) == {}


def test_the_field_key_also_matches():
    from apps.leads.views import auto_map_custom_fields

    fields = [_Field("Branch Office", "branch")]
    assert auto_map_custom_fields(["branch"], fields) == {"custom_branch": "branch"}


def test_duplicate_headers_do_not_flip_the_target():
    from apps.leads.views import auto_map_custom_fields

    fields = [_Field("Tenure", "tenure")]
    assert auto_map_custom_fields(["Tenure", "tenure"], fields) == {"custom_tenure": "Tenure"}


def test_no_headers_and_no_fields_are_both_safe():
    from apps.leads.views import auto_map_custom_fields

    assert auto_map_custom_fields([], [_Field("Tenure", "tenure")]) == {}
    assert auto_map_custom_fields(["Tenure"], []) == {}


@pytest.mark.django_db
def test_auto_mapped_columns_actually_import(property_type):
    """The guess has to survive into stored values, not just the preview."""
    from apps.leads.views import auto_map_custom_fields

    headers = ["Name", "Mobile", "Property Type"]
    mapping = {"name": "Name", "phone": "Mobile"}
    mapping.update(auto_map_custom_fields(headers, [property_type]))

    _run_import("Name,Mobile,Property Type\nDeepak Joshi,9876500111,Row House\n", mapping)

    lead = Lead.objects.get(phone="+919876500111")
    assert CustomFieldValue.objects.get(lead=lead, field=property_type).value == "Row House"


# ============================================================
# Job result counters
# ============================================================
# mark_completed() saved with update_fields=["status", "completed_at"], so the
# counters assigned immediately before it were discarded. Every finished job
# reported 0/0/0 with no errors, which is what made a fully-skipped duplicate
# import look identical to one that silently created nothing.

@pytest.mark.django_db
def test_successful_rows_are_recorded():
    job = _run_import(
        "Name,Mobile\nAsha Rao,9876500201\nBinu Nair,9876500202\n",
        {"name": "Name", "phone": "Mobile"},
    )
    assert job.successful_rows == 2
    assert job.failed_rows == 0
    assert job.status == "completed"


@pytest.mark.django_db
def test_skipped_duplicates_are_recorded():
    """The case that hid the real behaviour: everything skipped, nothing said."""
    Lead.objects.create(name="Asha Rao", phone="+919876500211")

    job = _run_import(
        "Name,Mobile\nAsha Rao,9876500211\n",
        {"name": "Name", "phone": "Mobile"},
        duplicate_action="skip",
    )
    assert job.duplicate_rows == 1
    assert job.successful_rows == 0
    assert Lead.objects.filter(phone="+919876500211").count() == 1


@pytest.mark.django_db
def test_failed_rows_and_their_errors_are_recorded():
    job = _run_import(
        "Name,Mobile\nNo Phone Person,\nGood Person,9876500221\n",
        {"name": "Name", "phone": "Mobile"},
    )
    assert job.failed_rows == 1
    assert job.successful_rows == 1
    assert job.row_errors, "the reason a row failed must survive the save"
    assert "Phone" in str(job.row_errors[0])
    # One good row and one bad = partial, not completed.
    assert job.status == "partial"


@pytest.mark.django_db
def test_update_mode_survives_a_repeated_phone(property_type):
    """
    phone is not unique. get() raised MultipleObjectsReturned on a number held
    by two leads, and `except Lead.DoesNotExist` did not catch it — so the row
    was counted as failed instead of updated. Oldest lead wins.
    """
    first = Lead.objects.create(name="Ravi A", phone="+919876500301")
    Lead.objects.create(name="Ravi B", phone="+919876500301")

    job = _run_import(
        "Name,Mobile,Type\nRavi,9876500301,Bungalow\n",
        {"name": "Name", "phone": "Mobile", "custom_property_type": "Type"},
        duplicate_action="update",
    )

    assert job.failed_rows == 0
    assert job.duplicate_rows == 1
    assert CustomFieldValue.objects.get(lead=first, field=property_type).value == "Bungalow"
