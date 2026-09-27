"""
TeleCRM Backend — apps/erp/services/numbering.py

Race-safe document numbering.

GST law requires invoice numbers to be unique and consecutive within a
financial year. Computing `max(number) + 1` (as the platform's own Invoice
model does) races: two concurrent requests read the same max and emit the same
number. Here the counter lives in its own row and is taken under
`select_for_update()`, so concurrent callers serialize on it.

The whole issue must therefore happen inside the caller's transaction — the
lock is released at commit. Callers use @transaction.atomic.
"""
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.erp.constants import DocumentType
from apps.erp.models import DocumentSequence


def financial_year(on: date | None = None) -> str:
    """Indian FY label for a date: April→March. e.g. 2026-27."""
    # IST, not the server clock: from midnight to 5:30 AM on 1 April the
    # server's date is still 31 March, the previous financial year.
    on = on or timezone.localdate()
    start = on.year if on.month >= 4 else on.year - 1
    return f"{start}-{str(start + 1)[2:]}"


@transaction.atomic
def next_number(doc_type: str, on: date | None = None) -> str:
    """
    Reserve and format the next document number, e.g. "INV/2026-27/00001".

    Must be called inside the transaction that persists the document; if that
    transaction rolls back the number is released and reused (no gaps).
    """
    if doc_type not in DocumentType.PREFIXES:
        raise ValueError(f"Unknown document type: {doc_type}")

    fy = financial_year(on)

    # Make sure the row exists, then lock it. get_or_create raced: the first
    # two documents of a new financial year both missed, both INSERTed, and
    # the loser's IntegrityError aborted its transaction — a 500. INSERT ...
    # ON CONFLICT DO NOTHING cannot fail that way, and the lock below still
    # hands out numbers one at a time.
    DocumentSequence.objects.bulk_create(
        [DocumentSequence(doc_type=doc_type, financial_year=fy)], ignore_conflicts=True,
    )
    seq = DocumentSequence.objects.select_for_update().get(doc_type=doc_type, financial_year=fy)

    seq.last_number += 1
    seq.save(update_fields=["last_number"])

    return f"{DocumentType.PREFIXES[doc_type]}/{fy}/{seq.last_number:05d}"
