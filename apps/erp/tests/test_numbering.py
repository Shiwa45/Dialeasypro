"""
Document numbering at the start of a financial year (LOW-12).

The sequence row was created with get_or_create. Two documents raised at the
same moment on 1 April both found no row and both INSERTed; the loser's
IntegrityError aborted its transaction and the user got a 500.
"""
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError

from apps.erp.models import DocumentSequence
from apps.erp.services.numbering import financial_year, next_number

pytestmark = pytest.mark.django_db


def test_losing_the_race_to_create_the_sequence_does_not_fail():
    """What the losing request sees: its INSERT collides with the winner's."""
    with patch.object(DocumentSequence.objects, "get_or_create",
                      side_effect=IntegrityError("duplicate key")):
        first = next_number("invoice")
        second = next_number("invoice")

    assert first.endswith("/00001")
    assert second.endswith("/00002")


def test_the_financial_year_turns_over_in_ist_not_utc():
    """00:30 IST on 1 April is still 31 March in UTC — the old year."""
    just_after_midnight = datetime(2027, 4, 1, 0, 30, tzinfo=ZoneInfo("Asia/Kolkata"))

    with patch("django.utils.timezone.now", return_value=just_after_midnight):
        assert financial_year() == "2027-28"
