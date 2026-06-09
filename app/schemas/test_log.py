"""Test log schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TestLogCreate(BaseModel):
    test_id: int | None = None
    control_id: int | None = None
    cycle_id: int | None = None
    log_date: int | None = None
    status: str = Field(..., max_length=50)
    execution_time_seconds: int | None = None
    report_link: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    @model_validator(mode="after")
    def _at_least_one_linkage(self) -> "TestLogCreate":
        if self.test_id is None and self.control_id is None and self.cycle_id is None:
            raise ValueError(
                "At least one of test_id, control_id, cycle_id must be provided."
            )
        return self


class TestLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_id: int
    test_id: int | None = None
    control_id: int | None = None
    control_number: str | None = None
    control_name: str | None = None
    cycle_id: int | None = None
    cycle_name: str | None = None
    log_date: int
    changed_by: int
    tested_by: str | None = None
    status: str
    execution_time_seconds: int | None = None
    report_link: str | None = None
    notes: str | None = None
    created_time: int
    updated_time: int
