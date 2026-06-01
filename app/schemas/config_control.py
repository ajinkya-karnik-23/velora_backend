"""Config control schemas — attaching controls to review cycles."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ConfigControlCreate(BaseModel):
    control_id: int


class ConfigControlBulkCreate(BaseModel):
    control_ids: list[int]


class ConfigControlBulkRemove(BaseModel):
    config_control_ids: list[int]


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
    created_time: int
    updated_time: int
