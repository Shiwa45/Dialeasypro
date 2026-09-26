"""apps/core/csv_export.safe_cell — see the module docstring for why."""
from decimal import Decimal

import pytest

from apps.core.csv_export import csv_stream, safe_cell


@pytest.mark.parametrize("value", [
    "=1+1", "+cmd|' /C calc'!A0", "-2+3+cmd|' /C calc'!A0", "@SUM(A1:A2)",
    "\t=1+1", "\r=1+1", '=HYPERLINK("http://evil","Click")',
])
def test_anything_a_spreadsheet_would_run_is_escaped(value):
    assert safe_cell(value) == "'" + value


@pytest.mark.parametrize("value", ["+919812345678", "-500", "+91 98123 45678", "Asha", "", "a=b"])
def test_ordinary_text_and_numbers_are_untouched(value):
    assert safe_cell(value) == value


def test_non_strings_pass_through():
    assert safe_cell(Decimal("-5.00")) == Decimal("-5.00")
    assert safe_cell(-3) == -3
    assert safe_cell(None) == ""
    assert safe_cell(True) == "Yes"


def test_the_stream_starts_with_a_bom_and_escapes_every_row():
    lines = list(csv_stream(["Name"], [["=1+1"]]))

    assert lines[0] == "﻿Name\r\n"
    assert lines[1] == "'=1+1\r\n"
