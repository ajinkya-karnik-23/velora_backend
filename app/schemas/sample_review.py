"""Schemas for the reviewer's word on a tested sample, and the notifications
the tester receives about reviewer actions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ReviewedResult = Literal["PASS", "FAIL", "NOT_VALIDATED"]
SampleVerdict = Literal["under_review", "reviewed", "approved", "returned_to_tester"]


class Involved(BaseModel):
    name: str
    email: str | None = None


class SampleReviewIn(BaseModel):
    """Any subset: an edit (result / conclusion), a comment, people involved,
    and — usually right after an edit — the verdict."""

    result: ReviewedResult | None = None
    conclusion: str | None = Field(default=None, max_length=4000)
    comment: str | None = Field(default=None, max_length=4000)
    involved: list[Involved] | None = None
    verdict: SampleVerdict | None = None


class SampleReviewOut(BaseModel):
    config_control_id: int
    sample_no: int
    result: str | None = None
    conclusion: str | None = None
    comment: str | None = None
    involved: list[Involved] = []
    verdict: str | None = None
    verdict_time: int | None = None
    reviewed_by_name: str | None = None
    updated_time: int


class SampleReviewEventOut(BaseModel):
    config_control_id: int
    sample_no: int
    kind: str
    detail: dict | None = None
    note: str | None = None
    actor_name: str | None = None
    event_time: int


class NotificationOut(BaseModel):
    """A review action that concerns the tester or the reviewer."""

    key: str
    cycle_id: int
    cycle_name: str
    config_control_id: int
    control_number: str | None = None
    control_name: str | None = None
    # None for a control-level verdict.
    sample_no: int | None = None
    # control_verdict | sample_verdict | edited | commented | involved — for the
    # tester; submitted — a hand-over, for the reviewer.
    kind: str
    status: str | None = None
    note: str | None = None
    actor_name: str | None = None
    event_time: int
