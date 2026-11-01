"""Tester judgements on tool-generated sample results.

The testing output is the tool's record and is never modified. A tester
reviewing a sample either accepts the tool's result or changes it; the
judgement is stored beside the output and every change is written to the
audit trail (test_logs, source "judgement").
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, ForbiddenException, NotFoundException
from app.models.config_control import ConfigControl
from app.models.sample_judgement import ROOT_CAUSE_CATEGORIES, SampleJudgement
from app.models.test_log import TestLog
from app.schemas.sample_judgement import SampleJudgementIn, SampleJudgementOut

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

PASS_RESULTS = {"PASS", "PASSED"}
FAIL_RESULTS = {"FAIL", "FAILED"}


def normalise_result(raw: str | None) -> str:
    value = (raw or "").strip().upper()
    if value in PASS_RESULTS:
        return "PASS"
    if value in FAIL_RESULTS:
        return "FAIL"
    return value or "NOT_VALIDATED"


def to_out(row: SampleJudgement) -> SampleJudgementOut:
    return SampleJudgementOut(
        config_control_id=row.config_control_id,
        sample_no=row.sample_no,
        tool_result=row.tool_result,
        result=row.result,
        action=row.action,
        conclusion=row.conclusion,
        root_cause_category=row.root_cause_category,
        root_cause_label=ROOT_CAUSE_CATEGORIES.get(row.root_cause_category or ""),
        root_cause_note=row.root_cause_note,
        judged_by_name=row.judge.user_name if row.judge else None,
        judged_time=row.updated_time,
    )


class SampleJudgementService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _config_control(
        self, cycle_id: int, config_control_id: int, current_user: dict[str, Any]
    ) -> ConfigControl:
        cc = await self.db.get(ConfigControl, config_control_id)
        if cc is None or cc.cycle_id != cycle_id:
            raise NotFoundException("Attached control not found in this cycle.")
        roles = current_user.get("roles", [])
        if not any(r in ("Admin", "Moderator") for r in roles):
            from app.repositories.engagement_team_repo import EngagementTeamRepo

            if not await EngagementTeamRepo(self.db).is_member(
                cycle_id, int(current_user["sub"])
            ):
                raise ForbiddenException("Not a member of this engagement.")
        return cc

    async def _row(self, config_control_id: int, sample_no: int) -> SampleJudgement | None:
        return (
            await self.db.execute(
                select(SampleJudgement)
                .where(
                    SampleJudgement.config_control_id == config_control_id,
                    SampleJudgement.sample_no == sample_no,
                )
                .options(selectinload(SampleJudgement.judge))
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    async def for_control(self, config_control_id: int) -> dict[int, SampleJudgementOut]:
        rows = (
            await self.db.execute(
                select(SampleJudgement)
                .where(SampleJudgement.config_control_id == config_control_id)
                .options(selectinload(SampleJudgement.judge))
            )
        ).scalars()
        return {row.sample_no: to_out(row) for row in rows}

    async def list_for_cycle(self, cycle_id: int) -> list[SampleJudgementOut]:
        cc_ids = select(ConfigControl.config_control_id).where(ConfigControl.cycle_id == cycle_id)
        rows = (
            await self.db.execute(
                select(SampleJudgement)
                .where(SampleJudgement.config_control_id.in_(cc_ids))
                .options(selectinload(SampleJudgement.judge))
                .order_by(SampleJudgement.config_control_id, SampleJudgement.sample_no)
            )
        ).scalars()
        return [to_out(row) for row in rows]

    async def record(
        self,
        cycle_id: int,
        config_control_id: int,
        sample_no: int,
        data: SampleJudgementIn,
        current_user: dict[str, Any],
    ) -> SampleJudgementOut:
        from app.services.config_control_service import ConfigControlService

        cc = await self._config_control(cycle_id, config_control_id, current_user)
        output = await ConfigControlService(self.db).get_test_output(config_control_id)
        sample = next(
            (
                s
                for i, s in enumerate(output.samples)
                if (s.sample_no if isinstance(s.sample_no, int) else i + 1) == sample_no
            ),
            None,
        )
        if sample is None:
            raise NotFoundException("This sample is not in the control's tested samples.")

        tool_result = normalise_result(sample.result)
        action = "accepted" if data.result == tool_result else "modified"
        conclusion = (data.conclusion or "").strip() or None
        if action == "modified" and not conclusion:
            raise AppException(
                code="CONCLUSION_REQUIRED",
                message="Say why you are changing the tool's result.",
                status_code=422,
                field="conclusion",
            )
        if data.result == "FAIL" and not data.root_cause_category:
            raise AppException(
                code="ROOT_CAUSE_REQUIRED",
                message="Choose a root-cause category for a failed sample.",
                status_code=422,
                field="root_cause_category",
            )
        # A root cause only describes a sample that did not pass.
        category = data.root_cause_category if data.result != "PASS" else None
        note = (data.root_cause_note or "").strip() or None if category else None

        row = await self._row(config_control_id, sample_no)
        if row is None:
            row = SampleJudgement(config_control_id=config_control_id, sample_no=sample_no)
            self.db.add(row)
        row.tool_result = tool_result
        row.result = data.result
        row.action = action
        row.conclusion = conclusion
        row.root_cause_category = category
        row.root_cause_note = note
        row.judged_by = int(current_user["sub"])

        verb = (
            f"accepted the tool result {tool_result}"
            if action == "accepted"
            else f"changed the tool result {tool_result} to {data.result}"
        )
        parts = [f"Tester {verb}."]
        if conclusion:
            parts.append(f"Conclusion: {conclusion}")
        if category:
            parts.append(f"Root cause: {ROOT_CAUSE_CATEGORIES[category]}.")
        self.db.add(
            TestLog(
                test_id=output.test_id,
                control_id=cc.control_id,
                cycle_id=cycle_id,
                log_date=int(time.time()),
                changed_by=int(current_user["sub"]),
                status=f"TESTER_{data.result}"[:50],
                notes=" ".join(parts),
                source="judgement",
                sample_no=sample_no,
            )
        )
        await self.db.commit()
        fresh = await self._row(config_control_id, sample_no)
        assert fresh is not None  # noqa: S101 — just written
        return to_out(fresh)

    async def revert(
        self,
        cycle_id: int,
        config_control_id: int,
        sample_no: int,
        current_user: dict[str, Any],
    ) -> None:
        """Drop the tester's judgement, so the tool's result stands again."""
        cc = await self._config_control(cycle_id, config_control_id, current_user)
        row = await self._row(config_control_id, sample_no)
        if row is None:
            return
        await self.db.delete(row)
        from app.models.control_test import ControlTest

        test = (
            await self.db.execute(
                select(ControlTest.test_id).where(
                    ControlTest.config_control_id == config_control_id
                )
            )
        ).scalars().first()
        self.db.add(
            TestLog(
                test_id=test,
                control_id=cc.control_id,
                cycle_id=cycle_id,
                log_date=int(time.time()),
                changed_by=int(current_user["sub"]),
                status="TESTER_REVERTED",
                notes=f"Tester judgement withdrawn; the tool result {row.tool_result} stands.",
                source="judgement",
                sample_no=sample_no,
            )
        )
        await self.db.commit()

    async def clear_for_cycle(self, cycle_id: int) -> int:
        """Drop every judgement in a cycle. Caller commits."""
        cc_ids = select(ConfigControl.config_control_id).where(ConfigControl.cycle_id == cycle_id)
        res = await self.db.execute(
            delete(SampleJudgement).where(SampleJudgement.config_control_id.in_(cc_ids))
        )
        return res.rowcount or 0  # type: ignore[attr-defined]
