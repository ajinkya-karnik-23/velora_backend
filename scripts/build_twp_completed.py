"""Build the completed TWP work paper for a control from its client data.

Takes the empty work-paper template and fills it from the control definition,
the sampling determination and the per-sample testing output — producing the
workbook the Controls view serves once every sample has been tested.

Re-run after editing any of the source JSONs:

    poetry run python -m scripts.build_twp_completed IA8.CA02 19A1

Values written into dropdown-validated cells are taken verbatim from the
template's own lookup lists (rows 176-194, the "do not touch these values"
block), so Excel does not flag them as invalid.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from app.core.config import settings
from app.services.control_matching import (
    find_control_json_by_control_and_entity,
    load_control_json,
)
from app.services.evidence_verification import (
    build_methodology,
    expected_filename_for_sample,
    load_filename_rule,
)
from app.services.sampling_matrix import (
    calculate_sample_size,
    extract_control_parameters,
    load_sampling_matrix,
    load_sampling_notes,
)
from app.services.test_output_matching import build_samples, find_test_output
from app.services.twp_templates import load_twp_templates

# The template's own frequency list (B188:B194) — a control's raw frequency is
# mapped onto one of these so the cell stays valid.
FREQUENCY_CHOICES = [
    "Annual",
    "Bi-annual",
    "Quarterly",
    "Monthly",
    "Weekly",
    "Daily",
    "Multiple times per day",
]

RESULT_OK = "OK"
RESULT_NOT_OK = "Not OK"
RESULT_NA = "N/A"

TEST_RESULT_EFFECTIVE = "EFFECTIVE - Test executed without exception(s)"
TEST_RESULT_INEFFECTIVE = "INEFFECTIVE - Test executed with exception(s)"

# The per-sample results band. Every row here carries a validated result cell
# (E118:E143 plus E144), giving exactly 27 rows.
RESULTS_FIRST_ROW = 118
RESULTS_LAST_ROW = 144


def _set(ws: Worksheet, coord: str, value: Any) -> None:
    """Write a value, redirecting to the anchor when the cell is merged."""
    for rng in ws.merged_cells.ranges:
        if coord in rng:
            ws.cell(row=rng.min_row, column=rng.min_col).value = value
            return
    ws[coord] = value


def _map_frequency(raw: str | None) -> str:
    """Fit a control's frequency onto the template's allowed list."""
    text = (raw or "").strip().lower()
    for choice in FREQUENCY_CHOICES:
        if choice.lower() == text:
            return choice
    # "Upon Occurrence" and similar have no slot in the list; the closest
    # honest reading of an event-driven control is its highest cadence.
    return "Multiple times per day" if text else ""


# Parameters that best identify a journal-entry sample. Controls describing
# their samples differently fall back to whatever they do carry.
PREFERRED_LABELS = ("Posting date", "Amount in local cur.", "Type")

# Long narrative fields are never useful as a row label.
LABEL_MAX_LEN = 60


def _sample_label(sample: dict) -> str:
    """One results-row description: sample number, document, key parameters."""
    parts = [f"Sample {sample.get('sample_no')}"]
    if sample.get("document_no"):
        parts.append(f"Doc {sample['document_no']}")

    params = sample.get("parameters") or []
    chosen = [p for p in params if p.get("label") in PREFERRED_LABELS]
    if not chosen:
        # This control names its samples some other way (a customer, a month).
        # Take the first few short parameters so the row still identifies
        # itself instead of reading "Sample 1" with nothing else.
        chosen = [
            p
            for p in params
            if p.get("value") not in (None, "") and len(str(p.get("value"))) <= LABEL_MAX_LEN
        ][:3]

    for param in chosen:
        value = param.get("value")
        if value not in (None, ""):
            parts.append(f"{param['label']}: {value}")
    return " | ".join(parts)


def _sample_fields(sample: dict) -> dict:
    """Flatten a normalised sample back to field -> value, as the filename
    rule is written against the client's own field names."""
    fields = {k: v for k, v in sample.items() if k != "parameters"}
    for param in sample.get("parameters") or []:
        label = param.get("label")
        if label:
            fields[label] = param.get("value")
    return fields


def _population_split(methodology: dict) -> str:
    """How the tested population divides, phrased for the conclusion line.

    Controls using the journal-entry methodology keep their original wording;
    any control declaring its own categories is described by those instead.
    """
    if methodology.get("manual_entries") is not None:
        return f"{methodology['manual_entries']} manual, {methodology['nr_entries']} NR"
    lines = methodology.get("breakdown") or []
    return ", ".join(f"{line['value']} {line['label'].lower()}" for line in lines)


