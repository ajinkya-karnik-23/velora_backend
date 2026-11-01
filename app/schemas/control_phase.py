"""Schemas for a control's testing phases (DE, OE, RF, YE and RM rounds)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PhaseRunOut(BaseModel):
    phase_run_id: int
    phase: str
    # The phase the run belongs to — for an RM round, the one it remediates.
    base_phase: str
    label: str
    name: str
    remediates_run_id: int | None = None
    attempt: int
    status: str
    matrix_value: str | None = None
    size_source: str | None = None
    sample_size: int | None = None
    override_size: int | None = None
    override_reason: str | None = None
    override_by_name: str | None = None
    override_time: int | None = None
    # When the tester computed the count on the Controls table; null = not yet.
    size_computed_time: int | None = None
    selected_samples: list[int] = []
    # sample_no (as text) -> latest result: logged run, or the tester's judgement.
    results: dict[str, str] = {}
    failure_reason: str | None = None
    started_time: int
    concluded_time: int | None = None
    concluded_by_name: str | None = None
    window_start: str | None = None
    window_end: str | None = None


class PhaseEventOut(BaseModel):
    phase_run_id: int | None = None
    label: str | None = None
    kind: str
    note: str | None = None
    detail: dict[str, Any] | None = None
    actor_name: str | None = None
    event_time: int


class PhaseSpan(BaseModel):
    start: Any
    end: Any


class ControlPhasesOut(BaseModel):
    config_control_id: int
    control_number: str | None = None
    frequency: str | None = None
    # Fields changed for the demo: {field: {from, to, note}}.
    demo_changes: dict[str, dict[str, Any]] = {}
    risk_level: str | None = None
    path: list[str]
    current_run_id: int | None = None
    current_phase: str | None = None
    in_remediation: bool = False
    complete: bool = False
    # Cleared its phase; the next opens when the whole cycle has cleared it.
    waiting_for: str | None = None
    runs: list[PhaseRunOut] = []
    # Planned slot of each phase within the cycle (epoch seconds).
    planned: dict[str, PhaseSpan] = {}
    # Evidence window of each phase (ISO dates).
    windows: dict[str, PhaseSpan] = {}
    events: list[PhaseEventOut] = []


class CyclePhasesOut(BaseModel):
    cycle_id: int
    period_under_review: PhaseSpan
    # The phase every control is moving through together; None when all done.
    cycle_phase: str | None = None
    controls: list[ControlPhasesOut]


class PhaseSampleSizeIn(BaseModel):
    phase_run_id: int
    size: int = Field(ge=1)
    reason: str = Field(min_length=1)


class PhaseSampleSizeResetIn(BaseModel):
    phase_run_id: int


class PhaseSizeComputedIn(BaseModel):
    phase_run_id: int
    computed: bool = True


class PhaseFailIn(BaseModel):
    reason: str = Field(min_length=1)
