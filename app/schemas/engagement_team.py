"""Engagement team schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TeamMemberAdd(BaseModel):
    user_id: int
    team_role: str = Field(..., max_length=50)


class TeamMemberBulkAdd(BaseModel):
    members: list[TeamMemberAdd]


class TeamMemberUpdate(BaseModel):
    team_role: str = Field(..., max_length=50)


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    user_name: str
    email: str
    profile_picture: str | None = None
    job_title: str | None = None
    team_role: str
    role_name: str | None = None
