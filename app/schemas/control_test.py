"""Control test schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ControlTestUpdate(BaseModel):
    tests: str | None = None
    note: str | None = None
    comments: str | None = None


class ControlTestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    test_id: int
    config_control_id: int
    tests: str | None = None
    note: str | None = None
    comments: str | None = None
    created_time: int
    updated_time: int


class CycleTestObjectiveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    test_id: int
    config_control_id: int
    control_id: int | None = None
    control_number: str | None = None
    control_name: str | None = None
    domain: str | None = None
    tests: str | None = None
    note: str | None = None
    comments: str | None = None
    created_time: int
    updated_time: int


class TestRunHistoryOut(BaseModel):
    """A single persisted test run, sourced from test_logs."""

    id: int
    test_id: int | None = None
    status: str
    notes: str | None = None
    execution_time_ms: int | None = None
    created_at: datetime


class ClearRunDataResponse(BaseModel):
    """Summary of a cycle run-data clear operation."""

    cycle_id: int
    deleted_test_results: int
    deleted_test_logs: int
