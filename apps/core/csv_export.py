"""
TeleCRM Backend — apps/core/csv_export.py

Cells and streams for CSV files people open in Excel.

- Formula injection. A cell starting with = + - @ (or a tab / carriage
  return) is run as a formula by Excel and LibreOffice. Lead names arrive
  from public webhooks and website forms, so `=HYPERLINK("http://evil",
  "Click")` in a lead's name became a live link in an admin's spreadsheet.
  Such cells are prefixed with an apostrophe, which spreadsheets show as
  text. Purely numeric values ("+919812345678", "-500") cannot run anything
  and are left alone, so phone numbers don't gain a stray quote.
- Encoding. Without a byte-order mark, Excel on Windows reads UTF-8 as the
  local code page: "Budget (₹)" became "Budget (â‚¹)" and Hindi names were
  garbled. Every stream starts with one.
- Time zone. Datetimes were written as raw UTC with microseconds, five and a
  half hours off. They are written in the tenant's local time, to the minute.
"""
import csv
import re
from datetime import datetime

from django.utils import timezone

BOM = "﻿"

_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")
_NUMERIC = re.compile(r"^[+-]?[\d\s().,-]+$")


def safe_cell(value):
    """One value, ready to be a CSV cell."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, str) and value.startswith(_FORMULA_TRIGGERS) and not _NUMERIC.match(value):
        return "'" + value
    return value


def safe_row(row):
    return [safe_cell(v) for v in row]


class _Echo:
    """A file-like object whose write() hands the line back instead of storing it."""

    def write(self, value):
        return value


def csv_stream(headers, rows):
    """
    Yield a CSV file line by line, for a StreamingHttpResponse.

    `rows` is any iterable of sequences; every cell goes through safe_cell().
    """
    writer = csv.writer(_Echo())
    yield BOM + writer.writerow(safe_row(headers))
    for row in rows:
        yield writer.writerow(safe_row(row))
