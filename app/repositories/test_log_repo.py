"""Test log repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models.test_log import TestLog
from app.repositories.base_repo import BaseRepo


class TestLogRepo(BaseRepo[TestLog]):
    model = TestLog

    async def get_by_cycle(self, cycle_id: int) -> list[TestLog]:
        stmt = (
            select(TestLog)
            .options(
                joinedload(TestLog.control),
                joinedload(TestLog.changer),
                joinedload(TestLog.review_cycle),
            )
            .where(TestLog.cycle_id == cycle_id)
            .order_by(TestLog.log_date.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())

    async def get_by_test(self, test_id: int) -> list[TestLog]:
        stmt = (
            select(TestLog)
            .options(
                joinedload(TestLog.control),
                joinedload(TestLog.changer),
                joinedload(TestLog.review_cycle),
            )
            .where(TestLog.test_id == test_id)
            .order_by(TestLog.log_date.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())

    async def get_all(self, limit: int = 200) -> list[TestLog]:
        stmt = (
            select(TestLog)
            .options(
                joinedload(TestLog.control),
                joinedload(TestLog.changer),
                joinedload(TestLog.review_cycle),
            )
            .order_by(TestLog.log_date.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())
