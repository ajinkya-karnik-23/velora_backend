"""Manual test step schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

TestType = Literal[
    "document_value_verification",
    "total_reconciliation",
    "email_verification",
    "approval_check",
    "signature_verification",
    "custom",
]

ParameterDataType = Literal["number", "text", "date", "boolean", "signature", "currency", "custom"]

Verdict = Literal["PASS", "FAIL", "NOT_VALIDATED"]


class StepParameter(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    data_type: ParameterDataType
    # Shape depends on data_type (operator + value for a number, currency code
    # for currency, …). Kept as given; the UI owns its interpretation.
    expected: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Parameter name is required.")
        return v


class StepFields(BaseModel):
    serial: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=255)
    summary: str = Field(..., min_length=1)
    test_type: TestType
    evidence_name: str = Field(..., min_length=1, max_length=255)
    evidence_description: str | None = None
    parameters: list[StepParameter] = Field(default_factory=list)

    @field_validator("serial", "title", "summary", "evidence_name")
    @classmethod
    def _required_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("This field is required.")
        return v


class ManualTestStepCreate(StepFields):
    config_control_id: int
    # Save the step on the control so every cycle testing it picks it up,
    # rather than only this cycle's attached control.
    keep_for_future_cycles: bool = False


class ManualTestStepUpdate(StepFields):
    # Moves a step between cycle scope and control scope. Only meaningful
    # alongside a cycle to scope it back to; see the service.
    keep_for_future_cycles: bool | None = None
    config_control_id: int | None = None


class RecordResultRequest(BaseModel):
    config_control_id: int
    verdict: Verdict
    remark: str | None = None

    @field_validator("remark")
    @classmethod
    def _strip_remark(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class StepResultOut(BaseModel):
    verdict: Verdict
    remark: str | None = None
    evidence_token: str
    recorded_by_name: str | None = None
    recorded_time: int


class ManualTestStepOut(BaseModel):
    step_id: int
    control_id: int
    control_number: str | None = None
    # Set for a cycle step; null for a step kept on the control.
    config_control_id: int | None = None
    scope: Literal["cycle", "control"]
    cycle_id: int | None = None
    cycle_name: str | None = None
    serial: str
    title: str
    summary: str
    test_type: TestType
    evidence_name: str
    evidence_description: str | None = None
    parameters: list[StepParameter]
    created_by_name: str | None = None
    created_time: int
    updated_time: int


class CycleManualStepOut(ManualTestStepOut):
    """A step as it applies to one attached control in a cycle."""

    # The attached control this row is being tested under. For a control-level
    # step this is the cycle's own attachment, not the step's scope.
    applies_to_config_control_id: int
    result: StepResultOut | None = None
