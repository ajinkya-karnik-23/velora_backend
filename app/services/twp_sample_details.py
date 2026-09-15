"""The "Sample Testing Details" sheet appended to a completed TWP work paper.

The Template sheet compresses each sample into one results line. This sheet is
the full record behind it: one row per sample, every tested parameter in its
own column, followed by the result, the remarks, and the testing details (the
validation narrative, the evidence it was run on, and who performed it).

Parameter columns are the union of every sample's parameters in first-seen
order, so a control whose samples describe themselves differently (credit
limit amendments alongside monthly reviews, say) still gets one column per
field rather than a column per sample shape.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

if TYPE_CHECKING:
    from collections.abc import Sequence

    from openpyxl.cell.cell import Cell
    from openpyxl.workbook.workbook import Workbook
    from openpyxl.worksheet.worksheet import Worksheet

SHEET_TITLE = "Sample Testing Details"

# Who is recorded as having performed the test until testers are tracked per
# sample.
DEFAULT_PERFORMER = "Velora Admin"

# Parameters lifted out into their own columns rather than repeated as tested
# fields.
REMARKS_KEY = "Remarks"

RESULT_OK = "OK"
RESULT_NOT_OK = "Not OK"
RESULT_PENDING = "Pending"

# Matches the Template sheet: Calibri 12, with its section-band blue-grey for
# the header so the two sheets read as one work paper.
FONT_NAME = "Calibri"
HEADER_FILL = "ADBBD7"
EXCEPTION_FILL = "FCE4E4"
# Excel's "Neutral" yellow: open, not failed.
PENDING_FILL = "FFF4D6"
RULE = Side(style="thin", color="A6A6A6")

HEADER_ROW = 4
FIRST_DATA_ROW = HEADER_ROW + 1

# Column widths, in Excel character units.
WIDTH_SAMPLE = 10
WIDTH_PARAMETER_MIN = 12
WIDTH_PARAMETER_MAX = 36
WIDTH_RESULT = 10
WIDTH_REMARKS = 34
WIDTH_DETAILS = 90


def _passed(sample: dict[str, Any]) -> bool:
    return (sample.get("result") or "").upper() in ("PASS", "PASSED")


def _pending(sample: dict[str, Any]) -> bool:
    return (sample.get("result") or "").strip().upper() == "PENDING"


def _parameter_labels(samples: Sequence[dict[str, Any]]) -> list[str]:
    """Every parameter label across the samples, in first-seen order."""
    labels: list[str] = []
    for sample in samples:
        for param in sample.get("parameters") or []:
            label = param.get("label")
            if label and label != REMARKS_KEY and label not in labels:
                labels.append(label)
    return labels


def _parameter_value(sample: dict[str, Any], label: str) -> object:
    for param in sample.get("parameters") or []:
        if param.get("label") == label:
            value = param.get("value")
            if isinstance(value, list):
                return ", ".join(str(v) for v in value)
            return value
    return None


def sample_remarks(sample: dict[str, Any]) -> str:
    """The sample's own remarks, or a plain statement of its outcome."""
    own = str(_parameter_value(sample, REMARKS_KEY) or "").strip()
    if own:
        return own
    if _passed(sample):
        return "No exception noted."
    if _pending(sample):
        return "Assessment pending. See testing details."
    return "Exception noted. See testing details."


def testing_details(sample: dict[str, Any], evidence: Sequence[str], performer: str) -> str:
    """Validation narrative, evidence used and performer, as one cell."""
    validation = str(sample.get("validation") or "").strip() or "No validation recorded."

    files = ", ".join(evidence) if evidence else "No evidence recorded."
    pages = sample.get("pages") or []
    if pages:
        label = "page" if len(pages) == 1 else "pages"
        files = f"{files} ({label} {', '.join(str(p) for p in pages)})"

    return (
        f"Validation summary:\n{validation}\n\n"
        f"Evidence used:\n{files}\n\n"
        f"Performed by:\n{performer}"
    )


def _style_header(cell: Cell) -> None:
    cell.font = Font(name=FONT_NAME, size=12, bold=True)
    cell.fill = PatternFill(fill_type="solid", start_color=HEADER_FILL, end_color=HEADER_FILL)
    cell.alignment = Alignment(vertical="center", wrap_text=True)
    cell.border = Border(left=RULE, right=RULE, top=RULE, bottom=RULE)


