"""
End-to-end: run the real import task and check the batch + auto-assign wiring.

These exercise process_lead_import itself rather than the pieces, because the
bugs that matter here live in the seams — a batch created before the file is
readable, leads stamped with the wrong batch, auto-assign running against
leads that were already assigned to the importing admin.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.constants import LeadSource
from apps.leads.models import Lead, LeadBatch, LeadImportJob
from apps.leads.tasks import process_lead_import

pytestmark = pytest.mark.django_db


CSV = (
    "name,phone,city\n"
    "Asha Menon,9876500001,Pune\n"
    "Bala Krishnan,9876500002,Chennai\n"
    "Chetan Rao,9876500003,Mumbai\n"
    "Divya Nair,9876500004,Kochi\n"
    "Esha Gupta,9876500005,Delhi\n"
    "Farid Khan,9876500006,Jaipur\n"
)


@pytest.fixture
def agents(db):
    from apps.authentication.models import Agent

    return [
        Agent.objects.create_agent(email=f"agent{i}@x.test", name=f"Agent {i}", password="x")
        for i in range(1, 4)
    ]


def _job(**kwargs):
    return LeadImportJob.objects.create(
        file=SimpleUploadedFile("leads.csv", CSV.encode()),
        original_filename="leads.csv",
        column_mapping={"name": "name", "phone": "phone", "city": "city"},
        default_source=LeadSource.CSV_IMPORT,
        **kwargs,
    )


def _run(job):
    from django.db import connection

    process_lead_import(connection.schema_name, str(job.id))
    job.refresh_from_db()
    return job


def test_import_creates_a_batch_and_stamps_every_lead(agents):
    job = _run(_job(batch_name="Diwali campaign"))

    assert job.successful_rows == 6
    batch = LeadBatch.objects.get(import_job=job)
    assert batch.name == "Diwali campaign"
    assert batch.label == "Diwali campaign"
    assert batch.kind == LeadBatch.KIND_IMPORT

    leads = Lead.objects.filter(import_job=job)
    assert leads.count() == 6
    assert all(lead.batch_id == batch.pk for lead in leads), "a lead escaped the batch"
    # The denormalised counter must match what actually landed.
    assert batch.total_leads == 6


def test_unnamed_import_gets_a_numbered_batch(agents):
    job = _run(_job())
    batch = LeadBatch.objects.get(import_job=job)
    assert batch.name == ""
    assert batch.label == f"Batch {batch.number}"


def test_auto_assign_distributes_round_robin(agents):
    a1, a2, a3 = agents
    job = _run(_job(
        batch_name="Auto",
        auto_assign=True,
        assign_method="round_robin",
        assign_to_agents=[a1.pk, a2.pk, a3.pk],
    ))

    leads = Lead.objects.filter(import_job=job)
    assert leads.filter(assigned_to__isnull=True).count() == 0, "a lead was left unassigned"
    # 6 leads, 3 agents, evenly.
    for agent in agents:
        assert leads.filter(assigned_to=agent).count() == 2

    assert job.assignment_result["distributed"] == 6
    assert sum(job.assignment_result["per_agent"].values()) == 6


def test_auto_assign_leaves_leads_unassigned_for_the_distributor(agents):
    """
    With auto-assign on, leads must land UNASSIGNED so the distributor has
    something to place. Defaulting them to the importing admin first would
    make every lead look assigned and the distribution a silent no-op.
    """
    a1 = agents[0]
    job = _job(auto_assign=True, assign_method="round_robin", assign_to_agents=[a1.pk])
    assert job.default_assigned_to is None or job.default_assigned_to == a1
    _run(job)
    assert Lead.objects.filter(import_job=job, assigned_to=a1).count() == 6


def test_auto_assign_respects_the_cap_and_reports_leftovers(agents):
    a1 = agents[0]
    job = _run(_job(
        auto_assign=True,
        assign_method="round_robin",
        assign_to_agents=[a1.pk],
        assign_max_per_agent=4,
    ))

    leads = Lead.objects.filter(import_job=job)
    assert leads.filter(assigned_to=a1).count() == 4
    assert leads.filter(assigned_to__isnull=True).count() == 2
    assert job.assignment_result["unassigned"] == 2
    assert "cap" in job.assignment_result["message"].lower()


def test_auto_assign_off_leaves_the_batch_alone(agents):
    job = _run(_job(batch_name="Manual later"))
    assert job.assignment_result == {}
    batch = LeadBatch.objects.get(import_job=job)
    assert batch.unassigned_count == 6


def test_inactive_agents_are_reported_not_silently_ignored(agents):
    a1 = agents[0]
    a1.is_active = False
    a1.save(update_fields=["is_active"])

    job = _run(_job(
        auto_assign=True, assign_method="round_robin", assign_to_agents=[a1.pk],
    ))
    assert job.assignment_result["distributed"] == 0
    assert "active" in job.assignment_result["message"].lower()
    # The leads are still safely batched — the import did not fail.
    assert Lead.objects.filter(import_job=job).count() == 6


def test_a_failed_import_leaves_no_orphan_batch(agents):
    """A batch is created only once the file parses, so a dead job leaves none."""
    before = LeadBatch.objects.count()
    job = LeadImportJob.objects.create(
        file=SimpleUploadedFile("broken.zzz", b"\x00\x01not a spreadsheet"),
        original_filename="broken.zzz",
        batch_name="Should not exist",
    )
    _run(job)
    assert job.status == "failed"
    assert LeadBatch.objects.count() == before


def test_second_import_gets_its_own_batch(agents):
    first = _run(_job(batch_name="Batch one"))
    second = _run(_job(batch_name="Batch two", duplicate_action="create_new"))

    b1 = LeadBatch.objects.get(import_job=first)
    b2 = LeadBatch.objects.get(import_job=second)
    assert b1.pk != b2.pk
    assert b2.number > b1.number
    # Distribution by batch is only meaningful if the two never overlap.
    assert not set(b1.leads.values_list("id", flat=True)) & set(
        b2.leads.values_list("id", flat=True)
    )


# ============================================================
# The API layer — where multipart parsing bugs live
# ============================================================

@pytest.fixture
def admin_agent(db):
    """A tenant admin. The API is JWT-authenticated, so see `_post_import`."""
    from apps.authentication.models import Agent

    return Agent.objects.create_tenant_admin(
        email="admin@x.test", name="Admin", password="pw12345!",
    )


def _post_import(agent, **extra):
    """
    Call LeadImportView directly through the DRF request factory.

    The endpoint authenticates with JWT, not sessions, so Django's
    `client.force_login` leaves it at 401 — force_authenticate is the
    equivalent for a DRF view.
    """
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.leads.views import LeadImportView

    payload = {
        "file": SimpleUploadedFile("leads.csv", CSV.encode(), content_type="text/csv"),
        "column_mapping": '{"name": "name", "phone": "phone", "city": "city"}',
        "source": LeadSource.CSV_IMPORT,
        # Required since the import screen made it required: a consignment
        # nobody named is one nobody can find again.
        "batch_name": "Test batch",
        **extra,
    }
    request = APIRequestFactory().post("/api/v1/leads/import/", payload, format="multipart")
    # TenantFeatureFlagMiddleware injects `has_feature` on a real request; the
    # factory bypasses middleware, so without this the plan gate 402s before
    # the view's own logic — the thing these tests are here to check — runs.
    request.has_feature = lambda key: True
    force_authenticate(request, user=agent)
    return LeadImportView.as_view()(request)


def test_auto_assign_false_string_is_not_treated_as_true(admin_agent, agents):
    """
    `auto_assign` crosses as multipart form data, so it arrives as the STRING
    "false". bool("false") is True — reading it naively would silently turn
    auto-assign on for everyone who explicitly turned it off.
    """
    res = _post_import(admin_agent, auto_assign="false")
    assert res.status_code == 202, res.data
    job = LeadImportJob.objects.latest("created_at")
    assert job.auto_assign is False


def test_auto_assign_without_agents_is_refused(admin_agent, agents):
    """Better a 400 than an import that quietly assigns nothing."""
    res = _post_import(admin_agent, auto_assign="true", assign_to_agents="[]")
    assert res.status_code == 400, res.data
    assert res.data["error"] == "agents_required"


def test_import_view_stores_the_batch_and_assign_options(admin_agent, agents):
    import json

    a1, a2, _ = agents
    res = _post_import(
        admin_agent,
        batch_name="  Spaced name  ",
        auto_assign="true",
        assign_method="least_loaded",
        assign_to_agents=json.dumps([a1.pk, a2.pk]),
        assign_max_per_agent="25",
    )
    assert res.status_code == 202, res.data
    job = LeadImportJob.objects.latest("created_at")
    assert job.batch_name == "Spaced name", "the name should be trimmed"
    assert job.auto_assign is True
    assert job.assign_method == "least_loaded"
    assert job.assign_to_agents == [a1.pk, a2.pk], "agent order must be preserved"
    assert job.assign_max_per_agent == 25
    # With auto-assign on, leads must NOT default to the importing admin.
    assert job.default_assigned_to is None


def test_unknown_assign_method_falls_back_rather_than_500ing(admin_agent, agents):
    import json

    res = _post_import(
        admin_agent,
        auto_assign="true",
        assign_method="telepathy",
        assign_to_agents=json.dumps([agents[0].pk]),
    )
    assert res.status_code == 202, res.data
    job = LeadImportJob.objects.latest("created_at")
    assert job.assign_method == "round_robin"


def test_stale_agent_ids_are_dropped(admin_agent, agents):
    import json

    a1 = agents[0]
    res = _post_import(
        admin_agent,
        auto_assign="true",
        assign_to_agents=json.dumps([a1.pk, 999999]),  # 999999 does not exist
    )
    assert res.status_code == 202, res.data
    job = LeadImportJob.objects.latest("created_at")
    assert job.assign_to_agents == [a1.pk]


def test_an_import_without_a_batch_name_is_refused(admin_agent, agents):
    """
    The name is how anyone finds the consignment again when they come to
    assign or report on it. "Batch 14" says nothing about where it came from.
    """
    res = _post_import(admin_agent, batch_name="   ")

    assert res.status_code == 400, res.data
    assert res.data["error"] == "batch_name_required"
