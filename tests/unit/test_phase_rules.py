"""Testing phases: path, sizing per phase, evidence windows and sample dates."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.core.phase_rules import (
    DE_SAMPLE_SIZE,
    EVIDENCE_WINDOWS,
    phase_path,
    planned_window,
)
from app.services.matrix_sampling import matrix_size
from app.services.phase_demo import apply_overlay, sample_date
from app.services.phase_service import base_phase, effective_size, run_label

MATRIX = {
    "Sampling Methodology": {
        "Operating Effectiveness Testing": {
            "Monthly": {
                "Risk Rating conclusion Low": None,
                "Risk Rating Conclusion Medium": "2 to 5",
                "RF (Full test)": 1,
                "RM": 2,
                "YE": None,
            },
            "Annual": {"RM": 1, "YE": 1},
        },
        "Sub-sampling according to population range applicable for all rounds": {
            "Less than 20 items": {"Low/ Medium": 2, "High": 5},
        },
        "Frequency to sub-sampling population band": {"Upon Occurrence": "Less than 20 items"},
    }
}


def run(phase, **kw):
    defaults = dict(
        phase_run_id=1, remediates_run_id=None, attempt=1, override_size=None, matrix_value=None
    )
    return SimpleNamespace(phase=phase, **{**defaults, **kw})


def test_annual_controls_add_year_end_after_rf():
    assert phase_path("Annual") == ["DE", "OE", "RF", "YE"]
    assert phase_path("Monthly") == ["DE", "OE", "RF"]
    assert phase_path("Upon Occurrence") == ["DE", "OE", "RF"]


def test_de_is_always_one_sample_whatever_the_override():
    assert effective_size(run("DE", override_size=7, matrix_value="5")) == DE_SAMPLE_SIZE == 1


def test_oe_uses_risk_and_the_rounds_use_frequency_only():
    monthly = {"frequency": "Monthly", "risk_level": "Medium"}
    assert matrix_size(MATRIX, {**monthly, "phase": "OE"}) == ("2 to 5", "matrix")
    assert matrix_size(MATRIX, {**monthly, "phase": "RF"}) == ("1", "matrix")
    assert matrix_size(MATRIX, {**monthly, "phase": "RM"}) == ("2", "matrix")
    # Risk does not change a remediation round's size.
    assert matrix_size(MATRIX, {**monthly, "risk_level": "Low", "phase": "RM"}) == ("2", "matrix")


def test_upon_occurrence_uses_the_population_band_in_every_round():
    params = {"frequency": "Upon Occurrence", "risk_level": "Low"}
    for phase in ("OE", "RF", "RM"):
        assert matrix_size(MATRIX, {**params, "phase": phase}) == ("2", "sub_sampling")


def test_missing_matrix_value_leaves_the_size_to_the_tester():
    assert matrix_size(MATRIX, {"frequency": "Monthly", "risk_level": "Low", "phase": "OE"}) == (
        None,
        None,
    )
    assert effective_size(run("OE", matrix_value=None)) is None
    assert effective_size(run("OE", matrix_value=None, override_size=4)) == 4
    assert effective_size(run("OE", matrix_value="2 to 5")) == 5


def test_remediation_rounds_belong_to_the_phase_they_remediate():
    oe = run("OE", phase_run_id=10)
    rm = run("RM", phase_run_id=11, remediates_run_id=10, attempt=2)
    runs = {10: oe, 11: rm}
    assert base_phase(rm, runs) == "OE"
    assert run_label(rm, runs) == "RM 2 · OE"
    assert run_label(oe, runs) == "OE"


def test_evidence_windows_follow_the_phase_order():
    assert EVIDENCE_WINDOWS["DE"][1] < EVIDENCE_WINDOWS["OE"][0]
    assert EVIDENCE_WINDOWS["OE"][1] < EVIDENCE_WINDOWS["RF"][0]


def test_planned_slots_follow_the_testing_calendar():
    start = int(datetime(2026, 5, 1, tzinfo=UTC).timestamp())
    due = int(datetime(2027, 1, 31, tzinfo=UTC).timestamp())

    def day(t: int) -> date:
        return datetime.fromtimestamp(t, tz=UTC).date()

    slots = {p: planned_window(p, start, due) for p in ("DE", "OE", "RF", "YE")}
    assert [(day(a), day(b)) for a, b in slots.values()] == [
        (date(2026, 5, 1), date(2026, 5, 31)),
        (date(2026, 9, 1), date(2026, 10, 31)),
        (date(2026, 12, 1), date(2026, 12, 31)),
        (date(2027, 1, 1), date(2027, 1, 31)),
    ]


def test_sample_dates_read_from_whichever_field_the_control_uses():
    assert sample_date({"Posting date": "2025-01-10"}) == date(2025, 1, 10)
    assert sample_date({"parameters": [{"label": "Date of change", "value": "2025-03-04"}]}) == date(
        2025, 3, 4
    )
    assert sample_date({"Month": "Apr-25"}) == date(2025, 4, 1)
    assert sample_date({"Sales order No": "B1"}) is None


def test_overlay_changes_a_copy_only():
    payload = {"test_details": {"5": {"sample_no": 5, "result": "PASS"}}}
    scenario = {"samples": {"5": {"result": "FAIL"}}}
    import app.services.phase_demo as demo

    original = demo.scenario_for
    demo.scenario_for = lambda *_: scenario
    try:
        out = apply_overlay(payload, "IA4.CA14", "19A1")
    finally:
        demo.scenario_for = original
    assert out["test_details"]["5"]["result"] == "FAIL"
    assert payload["test_details"]["5"]["result"] == "PASS"
