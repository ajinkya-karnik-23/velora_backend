"""Control catalog schemas."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ControlOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    control_id: int
    control_number: str
    version_id: int | None = None
    control_name: str
    reference_number: str | None = None
    entity: str
    control_desc: str
    domain: str | None = None
    status: str
    frequency: str
    risk_level: str
    pwc_reliance: str | None = None
    control_owner: int
    owner_name: str | None = None
    units_fccg_contact: int
    fccg_contact_name: str | None = None
    frameworks: list[str] = []
    created_time: int
    updated_time: int


class ControlFilter(BaseModel):
    domain: str | None = None
    risk_level: str | None = None
    frequency: str | None = None
    framework: str | None = None
    status: str | None = None
    search: str | None = None


class ChangeLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    change_id: int
    control_id: int
    changed_by: int
    changer_name: str | None = None
    from_version: int | None = None
    from_version_name: str | None = None
    to_version: int
    to_version_name: str | None = None
    change_type: str
    change_timestamp: int
    new_control_name: str | None = None
    new_control_desc: str | None = None
    change_percentage: Decimal | None = None
    is_archived: bool
    note: str | None = None
    created_time: int
    updated_time: int
