"""Evidence gating and page extraction for the Testing workspace.

Two responsibilities:

1. Filename verification — a control only runs when the evidence uploaded
   for it matches the filename mapped for that control. The mapping lives in
   the client's Miscellaneous folder and is editable without a code change.

2. Page extraction — the Explore action opens only the evidence pages a
   given sample was validated against, taken from the testing output.

Verification failures are deliberately opaque to the caller: the expected
filename is never returned, so it cannot leak into a UI message.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter


def load_expected_filename(
    map_path: Path, control_number: str, entity_code: str | None
) -> str | None:
    """Expected evidence filename for a control+entity, or None if unmapped.

    An unmapped control returns None, which callers treat as "no filename
    requirement" rather than an automatic failure — otherwise adding a
    control would silently block all of its testing.
    """
    if not map_path.exists():
        return None
    try:
        payload = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    for record in payload.get("controls") or []:
        if str(record.get("control_number", "")).strip() != control_number.strip():
            continue
        record_entity = str(record.get("entity_code", "")).strip()
        if entity_code is not None and record_entity != entity_code.strip():
            continue
        expected = record.get("expected_evidence_filename")
        return str(expected).strip() if expected else None
    return None


def load_filename_rule(
    map_path: Path, control_number: str, entity_code: str | None
) -> dict[str, Any] | None:
    """The raw filename-map record for a control+entity, or None if unmapped.

    Callers use this when they need more than the single expected filename —
    specifically the per-sample rule, where each sample expects its own file.
    """
    if not map_path.exists():
        return None
    try:
        payload = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    for record in payload.get("controls") or []:
        if str(record.get("control_number", "")).strip() != control_number.strip():
            continue
        record_entity = str(record.get("entity_code", "")).strip()
        if entity_code is not None and record_entity != entity_code.strip():
            continue
        return record if isinstance(record, dict) else None
    return None


def expected_filename_for_sample(
    rule: dict[str, Any] | None, sample: dict[str, Any] | None
) -> str | None:
    """Expected evidence filename for one sample.

    Two shapes are supported, and a control uses exactly one:

    * ``expected_evidence_filename`` — a single file every sample must supply.
      This is the original behaviour and is returned unchanged.
    * ``expected_evidence_filename_fields`` — the filename is derived from the
      sample's own data: the first listed field that carries a value becomes
      the stem, so each row expects a different file (customer "David" ->
      "David.pdf"). Rows that identify themselves differently (a monthly
      review has no customer, only a month) fall through to the next field.

    Returns None when the control is unmapped, or when the sample carries
    none of the named fields — which callers treat as "no requirement"
    rather than an automatic failure, so a data gap never silently blocks
    testing.
    """
    if not rule:
        return None

    fixed = rule.get("expected_evidence_filename")
    if fixed:
        return str(fixed).strip()

    fields = rule.get("expected_evidence_filename_fields") or []
    if not fields or not sample:
        return None

    extension = str(rule.get("expected_evidence_extension") or "").strip()
    for field in fields:
        value = sample.get(field)
        if value is None:
            continue
        stem = _safe_stem(str(value))
        if not stem:
            continue
        # A stem that already carries the extension is used as-is, so the
        # rule stays correct whether or not the data includes it.
        if extension and not stem.lower().endswith(extension.lower()):
            stem += extension
        return stem
    return None


def _safe_stem(value: str) -> str:
    """A field value reduced to something that can be a real filename.

    Client data legitimately contains characters a filename cannot hold — a
    customer recorded as "PSBT BT-Stal sp. z.o.o./Rawa Mazowiecka" cannot be
    matched by any single file. Path separators are folded to a hyphen so the
    expectation stays one predictable name rather than silently collapsing to
    the trailing segment, which is what plain path handling would do.
    """
    cleaned = value.strip()
    for separator in ("/", "\\"):
        cleaned = cleaned.replace(separator, "-")
    return " ".join(cleaned.split()).strip()


def filename_matches(uploaded: str | None, expected: str | None) -> bool:
    """Case-insensitive filename comparison, ignoring any folder path.

    A missing expectation means the control is unmapped and passes.
    """
    if not expected:
        return True
    if not uploaded:
        return False
    return Path(uploaded).name.strip().lower() == Path(expected).name.strip().lower()


def extract_pages(pdf_bytes: bytes, pages: list[int]) -> bytes:
    """Return a PDF containing only `pages` (1-indexed) from the source.

    Page numbers outside the document are skipped rather than raising, so a
    testing output referencing a stale page cannot break the viewer. If no
    requested page exists, the original document is returned unchanged.
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total = len(reader.pages)
    wanted = [p for p in pages if isinstance(p, int) and 1 <= p <= total]
    if not wanted:
        return pdf_bytes

    writer = PdfWriter()
    for page_no in wanted:
        writer.add_page(reader.pages[page_no - 1])

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def build_methodology(
    samples: list[dict[str, Any]], header: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Sample-population figures shown in step 1 of each sample's log.

    A control may declare its own methodology in its testing output header:

        "methodology": {
          "label": "Credit limit amendment and monthly review testing",
          "breakdown": [
            {"label": "Credit limit amendments", "when_field": "Customer name"},
            {"label": "Monthly reviews",         "when_field": "Month"}
          ]
        }

    Each line counts the samples carrying that field, so the categories suit
    whatever the control actually tests. Without a declaration the original
    journal-entry split applies unchanged: counts derived from the testing
    output, anything not typed "NR" treated as a manual journal entry.
    """
    total = len(samples)

    declared = (header or {}).get("methodology")
    if isinstance(declared, dict):

        def _fields(sample: dict[str, Any]) -> set[str]:
            names = {k for k in sample if k != "parameters"}
            for param in sample.get("parameters") or []:
                label = param.get("label") if isinstance(param, dict) else None
                if label:
                    names.add(label)
            return names

        present = [_fields(sample) for sample in samples]
        breakdown = [
            {
                "label": str(line.get("label", "")),
                "value": sum(1 for f in present if line.get("when_field") in f),
            }
            for line in declared.get("breakdown") or []
            if line.get("label")
        ]
        return {
            "methodology": str(declared.get("label") or "Sample-based testing"),
            "total_samples": total,
            "breakdown": breakdown,
        }

    nr = 0
    for sample in samples:
        type_value = next(
            (p.get("value") for p in sample.get("parameters", []) if p.get("label") == "Type"),
            None,
        )
        if str(type_value or "").strip().upper() == "NR":
            nr += 1
    return {
        "methodology": "NR & Manual Journal Entry testing",
        "total_samples": total,
        "breakdown": [
            {"label": "Manual Journal Entries", "value": total - nr},
            {"label": "NR Entries", "value": nr},
        ],
        "manual_entries": total - nr,
        "nr_entries": nr,
    }
