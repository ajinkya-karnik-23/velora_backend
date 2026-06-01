"""Control repository — catalog browsing with framework aggregation."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.models.control_framework import ControlFramework
from app.models.control_repository import ControlRepository
from app.repositories.base_repo import BaseRepo


class ControlRepo(BaseRepo[ControlRepository]):
    model = ControlRepository

    async def browse_with_frameworks(
        self,
        filters: dict[str, Any],
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ControlRepository], int]:
        """Browse control catalog with filters and framework eager-loading."""
        stmt = select(ControlRepository).options(
            joinedload(ControlRepository.owner),
            joinedload(ControlRepository.fccg_contact),
            joinedload(ControlRepository.frameworks),
        )
        count_stmt = select(func.count(ControlRepository.control_id))

        # Apply filters
        if filters.get("domain"):
            stmt = stmt.where(ControlRepository.domain == filters["domain"])
            count_stmt = count_stmt.where(ControlRepository.domain == filters["domain"])
        if filters.get("risk_level"):
            stmt = stmt.where(ControlRepository.risk_level == filters["risk_level"])
            count_stmt = count_stmt.where(ControlRepository.risk_level == filters["risk_level"])
        if filters.get("frequency"):
            stmt = stmt.where(ControlRepository.frequency == filters["frequency"])
            count_stmt = count_stmt.where(ControlRepository.frequency == filters["frequency"])
        if filters.get("status"):
            stmt = stmt.where(ControlRepository.status == filters["status"])
            count_stmt = count_stmt.where(ControlRepository.status == filters["status"])
        if filters.get("framework"):
            fw_sub = select(ControlFramework.control_id).where(
                ControlFramework.framework_name == filters["framework"]
            )
            stmt = stmt.where(ControlRepository.control_id.in_(fw_sub))
            count_stmt = count_stmt.where(ControlRepository.control_id.in_(fw_sub))
        if filters.get("search"):
            term = f"%{filters['search']}%"
            search_cond = or_(
                ControlRepository.control_name.ilike(term),
                ControlRepository.control_number.ilike(term),
                ControlRepository.control_desc.ilike(term),
            )
            stmt = stmt.where(search_cond)
            count_stmt = count_stmt.where(search_cond)

        total = (await self.session.execute(count_stmt)).scalar() or 0
        stmt = (
            stmt.order_by(ControlRepository.control_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(stmt)
        controls = list(result.unique().scalars().all())
        return controls, total

    async def get_detail(self, control_id: int) -> ControlRepository | None:
        """Get a single control with owner/contact names and frameworks."""
        stmt = (
            select(ControlRepository)
            .options(
                joinedload(ControlRepository.owner),
                joinedload(ControlRepository.fccg_contact),
                joinedload(ControlRepository.frameworks),
            )
            .where(ControlRepository.control_id == control_id)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()
