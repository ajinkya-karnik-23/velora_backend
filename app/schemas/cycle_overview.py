"""Per-cycle summary for the Review Cycles screen."""

from __future__ import annotations

from pydantic import BaseModel


class ControlResultOut(BaseModel):
    """One control's testing results as recorded in the audit trail."""

    config_control_id: int
    control_number: str | None = None
    control_name: str | None = None
    samples: int = 0
    executed: int = 0
    passed: int = 0
    # Failed samples, plus samples whose evidence did not meet the requirement.
    exceptions: int = 0
    # Executed but not concluded on (not validated, or the tool could not tell).
    not_concluded: int = 0
    not_tested_reason: str | None = None
    untested_types: int = 0
    review_status: str | None = None


class PersonOut(BaseModel):
    name: str
    role: str | None = None
    email: str | None = None
    title: str | None = None
    organisation: str | None = None
    location: str | None = None


class StakeholderOut(PersonOut):
    """A client-side person named in the cycle's control definitions."""

    # What they are for these controls (business process owner, control owner…).
    roles: list[str] = []
    controls: list[str] = []


class TesterOut(BaseModel):
    name: str
    # Samples this tester executed in the cycle.
    runs: int = 0


class ActivityDayOut(BaseModel):
    date: str  # ISO date, YYYY-MM-DD
    runs: int


class ControlProfileOut(BaseModel):
    """What kind of controls the cycle covers, as counts."""

    process: dict[str, int] = {}
    nature: dict[str, int] = {}
    risk: dict[str, int] = {}
    frequency: dict[str, int] = {}
    key_controls: int = 0
    ipe_controls: int = 0


class CycleOverviewOut(BaseModel):
    cycle_id: int
    controls: int = 0
    controls_not_tested: int = 0
    sample_types_not_tested: int = 0
    samples: int = 0
    executed: int = 0
    passed: int = 0
    exceptions: int = 0
    not_concluded: int = 0
    approved: int = 0
    with_reviewer: int = 0
    evidence_files: int = 0
    team_members: int = 0
    last_run_time: int | None = None
    # Root-cause category label -> failed samples carrying it.
    root_causes: dict[str, int] = {}
    control_results: list[ControlResultOut] = []
    # Controls with at least one sample executed.
    controls_tested: int = 0
    # Sample runs recorded (a re-run counts again).
    tests_run: int = 0
    # Full population behind the samples in scope (matrix cycles select from it).
    population: int = 0
    profile: ControlProfileOut = ControlProfileOut()
    team: list[PersonOut] = []
    # Testers by samples executed, primary first.
    testers: list[TesterOut] = []
    reviewer: str | None = None
    lead: str | None = None
    lead_contact: PersonOut | None = None
    reviewer_contact: PersonOut | None = None
    stakeholders: list[StakeholderOut] = []
    # Hand-over to the reviewer: controls submitted (any state past the
    # tester, approved included), sent back, and when it last happened.
    submitted: int = 0
    returned: int = 0
    last_submitted_time: int | None = None
    last_reviewed_time: int | None = None
    activity: list[ActivityDayOut] = []
    # True when team/testers/activity come from the demo activity file.
    demo_activity: bool = False
