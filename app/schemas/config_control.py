"""Config control schemas — attaching controls to review cycles."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


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
    # "matrix" when the methodology matrix supplied it, otherwise
    # "control_definition" when it came from the control's own attributes.
    sample_size_source: str | None = None


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
    # Standing of the evidence attached to this sample: "ok", "invalid"
    # (uploaded but does not meet the control's requirement), or "missing".
    # Never says what was expected — only whether the upload satisfies it.
    evidence_status: str = "missing"


class TestMethodology(BaseModel):
    """Sample-population figures shown in step 1 of each sample's log."""

    methodology: str
    total_samples: int
    manual_entries: int
    nr_entries: int


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


class EvidenceCheckOut(BaseModel):
    """Whether a control's uploaded evidence permits test execution.

    Deliberately carries no expected-filename detail — the message is
    generic so internal validation rules cannot leak to the UI.
    """

    ok: bool
    message: str | None = None
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
    status: str | None = None
    test_id: int | None = None
    tests: str | None = None
    note: str | None = None
    comments: str | None = None
    entity_code: str | None = None
    entity_detail_json: dict | None = None
    sample_size: str | None = None
    sample_size_source: str | None = None
    created_time: int
    updated_time: int
