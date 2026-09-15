"""Test log repository."""

from __future__ import annotations

from sqlalchemy import or_, select
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

    async def get_all(self, limit: int = 200, client_id: int | None = None) -> list[TestLog]:
        stmt = (
            select(TestLog)
            .options(
                joinedload(TestLog.control),
                joinedload(TestLog.changer),
                joinedload(TestLog.review_cycle),
                joinedload(TestLog.manual_step),
            )
            .order_by(TestLog.log_date.desc(), TestLog.log_id.desc())
            .limit(limit)
        )
        if client_id is not None:
            from app.models.control_repository import ControlRepository
            from app.models.review_cycle import ReviewCycle

            # An entry belongs to a client through its cycle, or through its
            # control when it was logged without one.
            stmt = stmt.where(
                or_(
                    TestLog.cycle_id.in_(
                        select(ReviewCycle.cycle_id).where(ReviewCycle.client_id == client_id)
                    ),
                    TestLog.cycle_id.is_(None)
                    & TestLog.control_id.in_(
                        select(ControlRepository.control_id).where(
                            ControlRepository.client_id == client_id
                        )
                    ),
                )
            )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())
