"""The demo scenario layered over the testing output for phased cycles.

`misc/phase_demo.json` (PHASE_DEMO_PATH) can, per control, pin which sample a
phase draws first and override fields of that sample's testing output. Only
matrix-sampled (phased) cycles apply it; the full-population baseline reads
the testing output untouched. The testing output files themselves are never
modified.

Matching follows the other client-data loaders: by control number + entity
code, degrading to "no scenario" when the file is missing or malformed.
"""

from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from typing import Any

from app.core.config import settings

# Fields, in order of preference, that date a sample. A sample with none of
# them (e.g. IA5.CA04's sales orders) is undated and fits any window.
DATE_FIELDS = (
    "Posting date",
    "Posting Date",
    "Document Date",
    "Date of change",
    "Date of review",
    "Created on",
)
_MONTHS = {
    m: i
    for i, m in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1
    )
}


def _load() -> list[dict[str, Any]]:
    path = Path(settings.PHASE_DEMO_PATH)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    controls = payload.get("controls") if isinstance(payload, dict) else None
    return [c for c in controls or [] if isinstance(c, dict)]


def scenario_for(control_number: str, entity_code: str | None) -> dict[str, Any]:
    for entry in _load():
        if str(entry.get("control_number", "")).strip() != control_number.strip():
            continue
        if entity_code and str(entry.get("entity_code", "")).strip() != entity_code.strip():
            continue
        return entry
    return {}


def pins_for(control_number: str, entity_code: str | None) -> dict[str, list[int]]:
    pins = scenario_for(control_number, entity_code).get("pins") or {}
    return {
        str(phase).upper(): [n for n in nos if isinstance(n, int)]
        for phase, nos in pins.items()
        if isinstance(nos, list)
    }


def demo_changes_for(control_number: str, entity_code: str | None) -> dict[str, dict[str, Any]]:
    """Fields of the control changed for the demo: {field: {from, to, note}}.

    The change itself is applied to the data by scripts/apply_demo_changes.py;
    this is what lets every screen mark the changed value as a demo change.
    """
    changes = scenario_for(control_number, entity_code).get("demo_changes") or {}
    return {
        str(field): change
        for field, change in changes.items()
        if isinstance(change, dict) and change.get("to") is not None
    }


def with_demo_changes(
    payload: dict[str, Any], control_number: str, entity_code: str | None
) -> dict[str, Any]:
    """A control definition with the demo's field changes applied (a copy).

    Seeding and importing pass every definition through this, so a control
    changed for the demo keeps the change when the repository is refreshed
    from the client's (unchanged) control JSON files.
    """
    change = demo_changes_for(control_number, entity_code).get("frequency")
    if not change:
        return payload
    out = copy.deepcopy(payload)
    out.setdefault("rcm_details", {})["Frequency"] = change["to"]
    return out


def excluded_for(control_number: str, entity_code: str | None) -> set[int]:
    nos = scenario_for(control_number, entity_code).get("exclude") or []
    return {n for n in nos if isinstance(n, int)}


def apply_overlay(
    payload: dict[str, Any] | None, control_number: str, entity_code: str | None
) -> dict[str, Any] | None:
    """The testing output with the scenario's sample overrides applied.

    Returns a copy; the payload passed in (often cached by the caller) is left
    as it was.
    """
    if not payload:
        return payload
    overrides = scenario_for(control_number, entity_code).get("samples") or {}
    if not overrides:
        return payload
    out = copy.deepcopy(payload)
    details = out.get("test_details") or {}
    for key, sample in details.items():
        if not isinstance(sample, dict):
            continue
        change = overrides.get(str(sample.get("sample_no", key)))
        if isinstance(change, dict):
            sample.update(change)
    return out


def sample_date(sample: dict[str, Any]) -> date | None:
    """The date a sample's evidence falls on, or None for an undated sample."""
    fields = dict(sample)
    for param in sample.get("parameters") or []:
        if isinstance(param, dict) and param.get("label"):
            fields[str(param["label"])] = param.get("value")
    for name in DATE_FIELDS:
        raw = fields.get(name)
        if isinstance(raw, str) and len(raw) >= 10 and raw[4] == "-":
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                continue
    month = fields.get("Month")
    if isinstance(month, str) and "-" in month:
        name, _, year = month.partition("-")
        number = _MONTHS.get(name.strip()[:3].lower())
        if number and year.strip().isdigit():
            return date(2000 + int(year.strip()) % 100, number, 1)
    return None
