"""Schemas for tester judgements on tool-generated sample results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

JudgedResult = Literal["PASS", "FAIL", "NOT_VALIDATED"]
RootCauseCategory = Literal[
    "not_executed_as_designed",
    "performed_with_delays",
    "ipe_related",
    "lack_of_control_activity",
    "lack_of_control_evidence",
]


class SampleJudgementIn(BaseModel):
    """The tester's judgement: accept the tool's result or change it.

    A failure needs a root-cause category, and changing the tool's result
    needs a conclusion saying why — the reviewer reads both.
    """

    result: JudgedResult
    conclusion: str | None = Field(default=None, max_length=4000)
    root_cause_category: RootCauseCategory | None = None
    root_cause_note: str | None = Field(default=None, max_length=4000)


class SampleJudgementOut(BaseModel):
    config_control_id: int
    sample_no: int
    tool_result: str | None = None
    result: str
    # "accepted" — the tool's result confirmed; "modified" — changed by the tester.
    action: str
    conclusion: str | None = None
    root_cause_category: str | None = None
    root_cause_label: str | None = None
    root_cause_note: str | None = None
    judged_by_name: str | None = None
    judged_time: int
