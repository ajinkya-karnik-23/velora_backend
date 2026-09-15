"""The sample testing details sheet on completed work papers."""

from __future__ import annotations

import openpyxl
import pytest

from app.services.twp_sample_details import (
    DEFAULT_PERFORMER,
    FIRST_DATA_ROW,
    HEADER_ROW,
    SHEET_TITLE,
    add_sample_details_sheet,
    sample_remarks,
)
from app.services.twp_sample_details import testing_details as details_text

SAMPLES = [
    {
        "sample_no": 1,
        "document_no": "1900006431",
        "result": "PASS",
        "validation": "Invoice matched on page 1.",
        "pages": [1, 3],
        "parameters": [
            {"label": "Type", "value": "KR"},
            {"label": "Amount in local cur.", "value": 83514.51},
        ],
    },
    {
        "sample_no": 2,
        "document_no": "1900006432",
        "result": "NOT_VALIDATED",
        "validation": "No supporting invoice was provided.",
        "pages": [],
        "parameters": [
            {"label": "Type", "value": "SA"},
            # A field only this sample carries still gets its own column.
            {"label": "Month", "value": "Apr-25"},
            {"label": "Remarks", "value": "Evidence requested from owner."},
        ],
    },
]
EVIDENCE = [["JV's TOE.pdf"], []]


def _headers(ws) -> list[str]:
    return [c.value for c in ws[HEADER_ROW] if c.value is not None]


def _column(ws, header: str) -> int:
    return _headers(ws).index(header) + 1


def _build() -> openpyxl.worksheet.worksheet.Worksheet:
    wb = openpyxl.Workbook()
    return add_sample_details_sheet(
        wb, SAMPLES, EVIDENCE, control_number="IA8.CA02", entity_code="19A1"
    )


def test_one_column_per_parameter_then_remarks_and_details() -> None:
    ws = _build()

    assert ws.title == SHEET_TITLE
    assert _headers(ws) == [
        "Sample No.",
        "Document No.",
        "Type",
        "Amount in local cur.",
        "Month",
        "Result",
        "Remarks",
        "Testing Details",
    ]


def test_rows_carry_each_samples_values() -> None:
    ws = _build()
    first, second = FIRST_DATA_ROW, FIRST_DATA_ROW + 1

    assert ws.cell(first, _column(ws, "Amount in local cur.")).value == 83514.51
    assert ws.cell(first, _column(ws, "Month")).value is None
    assert ws.cell(second, _column(ws, "Month")).value == "Apr-25"
    assert ws.cell(first, _column(ws, "Result")).value == "OK"
    # Anything but a pass is an exception, never absorbed into the passes.
    assert ws.cell(second, _column(ws, "Result")).value == "Not OK"
    assert ws.cell(second, _column(ws, "Remarks")).value == "Evidence requested from owner."


def test_testing_details_holds_validation_evidence_and_performer() -> None:
    text = details_text(SAMPLES[0], EVIDENCE[0], DEFAULT_PERFORMER)

    assert "Invoice matched on page 1." in text
    assert "JV's TOE.pdf (pages 1, 3)" in text
    assert text.endswith("Performed by:\nVelora Admin")


def test_missing_evidence_is_stated_not_blank() -> None:
    assert "No evidence recorded." in details_text(SAMPLES[1], [], DEFAULT_PERFORMER)


def test_remarks_default_from_outcome() -> None:
    assert sample_remarks({"result": "PASS"}) == "No exception noted."
    assert sample_remarks({"result": "FAIL"}).startswith("Exception noted")


def test_document_column_dropped_when_samples_have_none() -> None:
    samples = [{**s, "document_no": None} for s in SAMPLES]
    ws = add_sample_details_sheet(
        openpyxl.Workbook(), samples, EVIDENCE, control_number="X", entity_code="Y"
    )
    assert "Document No." not in _headers(ws)


def test_rebuilding_replaces_the_sheet() -> None:
    wb = openpyxl.Workbook()
    add_sample_details_sheet(wb, SAMPLES, EVIDENCE, control_number="A", entity_code="B")
    add_sample_details_sheet(wb, SAMPLES, EVIDENCE, control_number="A", entity_code="B")

    assert wb.sheetnames.count(SHEET_TITLE) == 1


def test_evidence_must_line_up_with_samples() -> None:
    with pytest.raises(ValueError):
        add_sample_details_sheet(
            openpyxl.Workbook(), SAMPLES, [[]], control_number="A", entity_code="B"
        )


def test_pending_samples_are_marked_pending_not_exceptions() -> None:
    samples = [
        SAMPLES[0],
        {**SAMPLES[0], "sample_no": 3, "result": "PENDING", "parameters": []},
    ]
    ws = add_sample_details_sheet(
        openpyxl.Workbook(), samples, [["a.pdf"], ["b.pdf"]], control_number="A", entity_code="B"
    )

    assert ws.cell(FIRST_DATA_ROW + 1, _column(ws, "Result")).value == "Pending"
    assert ws.cell(FIRST_DATA_ROW + 1, _column(ws, "Remarks")).value.startswith("Assessment pending")
    assert "0 exception(s), 1 pending" in ws["A2"].value
