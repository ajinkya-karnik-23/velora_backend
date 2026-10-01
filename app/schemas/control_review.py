"""Review workflow schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ReviewStatus = Literal[
    "submitted_for_review", "under_review", "reviewed", "approved", "returned_to_tester"
]
ReviewerVerdict = Literal["under_review", "reviewed", "approved", "returned_to_tester"]


class ControlReviewStatusOut(BaseModel):
    """Stored review state for one attached control.

    Controls with no row have not been submitted yet; their state is the
    tester-side progress, which the caller derives from the samples.
    """

    config_control_id: int
    status: ReviewStatus
    note: str | None = None
    submitted_by_name: str | None = None
    submitted_time: int | None = None
    reviewed_by_name: str | None = None
    reviewed_time: int | None = None
    updated_time: int


class ControlReviewEventOut(BaseModel):
    config_control_id: int
    from_status: str | None = None
    to_status: str
    note: str | None = None
    actor_name: str | None = None
    actor_persona: str
    event_time: int


class SubmitForReviewRequest(BaseModel):
    note: str | None = None


class SubmitManyRequest(BaseModel):
    config_control_ids: list[int] = Field(default_factory=list)


class SubmitForReviewResult(BaseModel):
    submitted: list[int]
    # Already with the reviewer, so left alone.
    skipped: list[int]


class ReviewVerdictRequest(BaseModel):
    verdict: ReviewerVerdict
    note: str | None = None
