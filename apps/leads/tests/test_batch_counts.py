"""
Batch lead counts follow deletions (LOW-2).

LeadBatch.total_leads went up as leads arrived and never came down, so a
batch kept counting leads that had been deleted.
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.core.constants import AgentRole
from apps.leads.models import Lead, LeadBatch
from apps.leads.views import LeadDetailView

pytestmark = pytest.mark.django_db


@pytest.fixture
def batch():
    batch = LeadBatch.objects.create(name="Diwali")
    for i in range(3):
        Lead.objects.create(name=f"L{i}", phone=f"+91981230010{i}", batch=batch)
    batch.recount()
    return batch


def test_deleting_a_lead_takes_it_off_the_batch_count(batch):
    manager = Agent.objects.create_agent(
        email="m@x.com", name="M", password="Pw@12345678", role=AgentRole.MANAGER,
    )
    lead = batch.leads.first()
    request = APIRequestFactory().delete(f"/api/v1/leads/{lead.pk}/")
    force_authenticate(request, user=manager)

    assert LeadDetailView.as_view()(request, pk=lead.pk).status_code == 204

    batch.refresh_from_db()
    assert batch.total_leads == 2


def test_retention_cleanup_takes_leads_off_the_count(batch):
    from datetime import timedelta

    from django.db import connection
    from django.utils import timezone

    from apps.leads.tasks import cleanup_old_leads

    Lead.objects.filter(pk=batch.leads.first().pk).update(
        created_at=timezone.now() - timedelta(days=400)
    )
    cleanup_old_leads.run(connection.schema_name, 365)

    batch.refresh_from_db()
    assert batch.total_leads == 2
