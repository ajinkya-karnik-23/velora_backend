"""Config control schemas — attaching controls to review cycles."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.sample_judgement import SampleJudgementOut  # noqa: TC001 — pydantic field
from app.schemas.sample_review import SampleReviewOut  # noqa: TC001 — pydantic field


class ConfigControlCreate(BaseModel):
    control_id: int


class ConfigControlBulkCreate(BaseModel):
    control_ids: list[int]


class ConfigControlBulkRemove(BaseModel):
    config_control_ids: list[int]


class AttributeNote(BaseModel):
    """Reasoning for one control attribute, with optional provenance tag."""

    text: str
    source: str | None = None


class SampleSizeResultOut(BaseModel):
    """Outcome of a sample-size determination, with the attributes it used."""

    config_control_id: int
    control_number: str | None = None
    entity_code: str | None = None
    # Control attributes the determination was based on.
    frequency: str | None = None
    risk_level: str | None = None
    phase: str | None = None
    # Optional per-attribute reasoning shown beneath each attribute.
    frequency_note: AttributeNote | None = None
    risk_level_note: AttributeNote | None = None
    phase_note: AttributeNote | None = None
    # Resolved size; text because the methodology contains ranges ("2 to 5").
    sample_size: str | None = None
    # "matrix" (Operating Effectiveness table), "sub_sampling" (population-band
    # table, for frequencies the first has no row for), or "control_definition"
    # when neither applied and the control's own attributes supplied it.
    sample_size_source: str | None = None
    # The sample size stated on the control definition itself, shown alongside
    # the methodology result so the two can be compared. Populated whenever the
    # definition carries one, including when it is also the resolved size.
    override_sample_size: str | None = None
    # Matrix-sampled cycles: how many samples were selected from how many
    # available, or why the control could not be tested.
    selected_count: int | None = None
    population_count: int | None = None
    not_tested_reason: str | None = None
    # Phased cycles: the phase run this size is for, its matrix cell, any
    # override, and whether it is still waiting for the tester to give a size.
    phase_info: PhaseInfo | None = None


class SampleParameter(BaseModel):
    label: str
    value: Any = None


class TestSampleOut(BaseModel):
    """One sample row on the Testing page, from the control's testing output."""

    sample_no: Any = None
    document_no: str | None = None
    parameters: list[SampleParameter] = []
    result: str | None = None
    validation: str | None = None
    pages: list[int] = []
    # Evidence files this sample was validated against, when the control's
    # testing output records them. Empty for controls that do not.
    evidences_used: list[str] = []
    # A field's value before the demo calendar moved its date; the evidence
    # filename rule reads these, as the files keep their real names.
    source_fields: dict[str, Any] = {}
    # Standing of the evidence attached to this sample: "ok", "invalid"
    # (uploaded but does not meet the control's requirement), or "missing".
    # Never says what was expected — only whether the upload satisfies it.
    evidence_status: str = "missing"
    # The tester's judgement on the tool's `result`, when one is recorded.
    # `result` itself always stays the tool's.
    judgement: SampleJudgementOut | None = None
    # The reviewer's word on the sample; its `result`, when set, is the effective one.
    review: SampleReviewOut | None = None


class MethodologyLine(BaseModel):
    """One counted category in the sample-population breakdown."""

    label: str
    value: int


class TestMethodology(BaseModel):
    """Sample-population figures shown in step 1 of each sample's log."""

    methodology: str
    total_samples: int
    # How the population splits, as this control counts it. Categories differ
    # per control (journal-entry types for one, amendments vs reviews for
    # another), so they are carried as labelled lines rather than fixed fields.
    breakdown: list[MethodologyLine] = []
    # Original fixed fields, kept so existing controls and callers are
    # unaffected. Populated only for the journal-entry methodology.
    manual_entries: int | None = None
    nr_entries: int | None = None


class UntestedType(BaseModel):
    """A sample type with no sample selected, reported as not tested."""

    label: str
    available: int
    reason: str


class PhaseInfo(BaseModel):
    """The phase run a phased cycle's testing output belongs to."""

    phase_run_id: int
    phase: str
    base_phase: str
    label: str
    name: str
    attempt: int = 1
    status: str
    sample_size: int | None = None
    matrix_value: str | None = None
    size_source: str | None = None
    override_size: int | None = None
    override_reason: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    # True when the matrix gave no size and the tester has not entered one.
    awaiting_size: bool = False
    failure_reason: str | None = None