def _style_body(cell: Cell, *, fill: str | None) -> None:
    cell.font = Font(name=FONT_NAME, size=11)
    cell.alignment = Alignment(vertical="top", wrap_text=True)
    cell.border = Border(left=RULE, right=RULE, top=RULE, bottom=RULE)
    if fill:
        cell.fill = PatternFill(fill_type="solid", start_color=fill, end_color=fill)


def add_sample_details_sheet(
    workbook: Workbook,
    samples: Sequence[dict[str, Any]],
    evidence_by_sample: Sequence[Sequence[str]],
    *,
    control_number: str,
    entity_code: str,
    performer: str = DEFAULT_PERFORMER,
) -> Worksheet:
    """Append (or rebuild) the sample details sheet and return it.

    `evidence_by_sample` lines up with `samples`: the files each sample was
    tested against. A sheet left by an earlier build is replaced, so the
    builder can run on a workbook that already carries one.
    """
    if len(evidence_by_sample) != len(samples):
        raise ValueError("evidence_by_sample must have one entry per sample")

    if SHEET_TITLE in workbook.sheetnames:
        del workbook[SHEET_TITLE]
    ws = workbook.create_sheet(SHEET_TITLE)

    pending = sum(1 for s in samples if _pending(s))
    exceptions = sum(1 for s in samples if not _passed(s) and not _pending(s))
    ws["A1"] = f"{control_number}.{entity_code} sample testing details"
    ws["A1"].font = Font(name=FONT_NAME, size=16, bold=True)
    ws["A2"] = (
        f"{len(samples)} samples tested, {len(samples) - exceptions - pending} passed, "
        f"{exceptions} exception(s)"
        + (f", {pending} pending" if pending else "")
        + f". Performed by {performer}."
    )
    ws["A2"].font = Font(name=FONT_NAME, size=12)

    labels = _parameter_labels(samples)
    headers = ["Sample No.", "Document No.", *labels, "Result", "Remarks", "Testing Details"]
    # Controls whose samples are not documents get no empty Document column.
    has_documents = any(s.get("document_no") for s in samples)
    if not has_documents:
        headers.remove("Document No.")

    for col, header in enumerate(headers, start=1):
        _style_header(ws.cell(row=HEADER_ROW, column=col, value=header))

    for offset, (sample, evidence) in enumerate(zip(samples, evidence_by_sample, strict=True)):
        row = FIRST_DATA_ROW + offset
        passed = _passed(sample)
        is_pending = _pending(sample)
        values: list[object] = [sample.get("sample_no")]
        if has_documents:
            values.append(sample.get("document_no"))
        values.extend(_parameter_value(sample, label) for label in labels)
        values.extend(
            [
                RESULT_OK if passed else RESULT_PENDING if is_pending else RESULT_NOT_OK,
                sample_remarks(sample),
                testing_details(sample, evidence, performer),
            ]
        )
        for col, value in enumerate(values, start=1):
            fill = None if passed else PENDING_FILL if is_pending else EXCEPTION_FILL
            _style_body(ws.cell(row=row, column=col, value=value), fill=fill)

    # Widths: identifiers narrow, parameters sized to their longest value
    # within bounds, narrative columns wide enough to read without resizing.
    for col, header in enumerate(headers, start=1):
        letter = get_column_letter(col)
        if col == 1:
            width = WIDTH_SAMPLE
        elif header == "Document No.":
            width = 16
        elif header == "Result":
            width = WIDTH_RESULT
        elif header == "Remarks":
            width = WIDTH_REMARKS
        elif header == "Testing Details":
            width = WIDTH_DETAILS
        else:
            longest = max(
                [len(header)]
                + [
                    len(str(ws.cell(row=r, column=col).value or ""))
                    for r in range(FIRST_DATA_ROW, FIRST_DATA_ROW + len(samples))
                ]
            )
            width = max(WIDTH_PARAMETER_MIN, min(WIDTH_PARAMETER_MAX, longest + 2))
        ws.column_dimensions[letter].width = width

    last_col = get_column_letter(len(headers))
    last_row = FIRST_DATA_ROW + max(len(samples), 1) - 1
    ws.auto_filter.ref = f"A{HEADER_ROW}:{last_col}{last_row}"
    # Sample number and header stay in view while scrolling either way.
    ws.freeze_panes = ws.cell(row=FIRST_DATA_ROW, column=2)
    return ws
