"""Role schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: int
    role_name: str


class RoleAssignment(BaseModel):
    role_ids: list[int]