class ControlTestOutputOut(BaseModel):
    # Set when the output is returned as part of a cycle-wide listing, so the
    # caller can key each output back to the attached control it came from.
    config_control_id: int | None = None
    control_number: str | None = None
    entity_code: str | None = None
    phase_of_control: str | None = None
    summary: str | None = None
    ipe_name: str | None = None
    test_id: int | None = None
    methodology: TestMethodology | None = None
    samples: list[TestSampleOut] = []
    # Size of the full testing population when only a selection of it is
    # tested (matrix-sampled cycles); null when every sample is shown.
    population_count: int | None = None
    not_tested_reason: str | None = None
    untested_types: list[UntestedType] = []
    phase: PhaseInfo | None = None


class SamplingTypeLine(BaseModel):
    label: str
    available: int
    selected: int


class SamplingCheckRow(BaseModel):
    """One control's sampling, checked against the population it has."""

    config_control_id: int
    control_number: str | None = None
    control_name: str | None = None
    frequency: str | None = None
    risk_level: str | None = None
    phase: str | None = None
    # The matrix cell as written ("2 to 5") and the count actually used.
    matrix_value: str | None = None
    sample_size_source: str | None = None
    required: int | None = None
    available: int = 0
    selected: int = 0
    types: list[SamplingTypeLine] = []
    # "ok" | "partial" (a sample type got no sample) | "shortfall" (population
    # smaller than the matrix asks for) | "not_tested"
    status: str
    message: str | None = None
    # How the size was derived — the matrix cells read, in order — and which
    # samples were chosen, for the Controls table's derivation log.
    oe_row: str | None = None
    oe_column: str | None = None
    oe_value: str | None = None
    population_band: str | None = None
    sub_row: str | None = None
    sub_column: str | None = None
    sub_value: str | None = None
    notes: dict[str, str] = {}
    selected_samples: list[int] = []
    # The size stated on the control definition (used by full-population cycles
    # only as a reference).
    stated_size: str | None = None


class SamplingCheckOut(BaseModel):
    cycle_id: int
    sampling_mode: str
    controls: list[SamplingCheckRow] = []


class EvidenceCheckOut(BaseModel):
    """Whether a control's uploaded evidence permits test execution.

    Deliberately carries no expected-filename detail — the message is
    generic so internal validation rules cannot leak to the UI.
    """

    ok: bool
    message: str | None = None
    # Why the check did not pass: "no_evidence" (nothing uploaded yet — the
    # normal starting state) or "mismatch" (uploaded, but it does not satisfy
    # the control). Lets the UI tell an empty control apart from a failing one
    # without exposing what was expected.
    reason: str | None = None
    # Sample rows whose own attached evidence does not satisfy the control's
    # requirement. Carries sample numbers only — never what was expected.
    invalid_samples: list[int] = []


class ConfigControlOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    config_control_id: int
    cycle_id: int
    control_id: int
    control_number: str | None = None
    control_name: str | None = None
    domain: str | None = None
    risk_level: str | None = None
    frequency: str | None = None
    # Fields changed for the demo: {field: {from, to, note}}.
    demo_changes: dict[str, dict[str, Any]] = {}
    # The control's owner (a demo owner where configured).
    owner_name: str | None = None
    owner_role: str | None = None
    status: str | None = None
    test_id: int | None = None
    tests: str | None = None
    note: str | None = None
    comments: str | None = None
    entity_code: str | None = None
    entity_detail_json: dict | None = None
    sample_size: str | None = None
    sample_size_source: str | None = None
    # The size stated on the control definition itself. The Controls table
    # shows this in preference to the methodology result, which stays
    # available (with both values) in the determination modal.
    override_sample_size: str | None = None
    # Audit-style testing scope from the control JSON's control_details
    # ("scope_summary"). Read from the client's current JSON, so edits to it
    # show without re-attaching the control.
    scope_summary: str | None = None
    # Matrix-sampled cycles: the sample numbers selected for testing (null when
    # every sample in the output is tested).
    selected_samples: list[int] | None = None
    # Why the control is not tested (no population, or no matrix size).
    not_tested_reason: str | None = None
    # Sample types left without a sample by the matrix split, with the reason.
    untested_types: list[UntestedType] | None = None
    testing_started_time: int | None = None
    testing_started_by_name: str | None = None
    created_time: int
    updated_time: int


class DefaultEvidenceFileOut(BaseModel):
    sample_no: int
    file_name: str


class DefaultEvidenceStatusOut(BaseModel):
    """Default evidence for one attached control, as its Testing card shows it."""

    # Whether this control has default evidence configured at all.
    configured: bool
    # Files mapped across all samples.
    planned: int
    # Mapped files not yet attached that can be attached now.
    missing: int
    # Mapped files absent from the evidence folder.
    unavailable: int
    # The files still to attach, in sample order, so the UI can attach them
    # one at a time.
    missing_files: list[DefaultEvidenceFileOut] = []


class DefaultEvidenceAttachOut(DefaultEvidenceStatusOut):
    attached: int

SampleSizeResultOut.model_rebuild()
