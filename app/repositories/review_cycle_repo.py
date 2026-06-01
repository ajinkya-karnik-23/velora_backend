"""Review cycle repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.engagement_team import EngagementTeam
from app.models.review_cycle import ReviewCycle
from app.models.user import User
from app.repositories.base_repo import BaseRepo


class ReviewCycleRepo(BaseRepo[ReviewCycle]):
    model = ReviewCycle

    async def list_with_client_and_lead(
        self,
        filters: dict[str, Any],
        user_id: int,
        user_roles: list[str],
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ReviewCycle], int]:
        """List review cycles. Auditor/Viewer filtered to own engagements."""
        stmt = select(ReviewCycle).options(selectinload(ReviewCycle.lead))
        count_stmt = select(func.count(ReviewCycle.cycle_id))

        # Apply filters
        if filters.get("client_id"):
            stmt = stmt.where(ReviewCycle.client_id == filters["client_id"])
            count_stmt = count_stmt.where(ReviewCycle.client_id == filters["client_id"])
        if filters.get("status"):
            stmt = stmt.where(ReviewCycle.status == filters["status"])
            count_stmt = count_stmt.where(ReviewCycle.status == filters["status"])

        # Engagement scoping for Auditor/Viewer
        if not any(r in ("Admin", "Moderator") for r in user_roles):
            member_cycles = (
                select(EngagementTeam.cycle_id).where(EngagementTeam.user_id == user_id)
            )
            stmt = stmt.where(ReviewCycle.cycle_id.in_(member_cycles))
            count_stmt = count_stmt.where(ReviewCycle.cycle_id.in_(member_cycles))

        total = (await self.session.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(ReviewCycle.cycle_id).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        cycles = list(result.scalars().all())
        return cycles, total

    async def get_with_lead(self, cycle_id: int) -> ReviewCycle | None:
        stmt = (
            select(ReviewCycle)
            .options(joinedload(ReviewCycle.lead))
            .where(ReviewCycle.cycle_id == cycle_id)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_by_client(self, client_id: int) -> list[ReviewCycle]:
        stmt = select(ReviewCycle).where(ReviewCycle.client_id == client_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
