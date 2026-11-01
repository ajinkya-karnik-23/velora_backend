"""The Continuous Reviewable Process (CRP) workbook — placeholder format.

The client has not yet defined the CRP layout, so this produces a clean,
readable stand-in: a cover sheet describing the phase and its sign-off, and a
sheet listing each sample tested in it with its result and supporting
documents. It reads the same TwpContext as the TWP, so the two never disagree.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from app.services.twp_builder import TwpContext

INK = "1A1B20"
RULE = Side(style="thin", color="D4D6DB")
HEADER_FILL = PatternFill("solid", fgColor="F1F2F4")


def _when(epoch: int | None) -> str:
    if not epoch:
        return "—"
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%d %b %Y")


def _param(sample: dict[str, Any], *names: str) -> Any:
    for param in sample.get("parameters") or []:
        if isinstance(param, dict) and param.get("label") in names:
            return param.get("value")
    for name in names:
        if sample.get(name) not in (None, ""):
            return sample.get(name)
    return None


def build_crp_workbook(
    control_number: str,
    control_name: str | None,
    entity_code: str | None,
    context: TwpContext,
) -> Workbook:
    wb = Workbook()
    cover = wb.active
    cover.title = "CRP"
    cover["A1"] = "Continuous Reviewable Process"
    cover["A1"].font = Font(name="Calibri", size=18, bold=True, color=INK)
    cover["A2"] = (
        f"{control_number}{'.' + entity_code if entity_code else ''} · {control_name or ''}"
    )
    cover["A2"].font = Font(name="Calibri", size=12, color="5F6368")

    samples = context.samples or []
    exceptions = [s for s in samples if str(s.get("result") or "").upper() in ("FAIL", "FAILED")]
    rows: list[tuple[str, Any]] = [
        ("Review cycle", context.cycle_name or "—"),
        ("Phase", f"{context.phase_name} ({context.phase_label})" if context.phase_label else "—"),
        ("Evidence window", context.evidence_window or "—"),
        ("Sample size basis", context.size_basis or "—"),
        ("Samples tested", len(samples)),
        ("Exceptions", len(exceptions)),
        ("Outcome", context.phase_outcome or context.review_status or "—"),
        ("Failure reason", context.failure_reason or "—"),
        ("Prepared by", context.tester or "—"),
        ("Submitted", _when(context.submitted_time)),
        ("Reviewed by", context.reviewer or "—"),
        ("Concluded", _when(context.phase_concluded_time or context.reviewed_time)),
    ]
    for i, (label, value) in enumerate(rows, start=4):
        cover.cell(row=i, column=1, value=label).font = Font(name="Calibri", bold=True)
        cell = cover.cell(row=i, column=2, value=value)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    cover.column_dimensions["A"].width = 24
    cover.column_dimensions["B"].width = 90

    sheet = wb.create_sheet("Samples")
    headers = ["Sample", "Document", "Date", "Result", "Supporting documents", "Testing note"]
    for col, title in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=col, value=title)
        cell.font = Font(name="Calibri", bold=True, color=INK)
        cell.fill = HEADER_FILL
        cell.border = Border(bottom=RULE)
    for r, sample in enumerate(samples, start=2):
        no = sample.get("sample_no")
        docs = context.documents.get(no, []) if isinstance(no, int) else []
        values = [
            no,
            sample.get("document_no")
            or _param(sample, "Document Number", "Sales order No", "Customer name"),
            _param(
                sample, "Posting Date", "Posting date", "Document Date", "Date of change", "Month"
            ),
            sample.get("result"),
            "\n".join(f"{ref} · {name}" for ref, name in docs) or "—",
            sample.get("validation"),
        ]
        for col, value in enumerate(values, start=1):
            cell = sheet.cell(row=r, column=col, value=value)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = Border(bottom=RULE)
    for col, width in zip("ABCDEF", (9, 18, 14, 10, 44, 90), strict=True):
        sheet.column_dimensions[col].width = width
    return wb


def build_cycle_crp_workbook(
    cycle_name: str,
    phase: str,
    phase_name: str,
    controls: list[tuple[str, str | None, str | None, TwpContext]],
) -> Workbook:
    """The CRP for one phase across a cycle, issued once every control on that
    phase has cleared it: a cover, one row per control (its final round —
    the phase itself or its last remediation round) and every sample tested
    in those rounds. `controls` is (control number, name, entity, context)."""
    wb = Workbook()
    cover = wb.active
    cover.title = "CRP"
    cover["A1"] = "Continuous Reviewable Process"
    cover["A1"].font = Font(name="Calibri", size=18, bold=True, color=INK)
    cover["A2"] = f"{cycle_name} · {phase_name} ({phase})"
    cover["A2"].font = Font(name="Calibri", size=12, color="5F6368")

    def exceptions(ctx: TwpContext) -> int:
        return sum(
            1 for s in ctx.samples or [] if str(s.get("result") or "").upper() in ("FAIL", "FAILED")
        )

    remediated = [c for c in controls if (c[3].phase_label or "").startswith("RM")]
    concluded = [c[3].phase_concluded_time for c in controls if c[3].phase_concluded_time]
    rows: list[tuple[str, Any]] = [
        ("Review cycle", cycle_name),
        ("Phase", f"{phase_name} ({phase})"),
        (
            "Evidence window",
            next((c[3].evidence_window for c in controls if c[3].evidence_window), "—"),
        ),
        ("Controls in the phase", len(controls)),
        ("Approved", f"{len(controls)} of {len(controls)}"),
        ("Cleared after remediation", len(remediated)),
        ("Samples tested", sum(len(c[3].samples or []) for c in controls)),
        ("Exceptions in the final rounds", sum(exceptions(c[3]) for c in controls)),
        ("Phase cleared", _when(max(concluded)) if concluded else "—"),
        ("Issued", datetime.now(tz=UTC).strftime("%d %b %Y")),
    ]
    for i, (label, value) in enumerate(rows, start=4):
        cover.cell(row=i, column=1, value=label).font = Font(name="Calibri", bold=True)
        cell = cover.cell(row=i, column=2, value=value)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    cover.column_dimensions["A"].width = 30
    cover.column_dimensions["B"].width = 80

    def table(
        title: str, headers: list[str], body: list[list[Any]], widths: tuple[int, ...]
    ) -> None:
        sheet = wb.create_sheet(title)
        for col, head in enumerate(headers, start=1):
            cell = sheet.cell(row=1, column=col, value=head)
            cell.font = Font(name="Calibri", bold=True, color=INK)
            cell.fill = HEADER_FILL
            cell.border = Border(bottom=RULE)
        for r, values in enumerate(body, start=2):
            for col, value in enumerate(values, start=1):
                cell = sheet.cell(row=r, column=col, value=value)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                cell.border = Border(bottom=RULE)
        for col, width in enumerate(widths, start=1):
            sheet.column_dimensions[chr(64 + col)].width = width

    table(
        "Controls",
        [
            "Control",
            "Name",
            "Final round",
            "Size basis",
            "Samples",
            "Exceptions",
            "Outcome",
            "Prepared by",
            "Reviewed by",
            "Concluded",
        ],
        [
            [
                f"{number}{'.' + entity if entity else ''}",
                name,
                ctx.phase_label,
                ctx.size_basis,
                len(ctx.samples or []),
                exceptions(ctx),
                ctx.phase_outcome or ctx.review_status,
                ctx.tester,
                ctx.reviewer,
                _when(ctx.phase_concluded_time or ctx.reviewed_time),
            ]
            for number, name, entity, ctx in controls
        ],
        (18, 30, 12, 40, 9, 11, 14, 18, 18, 13),
    )
    samples: list[list[Any]] = []
    for number, _name, _entity, ctx in controls:
        for s in ctx.samples or []:
            no = s.get("sample_no")
            docs = ctx.documents.get(no, []) if isinstance(no, int) else []
            samples.append(
                [
                    number,
                    ctx.phase_label,
                    no,
                    s.get("document_no")
                    or _param(s, "Document Number", "Sales order No", "Customer name"),
                    _param(
                        s,
                        "Posting Date",
                        "Posting date",
                        "Document Date",
                        "Date of change",
                        "Month",
                    ),
                    s.get("result"),
                    "\n".join(f"{ref} · {doc}" for ref, doc in docs) or "—",
                ]
            )
    table(
        "Samples",
        ["Control", "Round", "Sample", "Document", "Date", "Result", "Supporting documents"],
        samples,
        (14, 10, 9, 18, 14, 10, 60),
    )
    return wb
