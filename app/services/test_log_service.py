"""Test log service — create, list by cycle/test."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.test_log import TestLog
from app.repositories.test_log_repo import TestLogRepo
from app.schemas.test_log import RecordSampleRunRequest, TestLogCreate, TestLogOut


# Deliberately generic: must never say what the evidence was expected to be.
EVIDENCE_EXCEPTION_NOTE = (
    "The evidence uploaded for this sample does not meet the requirements of this test."
)


def _step_label(log: TestLog) -> str | None:
    step = log.__dict__.get("manual_step")  # only when eagerly loaded
    return f"{step.serial} · {step.title}" if step is not None else None


def _to_out(log: TestLog) -> TestLogOut:
    ctrl = getattr(log, "control", None)
    changer = getattr(log, "changer", None)
    cycle = getattr(log, "review_cycle", None)
    return TestLogOut(
        log_id=log.log_id,
        test_id=log.test_id,
        control_id=log.control_id,
        control_number=ctrl.control_number if ctrl else None,
        control_name=ctrl.control_name if ctrl else None,
        cycle_id=log.cycle_id,
        cycle_name=cycle.name if cycle else None,
        log_date=log.log_date,
        changed_by=log.changed_by,
        tested_by=changer.user_name if changer else None,
        status=log.status,
        execution_time_seconds=log.execution_time_seconds,
        report_link=log.report_link,
        notes=log.notes,
        source=log.source,
        sample_no=log.sample_no,
        manual_step_id=log.manual_step_id,
        step_label=_step_label(log),
        created_time=log.created_time,
        updated_time=log.updated_time,
    )


class TestLogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = TestLogRepo(db)

    async def create_log(
        self, data: TestLogCreate, current_user: dict[str, Any]
    ) -> TestLogOut:
        log = TestLog(
            test_id=data.test_id,
            control_id=data.control_id,
            cycle_id=data.cycle_id,
            log_date=data.log_date or int(time.time()),
            changed_by=int(current_user["sub"]),
            status=data.status,
            execution_time_seconds=data.execution_time_seconds,
            report_link=data.report_link,
            notes=data.notes,
        )
        await self.repo.create(log)
        await self.db.commit()
        # Re-fetch with all joins so _to_out can access relationships
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload
        stmt = (
            select(TestLog)
            .options(
                joinedload(TestLog.control),
                joinedload(TestLog.changer),
                joinedload(TestLog.review_cycle),
            )
            .where(TestLog.log_id == log.log_id)
        )
        result = await self.db.execute(stmt)
        fresh = result.unique().scalar_one_or_none()
        return _to_out(fresh) if fresh else _to_out(log)

    async def record_sample_run(
        self, data: RecordSampleRunRequest, current_user: dict[str, Any]
    ) -> TestLogOut:
        """Log a finished sample run with the verdict the testing output holds."""
        from app.core.exceptions import AppException, ForbiddenException, NotFoundException
        from app.models.config_control import ConfigControl
        from app.services.config_control_service import ConfigControlService

        cc = await self.db.get(ConfigControl, data.config_control_id)
        if cc is None:
            raise NotFoundException("Attached control not found.")
        roles = current_user.get("roles", [])
        if not any(r in ("Admin", "Moderator") for r in roles):
            from app.repositories.engagement_team_repo import EngagementTeamRepo

            if not await EngagementTeamRepo(self.db).is_member(
                cc.cycle_id, int(current_user["sub"])
            ):
                raise ForbiddenException("Not a member of this engagement.")

        output = await ConfigControlService(self.db).get_test_output(cc.config_control_id)
        sample = next(
            (
                s
                for i, s in enumerate(output.samples)
                if (s.sample_no if isinstance(s.sample_no, int) else i + 1) == data.sample_no
            ),
            None,
        )
        if sample is None:
            raise NotFoundException("Sample not found in this control's testing output.")
        if sample.evidence_status == "missing":
            raise AppException(
                code="EVIDENCE_REQUIRED",
                message="Upload evidence for this sample before running it.",
                status_code=422,
            )

        if sample.evidence_status == "invalid":
            status, notes = "EVIDENCE_EXCEPTION", EVIDENCE_EXCEPTION_NOTE
        else:
            status = (sample.result or "NOT_VALIDATED").strip().upper()[:50]
            notes = sample.validation

        seconds = None
        if data.execution_time_ms is not None:
            seconds = max(1, -(-data.execution_time_ms // 1000))

        log = TestLog(
            test_id=output.test_id,
            control_id=cc.control_id,
            cycle_id=cc.cycle_id,
            log_date=int(time.time()),
            changed_by=int(current_user["sub"]),
            status=status,
            execution_time_seconds=seconds,
            notes=notes,
            source="sample",
            sample_no=data.sample_no,
        )
        return await self._save(log)

    async def _save(self, log: TestLog) -> TestLogOut:
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        await self.repo.create(log)
        await self.db.commit()
        fresh = (
            await self.db.execute(
                select(TestLog)
                .options(
                    joinedload(TestLog.control),
                    joinedload(TestLog.changer),
                    joinedload(TestLog.review_cycle),
                    joinedload(TestLog.manual_step),
                )
                .where(TestLog.log_id == log.log_id)
            )
        ).unique().scalar_one_or_none()
        return _to_out(fresh) if fresh else _to_out(log)

    async def list_by_cycle(self, cycle_id: int) -> list[TestLogOut]:
        logs = await self.repo.get_by_cycle(cycle_id)
        return [_to_out(log) for log in logs]

    async def list_all(self, limit: int = 200, client_id: int | None = None) -> list[TestLogOut]:
        logs = await self.repo.get_all(limit, client_id=client_id)
        return [_to_out(log) for log in logs]
