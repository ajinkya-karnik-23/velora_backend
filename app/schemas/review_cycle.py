"""Review cycle schemas."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ReviewCycleCreate(BaseModel):
    client_id: int
    project_lead: int | None = None
    review_period: str = Field(..., max_length=50)
    name: str = Field(..., max_length=255)
    audit_type: str | None = Field(default=None, max_length=100)
    priority: str | None = Field(default=None, max_length=20)
    framework: str | None = Field(default=None, max_length=100)
    start_date: int
    due_date: int
    overview: str | None = None
    description: str | None = None


class ReviewCycleUpdate(BaseModel):
    project_lead: int | None = None
    review_period: str | None = Field(default=None, max_length=50)
    name: str | None = Field(default=None, max_length=255)
    audit_type: str | None = None
    priority: str | None = None
    framework: str | None = None
    start_date: int | None = None
    due_date: int | None = None
    end_date: int | None = None
    status: str | None = Field(default=None, max_length=50)
    score: Decimal | None = None
    overview: str | None = None
    description: str | None = None


class ReviewCycleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cycle_id: int
    client_id: int
    project_lead: int | None = None
    lead_name: str | None = None
    review_period: str
    name: str
    audit_type: str | None = None
    priority: str | None = None
    framework: str | None = None
    start_date: int
    due_date: int
    end_date: int | None = None
    status: str
    score: Decimal | None = None
    overview: str | None = None
    description: str | None = None
    created_time: int
    updated_time: int


class ReviewCycleFilter(BaseModel):
    client_id: int | None = None
    status: str | None = None


class ReviewCycleStats(BaseModel):
    total_controls: int = 0
    tested_controls: int = 0
    team_members: int = 0
    completion_percentage: float = 0.0
    evidence_count: int = 0
    days_remaining: int = 0
