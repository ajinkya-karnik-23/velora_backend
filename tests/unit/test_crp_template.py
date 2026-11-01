"""Filling the client's CRP workbook keeps its structure and writes only
the cells the platform owns."""

from __future__ import annotations

import io
import re
import warnings
import zipfile
from pathlib import Path

import openpyxl
import pytest

from app.core.config import settings
from app.services.crp_template import (
    EFFECTIVE,
    NOT_APPLICABLE,
    PASS,
    READY_FOR_REVIEW,
    SELECT,
    CrpRow,
    fill_crp,
    template_frequency,
)

TEMPLATE = Path(settings.CRP_TEMPLATE_PATH)
pytestmark = pytest.mark.skipif(not TEMPLATE.exists(), reason="CRP template not present")


def _row(number: str) -> CrpRow:
    return CrpRow(
        control_number=number,
        entity_code="19A1",
        short_name=f"BP-ACIS.19A1..IA5...{number}.19A1. Test control",
        frequency="Annually",
        control_type="Manual",
        ipe="Yes",
        documents="Complete for testing ",
        test_performed=READY_FOR_REVIEW,
        test_result=EFFECTIVE,
        tester="Anshu Sharma",
        mandatory_fields=PASS,
        ipe_section=PASS,
        preparer_identified=PASS,
        samples_appropriate=PASS,
    )


def _counts(xml: str) -> tuple[int, ...]:
    return tuple(
        len(re.findall(k, xml))
        for k in ("<x14:dataValidation ", "<x14:conditionalFormatting", "<mergeCell ", "<row ")
    )


def _load(content: bytes) -> openpyxl.Workbook:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return openpyxl.load_workbook(io.BytesIO(content))


def test_each_sheet_lists_only_the_given_controls_and_structure_is_kept() -> None:
    template = TEMPLATE.read_bytes()
    row = _row("IA5.CA03.1")
    row.notes = {"P": "Sample #1 — PASS"}
    out = fill_crp(
        template,
        {"DE": [row, _row("IA8.CA02")]},
        {"F14": "19A1", "F16": "Reviewer"},
        {"DE": ["Note: 2 controls in scope."]},
    )

    before, after = zipfile.ZipFile(io.BytesIO(template)), zipfile.ZipFile(io.BytesIO(out))
    assert set(before.namelist()) <= set(after.namelist())
    for name in before.namelist():
        if name.startswith("xl/worksheets/sheet"):
            assert _counts(before.read(name).decode()) == _counts(after.read(name).decode())

    wb = _load(out)
    ws = wb["Test of Design"]
    assert "IA5.CA03.1.19A1" in ws["D6"].value
    assert "IA8.CA02.19A1" in ws["D7"].value
    assert ws["F6"].value == "Annually"
    assert ws["P6"].value == EFFECTIVE
    assert ws["R6"].value == "Anshu Sharma"
    assert ws["AJ6"].value == NOT_APPLICABLE
    assert ws["AD6"].value == SELECT  # Optro is outside the platform
    assert ws["P6"].comment is not None and "Sample #1" in ws["P6"].comment.text
    # The rest of the client's list is emptied and hidden; the filter that
    # hid our rows is gone; the scope note is the cycle's.
    assert not ws.row_dimensions[6].hidden and ws.row_dimensions[8].hidden
    assert ws["D8"].value is None
    assert not ws.auto_filter.filterColumn
    assert ws["D45"].value == "Note: 2 controls in scope."
    assert wb["Introductory Page"]["F16"].value == "Reviewer"


def test_rollforward_starts_its_list_at_the_first_row() -> None:
    out = fill_crp(TEMPLATE.read_bytes(), {"RF": [_row("IA5.CA03.1")]})
    ws = _load(out)["Rollforward"]
    assert ws["A6"].value is None  # the example row is replaced
    assert "IA5.CA03.1.19A1. Review of Credit Limits" in ws["D6"].value
    assert ws["P6"].value == EFFECTIVE
    assert ws.row_dimensions[7].hidden


def test_year_end_sheet_takes_annual_controls() -> None:
    out = fill_crp(TEMPLATE.read_bytes(), {"YE": [_row("IA5.CA03.1")]})
    wb = _load(out)
    assert wb.sheetnames[-1] == "Year End"
    ws = wb["Year End"]
    assert ws["B2"].value == "YEAR END"
    assert "IA5.CA03.1.19A1" in ws["D6"].value
    assert ws["P6"].value == EFFECTIVE


def test_a_phase_still_to_come_shows_identity_only() -> None:
    row = _row("IA5.CA03.1")
    row.identity_only = True
    ws = _load(fill_crp(TEMPLATE.read_bytes(), {"OE": [row]}))["Operating Effectiveness"]
    assert "IA5.CA03.1.19A1" in ws["D6"].value
    assert ws["P6"].value.startswith("Please select")
    assert ws["R6"].value == "Please complete the section…"


def test_frequency_uses_the_templates_words() -> None:
    assert template_frequency("Annual") == "Annually"
    assert template_frequency("Bi-annual") == "Bi-Annually"
    assert template_frequency("Monthly") == "Monthly"
