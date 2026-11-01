"""The cycle moves in step: what each control still has to clear."""

from __future__ import annotations

from types import SimpleNamespace

from app.core.phase_rules import CYCLE_ORDER
from app.services.phase_service import first_needed


def run(run_id: int, phase: str, status: str, remediates: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(phase_run_id=run_id, phase=phase, status=status, remediates_run_id=remediates)


def test_first_needed_walks_the_path() -> None:
    path = ["DE", "OE", "RF"]
    assert first_needed(path, [run(1, "DE", "active")]) == "DE"
    assert first_needed(path, [run(1, "DE", "approved")]) == "OE"
    assert first_needed(path, [run(1, "DE", "approved"), run(2, "OE", "approved"), run(3, "RF", "approved")]) is None


def test_a_remediated_phase_clears_once_its_round_is_approved() -> None:
    path = ["DE", "OE", "RF"]
    assert first_needed(path, [run(1, "DE", "failed"), run(2, "RM", "active", 1)]) == "DE"
    assert first_needed(path, [run(1, "DE", "failed"), run(2, "RM", "approved", 1)]) == "OE"


def test_the_cycle_is_in_the_earliest_phase_any_control_needs() -> None:
    needed = ["RF", "DE", "OE"]
    assert min(needed, key=CYCLE_ORDER.index) == "DE"
    # An annual control waiting for YE never holds the others back.
    assert min(["YE", "OE"], key=CYCLE_ORDER.index) == "OE"
