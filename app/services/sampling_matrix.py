"""Sampling size calculation from the client's sampling matrix.

The matrix (<CLIENT_DATA_PATH>/misc/sampling_matrix.json) holds an
"Operating Effectiveness Testing" table keyed by control frequency, with
columns for each risk rating plus the testing-round columns RF/RM/YE:

    {"Monthly": {"Risk Rating Conclusion Medium": "2 to 5",
                 "RF (Full test)": 1, "RM": 2, "YE": null, ...}, ...}

Lookup rule
-----------
frequency picks the row. The column is picked by the control's phase when
that phase names a testing round (RF / RM / YE); otherwise — including the
common design/operating-effectiveness phases DE and OE — the column is
picked by the control's risk level.

Any miss (unknown frequency, unmapped column, null cell) yields no matrix
result, and the caller falls back to the "Sample Size" already present in
the control's own JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Phase codes that name a testing round and so select their own column.
PHASE_COLUMNS = {
    "RF": "RF (Full test)",
    "RM": "RM",
    "YE": "YE",
}

RISK_COLUMNS = {
    "low": "Risk Rating conclusion Low",
    "medium": "Risk Rating Conclusion Medium",
    "high": "Risk Rating Conclusion High",
}


def load_sampling_matrix(matrix_path: Path) -> dict[str, Any]:
    """Parse the sampling matrix JSON. Returns {} if missing/unreadable."""
    if not matrix_path.exists():
        return {}
    try:
        return json.loads(matrix_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _operating_effectiveness_table(matrix: dict[str, Any]) -> dict[str, Any]:
    return matrix.get("Sampling Methodology", {}).get("Operating Effectiveness Testing", {}) or {}


def _find_row(table: dict[str, Any], frequency: str) -> dict[str, Any] | None:
    """Case/whitespace-insensitive frequency row lookup."""
    target = (frequency or "").strip().lower()
    if not target:
        return None
    for key, row in table.items():
        if key.strip().lower() == target:
            return row
    return None


def resolve_column(risk_level: str | None, phase: str | None) -> str | None:
    """Which matrix column applies for this control's phase / risk level."""
    phase_key = (phase or "").strip().upper()
    if phase_key in PHASE_COLUMNS:
        return PHASE_COLUMNS[phase_key]
    return RISK_COLUMNS.get((risk_level or "").strip().lower())


def calculate_sample_size(
    matrix: dict[str, Any],
    risk_level: str | None,
    frequency: str | None,
    phase: str | None,
) -> str | None:
    """Return the matrix sample size as a string, or None if not derivable.

    Values are returned as strings because the matrix legitimately contains
    ranges (e.g. "2 to 5") alongside plain integers.
    """
    table = _operating_effectiveness_table(matrix)
    if not table:
        return None

    row = _find_row(table, frequency or "")
    if not row:
        return None

    column = resolve_column(risk_level, phase)
    if column is None:
        return None

    value = row.get(column)
    if value is None or value == "":
        return None
    return str(value)


def _sub_sampling_table(matrix: dict[str, Any]) -> dict[str, Any]:
    return (
        matrix.get("Sampling Methodology", {}).get(
            "Sub-sampling according to population range applicable for all rounds", {}
        )
        or {}
    )


def _frequency_band_map(matrix: dict[str, Any]) -> dict[str, Any]:
    return (
        matrix.get("Sampling Methodology", {}).get("Frequency to sub-sampling population band", {})
        or {}
    )


def sub_sampling_size(
    matrix: dict[str, Any],
    risk_level: str | None,
    frequency: str | None,
) -> str | None:
    """Sample size from the sub-sampling table, or None if not derivable.

    Applies to frequencies the Operating Effectiveness table has no row for.
    Which population band such a frequency belongs to is a client judgement,
    so it is declared in the matrix ("Frequency to sub-sampling population
    band") rather than inferred here — e.g. an "Upon Occurrence" control is
    low-volume and is tested against "Less than 20 items".

    The sub-sampling table splits on risk as High vs Low/Medium only, so any
    non-high risk takes the "Low/ Medium" column.
    """
    target = (frequency or "").strip().lower()
    if not target:
        return None

    band = None
    for key, value in _frequency_band_map(matrix).items():
        if key.startswith("_"):
            continue
        if key.strip().lower() == target:
            band = value
            break
    if not band:
        return None

    row = None
    for key, value in _sub_sampling_table(matrix).items():
        if key.strip().lower() == str(band).strip().lower():
            row = value
            break
    if not isinstance(row, dict):
        return None

    column = "High" if (risk_level or "").strip().lower() == "high" else "Low/ Medium"
    value = row.get(column)
    if value is None or value == "":
        return None
    return str(value)


NOTE_KEYS = ("frequency", "risk_level", "phase")


def _normalise_note(raw: Any) -> dict[str, str | None] | None:
    """Accept either a bare string or {"text", "source"} for a note.

    The bare-string form stays supported so notes can be added quickly
    without a source tag.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, str):
        return {"text": raw, "source": None}
    if isinstance(raw, dict):
        text = raw.get("text")
        if not text:
            return None
        source = raw.get("source")
        return {"text": str(text), "source": str(source) if source else None}
    return None


def load_sampling_notes(
    metadata_path: Path, control_number: str, entity_code: str | None
) -> dict[str, dict[str, str | None] | None]:
    """Per-attribute sampling reasoning for one control+entity.

    Records are matched on their own control_number / entity_code fields,
    mirroring how control definitions and testing outputs are matched. Each
    note carries optional `source` provenance (e.g. "RCM") for display.

    Missing file, malformed content, or no matching record all yield empty
    notes — the reasoning is supplementary, never required.
    """
    empty: dict[str, dict[str, str | None] | None] = dict.fromkeys(NOTE_KEYS)
    if not metadata_path.exists():
        return empty
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return empty

    for record in payload.get("controls") or []:
        if str(record.get("control_number", "")).strip() != control_number.strip():
            continue
        record_entity = str(record.get("entity_code", "")).strip()
        if entity_code is not None and record_entity != entity_code.strip():
            continue
        notes = record.get("notes") or {}
        return {key: _normalise_note(notes.get(key)) for key in NOTE_KEYS}
    return empty


def extract_control_parameters(source_json: dict[str, Any]) -> dict[str, Any]:
    """Pull the three sampling inputs (+ JSON fallback) from a control JSON.

    Risk level and frequency live in rcm_details; the control phase and the
    fallback sample size live in control_details.
    """
    details = source_json.get("control_details") or {}
    rcm = source_json.get("rcm_details") or {}
    fallback = details.get("Sample Size")
    return {
        "risk_level": rcm.get("Risk Level"),
        "frequency": rcm.get("Frequency"),
        "phase": details.get("Phase of control"),
        "fallback_sample_size": None if fallback in (None, "") else str(fallback),
    }
