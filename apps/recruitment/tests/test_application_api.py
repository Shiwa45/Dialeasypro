"""
Applications over the API (LOW-14, LOW-15).

LOW-14: has_offer read a reverse one-to-one on every card, so the pipeline
board ran one query per application.
LOW-15: `candidate` and `opening` were writable on PATCH, so an application
could be moved to another opening with its stage and history intact.
"""
from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.authentication.models import Agent
from apps.recruitment.constants import OpeningStatus
from apps.recruitment.models import Candidate, JobOpening
from apps.recruitment.services import pipeline as pipeline_svc
from apps.recruitment.views import ApplicationDetailView, ApplicationListCreateView

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return Agent.objects.create_tenant_admin(email="own@x.com", name="Own", password="Pw@12345678")


def _opening(code):
    return JobOpening.objects.create(title=code, code=code, status=OpeningStatus.OPEN,
                                     openings=5, opened_on=date.today())


def _applications(n, opening):
    pipeline_svc.seed_pipeline()
    return [
        pipeline_svc.create_application(
            candidate=Candidate.objects.create(name=f"C{i}", email=f"c{i}@x.com"), opening=opening,
        )
        for i in range(n)
    ]


def _list(user):
    request = APIRequestFactory().get("/api/v1/recruitment/applications/")
    force_authenticate(request, user=user)
    request.has_feature = lambda key: True
    with CaptureQueriesContext(connection) as queries:
        response = ApplicationListCreateView.as_view()(request)
        response.render()
    return response, len(queries)


def test_the_board_does_not_query_per_card(admin):
    opening = _opening("OPEN-1")
    _applications(2, opening)
    _, few = _list(admin)

    _applications(8, opening)
    response, many = _list(admin)

    assert response.status_code == 200
    assert many == few, f"{few} queries for 2 cards, {many} for 10"


def test_an_application_cannot_be_moved_to_another_opening(admin):
    first, second = _opening("OPEN-A"), _opening("OPEN-B")
    application = _applications(1, first)[0]

    request = APIRequestFactory().patch(
        f"/api/v1/recruitment/applications/{application.pk}/",
        {"opening": second.pk, "rating": 4}, format="json",
    )
    force_authenticate(request, user=admin)
    request.has_feature = lambda key: True
    response = ApplicationDetailView.as_view()(request, pk=application.pk)

    assert response.status_code == 200
    application.refresh_from_db()
    assert application.opening_id == first.pk
    assert application.rating == 4, "ordinary fields still update"
