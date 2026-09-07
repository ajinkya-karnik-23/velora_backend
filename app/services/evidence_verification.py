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


def build_methodology(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Sample-population figures shown in step 1 of each sample's log.

    Counts are derived from the testing output rather than hard-coded, so
    they stay correct as the sample set changes. Anything not typed "NR" is
    treated as a manual journal entry.
    """
    total = len(samples)
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
        "manual_entries": total - nr,
        "nr_entries": nr,
    }
