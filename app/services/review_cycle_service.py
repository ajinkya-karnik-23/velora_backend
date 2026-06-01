"""Review cycle service — CRUD, lifecycle state machine, stats."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.config_control import ConfigControl
from app.models.engagement_team import EngagementTeam
from app.models.evidence_file import EvidenceFile
from app.models.review_cycle import ReviewCycle
from app.models.test_log import TestLog
from app.repositories.review_cycle_repo import ReviewCycleRepo
from app.schemas.review_cycle import ReviewCycleCreate, ReviewCycleOut, ReviewCycleUpdate

# Lifecycle state machine: forward only, no skipping
VALID_TRANSITIONS: dict[str, list[str]] = {
    "Draft": ["Active"],
    "Active": ["In Review"],
    "In Review": ["Completed"],
    "Completed": ["Archived"],
    "Archived": [],
}


def _to_out(cycle: ReviewCycle) -> ReviewCycleOut:
    lead_name = cycle.lead.user_name if cycle.lead else None
    return ReviewCycleOut(
        **{c.key: getattr(cycle, c.key) for c in cycle.__table__.columns},
        lead_name=lead_name,
    )


class ReviewCycleService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ReviewCycleRepo(db)

    async def create_cycle(self, data: ReviewCycleCreate) -> ReviewCycleOut:
        cycle = ReviewCycle(**data.model_dump(), status="Draft")
        await self.repo.create(cycle)
        await self.db.commit()
        cycle = await self.repo.get_with_lead(cycle.cycle_id)
        return _to_out(cycle)

    async def get_cycle(self, cycle_id: int) -> ReviewCycleOut:
        cycle = await self.repo.get_with_lead(cycle_id)
        if not cycle:
            raise NotFoundException("Review cycle not found.")
        return _to_out(cycle)

    async def list_cycles(
        self,
        filters: dict[str, Any],
        user_id: int,
        user_roles: list[str],
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ReviewCycleOut], int]:
        cycles, total = await self.repo.list_with_client_and_lead(
            filters, user_id, user_roles, page, page_size
        )
        return [_to_out(c) for c in cycles], total

    async def update_cycle(self, cycle_id: int, data: ReviewCycleUpdate) -> ReviewCycleOut:
        cycle = await self.repo.get_with_lead(cycle_id)
        if not cycle:
            raise NotFoundException("Review cycle not found.")

        update_data = {k: v for k, v in data.model_dump().items() if v is not None}

        # Validate state transition if status is being changed
        if "status" in update_data and update_data["status"] != cycle.status:
            new_status = update_data["status"]
            if new_status not in VALID_TRANSITIONS.get(cycle.status, []):
                raise AppException(
                    code="INVALID_TRANSITION",
                    message=f"Cannot transition from '{cycle.status}' to '{new_status}'.",
                    status_code=400,
                )

        await self.repo.update(cycle, update_data)
        await self.db.commit()
        cycle = await self.repo.get_with_lead(cycle_id)
        return _to_out(cycle)

    async def delete_cycle(self, cycle_id: int) -> None:
        cycle = await self.repo.get_by_id(cycle_id)
        if not cycle:
            raise NotFoundException("Review cycle not found.")
        if cycle.status != "Draft":
            raise ConflictException("Can only delete cycles in Draft status.")
        # Phase 5: block deletion if any evidence exists
        ev_count = (
            await self.db.execute(
                select(func.count(EvidenceFile.evidence_id)).where(
                    EvidenceFile.cycle_id == cycle_id
                )
            )
        ).scalar() or 0
        if ev_count > 0:
            raise ConflictException("Cannot delete cycle: evidence files exist.")
        await self.repo.delete(cycle)
        await self.db.commit()

    async def get_stats(self, cycle_id: int) -> dict:
        """Compute cycle stats aligned with the Overview KPI cards."""
        cycle = await self.repo.get_by_id(cycle_id)
        if not cycle:
            raise NotFoundException("Review cycle not found.")

        days_remaining = max(0, (cycle.due_date - int(time.time())) // 86400)

        total_controls = (
            await self.db.execute(
                select(func.count(ConfigControl.config_control_id)).where(
                    ConfigControl.cycle_id == cycle_id
                )
            )
        ).scalar() or 0

        tested_controls = (
            await self.db.execute(
                select(func.count(func.distinct(TestLog.control_id))).where(
                    TestLog.cycle_id == cycle_id, TestLog.control_id.is_not(None)
                )
            )
        ).scalar() or 0

        team_members = (
            await self.db.execute(
                select(func.count(EngagementTeam.engagement_team_id)).where(
                    EngagementTeam.cycle_id == cycle_id
                )
            )
        ).scalar() or 0

        evidence_count = (
            await self.db.execute(
                select(func.count(EvidenceFile.evidence_id)).where(
                    EvidenceFile.cycle_id == cycle_id
                )
            )
        ).scalar() or 0

        completion_pct = (
            round(float(tested_controls) / float(total_controls) * 100.0, 2)
            if total_controls else 0.0
        )

        return {
            "total_controls": int(total_controls),
            "tested_controls": int(tested_controls),
            "team_members": int(team_members),
            "completion_percentage": completion_pct,
            "evidence_count": int(evidence_count),
            "days_remaining": int(days_remaining),
        }
