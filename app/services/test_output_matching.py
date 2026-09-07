"""Locate a control's testing-output JSON and normalise its sample rows.

Output files live in the client's test_outputs directory, one per
control+entity, e.g. "IA8.CA02.19A1.TestOutput.json":

    {"control_test_output": {"control_number": "IA8.CA02",
                             "entity_code": "19A1", ...},
     "test_details": {"1": {"sample_no": 1, "Document No": "...", ...}, ...}}

As with control definitions, files are matched on their CONTENT
(control_test_output.control_number / entity_code) rather than their
filename, and any extension is accepted so long as the body parses as JSON.

The per-sample keys use the client's own column names ("Document No",
"Amount in local cur.", ...). normalise_sample() maps those onto stable
field names for the API while keeping every remaining key as a displayable
parameter, so new columns in the source data flow through untouched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Source key -> stable API field for the columns the Testing table needs.
_CORE_FIELDS = {
    "sample_no": "sample_no",
    "Document No": "document_no",
    "result": "result",
    "validation": "validation",
    "pages": "pages",
}

# Source keys surfaced as the grouped "Parameters" object, in display order.
_PARAMETER_KEYS = [
    "Type",
    "Document description",
    "Posting date",
    "Amount in local cur.",
    "LCurr",
    "Text",
]


def iter_test_outputs(test_outputs_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    """(path, payload) for every file that parses as a testing-output JSON."""
    if not test_outputs_dir.exists():
        return []
    results: list[tuple[Path, dict[str, Any]]] = []
    for candidate in sorted(test_outputs_dir.iterdir()):
        if not candidate.is_file() or candidate.name.startswith("."):
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and "control_test_output" in payload:
            results.append((candidate, payload))
    return results


def find_test_output(
    test_outputs_dir: Path, control_number: str, entity_code: str | None
) -> dict[str, Any] | None:
    """Return the testing output whose header matches control (+ entity).

    When entity_code is given it must match too; when it is None the first
    output for that control number wins.
    """
    for _path, payload in iter_test_outputs(test_outputs_dir):
        header = payload.get("control_test_output") or {}
        if str(header.get("control_number", "")).strip() != control_number.strip():
            continue
        if entity_code is not None:
            if str(header.get("entity_code", "")).strip() != entity_code.strip():
                continue
        return payload
    return None


def normalise_sample(key: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Map one raw test_details entry onto the API's sample shape.

    Every key that isn't a core field becomes a parameter, so the six
    documented parameters are grouped without hard-coding them as the only
    possibility.
    """
    out: dict[str, Any] = {
        "sample_no": None,
        "document_no": None,
        "result": None,
        "validation": None,
        "pages": [],
    }
    parameters: list[dict[str, Any]] = []
    extras: dict[str, Any] = {}

    for src_key, value in raw.items():
        if src_key in _CORE_FIELDS:
            out[_CORE_FIELDS[src_key]] = value
        else:
            extras[src_key] = value

    # Documented parameters first, in order; then anything else present.
    for pkey in _PARAMETER_KEYS:
        if pkey in extras:
            parameters.append({"label": pkey, "value": extras.pop(pkey)})
    for pkey, value in extras.items():
        parameters.append({"label": pkey, "value": value})

    # Fall back to the dict key when the row omits its own sample_no.
    if out["sample_no"] is None:
        try:
            out["sample_no"] = int(key)
        except (TypeError, ValueError):
            out["sample_no"] = key

    out["parameters"] = parameters
    return out


def build_samples(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalised, numerically-ordered sample rows from a testing output."""
    details = payload.get("test_details") or {}
    if not isinstance(details, dict):
        return []

    def sort_key(k: str) -> tuple[int, Any]:
        try:
            return (0, int(k))
        except (TypeError, ValueError):
            return (1, k)

    return [normalise_sample(k, details[k]) for k in sorted(details, key=sort_key)]
