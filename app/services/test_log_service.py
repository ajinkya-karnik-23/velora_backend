"""Test log service — create, list by cycle/test."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.test_log import TestLog
from app.repositories.test_log_repo import TestLogRepo
from app.schemas.test_log import TestLogCreate, TestLogOut


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

    async def list_by_cycle(self, cycle_id: int) -> list[TestLogOut]:
        logs = await self.repo.get_by_cycle(cycle_id)
        return [_to_out(log) for log in logs]

    async def list_all(self, limit: int = 200) -> list[TestLogOut]:
        logs = await self.repo.get_all(limit)
        return [_to_out(log) for log in logs]
