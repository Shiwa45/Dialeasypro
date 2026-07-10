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

from apps.erp.constants import DocumentType
from apps.erp.models import DocumentSequence


def financial_year(on: date | None = None) -> str:
    """Indian FY label for a date: April→March. e.g. 2026-27."""
    on = on or date.today()
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

    # get_or_create then lock: the row must exist before it can be locked.
    DocumentSequence.objects.get_or_create(doc_type=doc_type, financial_year=fy)
    seq = DocumentSequence.objects.select_for_update().get(doc_type=doc_type, financial_year=fy)

    seq.last_number += 1
    seq.save(update_fields=["last_number"])

    return f"{DocumentType.PREFIXES[doc_type]}/{fy}/{seq.last_number:05d}"