def build(control_number: str, entity_code: str) -> Path:
    templates = load_twp_templates(
        Path(settings.TWP_TEMPLATE_MAP_PATH), control_number, entity_code
    )
    source = Path(templates.empty or settings.TWP_TEMPLATE_PATH)
    # Unmapped controls land beside the template they were built from, inside
    # whichever client-data folder is configured.
    target = Path(
        templates.completed
        or Path(settings.TWP_TEMPLATE_PATH).parent
        / f"{control_number}.{entity_code}.TWP.Completed.xlsm"
    )
    if not source.exists():
        raise SystemExit(f"Empty template not found: {source}")

    control_path = find_control_json_by_control_and_entity(
        Path(settings.CONTROL_JSONS_PATH), control_number, entity_code
    )
    if control_path is None:
        raise SystemExit(f"No control JSON for {control_number}.{entity_code}")
    rcm = load_control_json(control_path).get("rcm_details") or {}

    payload = find_test_output(Path(settings.TEST_OUTPUTS_PATH), control_number, entity_code)
    samples = build_samples(payload) if payload else []
    methodology = build_methodology(samples, (payload or {}).get("control_test_output"))

    params = extract_control_parameters({"rcm_details": rcm})
    matrix = load_sampling_matrix(Path(settings.SAMPLING_MATRIX_PATH))
    sample_size = calculate_sample_size(
        matrix,
        risk_level=params["risk_level"],
        frequency=params["frequency"],
        phase=params["phase"],
    ) or str(len(samples))
    notes = load_sampling_notes(Path(settings.SAMPLING_METADATA_PATH), control_number, entity_code)

    exceptions = [s for s in samples if (s.get("result") or "").upper() not in ("PASS", "PASSED")]

    wb = openpyxl.load_workbook(source, keep_vba=True)
    ws = wb["Template"]

    # ── Work paper preparation ────────────────────────────────────────────
    _set(ws, "D5", rcm.get("Entity Name") or entity_code)
    _set(ws, "D7", control_number)
    _set(ws, "D9", rcm.get("Title"))
    _set(ws, "D11", f"TWP-{control_number}.{entity_code}")
    _set(ws, "D13", rcm.get("Description"))
    _set(ws, "D15", "Yes" if str(rcm.get("IPE Name of Report")).strip().lower() == "yes" else "No")
    _set(ws, "D17", "Validated through Usage")

    # ── Test plan ─────────────────────────────────────────────────────────
    _set(ws, "D22", len(samples) or sample_size)
    _set(ws, "F22", (notes.get("frequency") or {}).get("text") if notes.get("frequency") else None)
    _set(ws, "H24", (params["risk_level"] or "").upper() or None)
    _set(ws, "D28", _map_frequency(params["frequency"]))
    _set(ws, "D30", rcm.get("Effective Date"))
    _set(ws, "D32", rcm.get("Control Type") or "Manual")
    _set(ws, "D34", rcm.get("Control Objective"))

    # ── Test execution ────────────────────────────────────────────────────
    _set(ws, "D114", rcm.get("Control Owner"))

    # Rows are never inserted here: openpyxl shifts cell values but leaves
    # merged ranges where they are, which would silently desynchronise every
    # label below the band from its value. Overflow is refused instead, so the
    # template gets extended deliberately rather than producing a broken
    # workbook.
    capacity = RESULTS_LAST_ROW - RESULTS_FIRST_ROW + 1
    if len(samples) > capacity:
        raise SystemExit(
            f"{len(samples)} samples exceed the template's {capacity}-row results "
            f"band (rows {RESULTS_FIRST_ROW}-{RESULTS_LAST_ROW}). Extend the band "
            "in the template — copying the result-cell validation down — then "
            "update RESULTS_LAST_ROW."
        )

    for offset, sample in enumerate(samples):
        row = RESULTS_FIRST_ROW + offset
        passed = (sample.get("result") or "").upper() in ("PASS", "PASSED")
        _set(ws, f"D{row}", _sample_label(sample))
        _set(ws, f"E{row}", RESULT_OK if passed else RESULT_NOT_OK)
        _set(ws, f"F{row}", None if passed else sample.get("validation"))

    # Conclusion block. Fixed positions: the band is never resized, so these
    # sit exactly where the template puts them. The summary caption lives in
    # column D with its value beneath; the rest are captioned in column B with
    # the value in D on the same row.
    summary_label = 146
    _set(
        ws,
        f"D{summary_label + 1}",
        f"{methodology['methodology']}: {methodology['total_samples']} samples tested "
        f"({_population_split(methodology)}). "
        f"{len(samples) - len(exceptions)} passed, {len(exceptions)} exception(s).",
    )
    _set(ws, f"D{summary_label + 4}", len(exceptions))
    if exceptions:
        _set(
            ws,
            f"D{summary_label + 6}",
            "Journal entries flagged NR could not be validated against the "
            "supporting documentation provided.",
        )
    _set(ws, f"D{summary_label + 8}", RESULT_OK if not exceptions else RESULT_NOT_OK)
    _set(
        ws,
        f"D{summary_label + 10}",
        TEST_RESULT_EFFECTIVE if not exceptions else TEST_RESULT_INEFFECTIVE,
    )

    # Evidence collected — the work paper records what the test was run against.
    # A control either names one file for every sample, or one per sample
    # derived from that sample's own data; both are recorded here.
    rule = load_filename_rule(
        Path(settings.EVIDENCE_FILENAME_MAP_PATH), control_number, entity_code
    )
    fixed = expected_filename_for_sample(rule, None) if rule else None
    if fixed:
        _set(ws, f"D{summary_label + 13}", fixed)
        _set(
            ws,
            f"E{summary_label + 13}",
            f"Test of effectiveness evidence supporting all {len(samples)} samples.",
        )
    elif rule:
        per_sample = [
            expected_filename_for_sample(rule, _sample_fields(sample)) for sample in samples
        ]
        named = [name for name in per_sample if name]
        if named:
            _set(ws, f"D{summary_label + 13}", ", ".join(named))
            _set(
                ws,
                f"E{summary_label + 13}",
                f"One evidence file per sample, {len(named)} in total.",
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    wb.save(target)
    return target


def main() -> None:
    control_number = sys.argv[1] if len(sys.argv) > 1 else "IA8.CA02"
    entity_code = sys.argv[2] if len(sys.argv) > 2 else "19A1"
    out = build(control_number, entity_code)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
