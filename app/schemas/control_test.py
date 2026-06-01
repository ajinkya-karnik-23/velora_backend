"""Control test schemas."""

from __future__ import annotations

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
