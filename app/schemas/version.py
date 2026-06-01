"""Version schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VersionCreate(BaseModel):
    version_name: str | None = Field(default=None, max_length=255)
    released_at: int | None = None
    is_current: bool = False
    description: str | None = None


class VersionUpdate(BaseModel):
    version_name: str | None = Field(default=None, max_length=255)
    released_at: int | None = None
    is_current: bool | None = None
    description: str | None = None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_id: int
    version_name: str | None = None
    released_at: int | None = None
    is_current: bool
    description: str | None = None
    created_time: int
    updated_time: int
