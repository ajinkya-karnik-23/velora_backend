"""Evidence file repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.models.engagement_team import EngagementTeam
from app.models.evidence_file import EvidenceFile
from app.models.review_cycle import ReviewCycle
from app.repositories.base_repo import BaseRepo


class EvidenceRepo(BaseRepo[EvidenceFile]):
    model = EvidenceFile

    def _load_opts(self):
        return (
            joinedload(EvidenceFile.uploader),
            joinedload(EvidenceFile.review_cycle),
            joinedload(EvidenceFile.control),
        )

    async def list_with_joins(
        self,
        filters: dict[str, Any],
        user_id: int,
        user_roles: list[str],
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[EvidenceFile], int]:
        stmt = select(EvidenceFile).options(*self._load_opts())
        count_stmt = select(func.count(EvidenceFile.evidence_id))

        conds = []
        if filters.get("cycle_id"):
            conds.append(EvidenceFile.cycle_id == filters["cycle_id"])
        if filters.get("control_id"):
            conds.append(EvidenceFile.control_id == filters["control_id"])
        if filters.get("test_id"):
            conds.append(EvidenceFile.test_id == filters["test_id"])
        if filters.get("uploaded_by"):
            conds.append(EvidenceFile.uploaded_by == filters["uploaded_by"])
        if filters.get("file_type"):
            conds.append(EvidenceFile.file_type == filters["file_type"])
        if filters.get("status"):
            conds.append(EvidenceFile.status == filters["status"])
        if filters.get("search"):
            like = f"%{filters['search']}%"
            conds.append(
                or_(
                    EvidenceFile.file_name.ilike(like),
                    EvidenceFile.comments.ilike(like),
                )
            )

        for c in conds:
            stmt = stmt.where(c)
            count_stmt = count_stmt.where(c)

        # Engagement scoping for Auditor/Viewer
        if not any(r in ("Admin", "Moderator") for r in user_roles):
            member_cycles = select(EngagementTeam.cycle_id).where(
                EngagementTeam.user_id == user_id
            )
            scope = EvidenceFile.cycle_id.in_(member_cycles)
            stmt = stmt.where(scope)
            count_stmt = count_stmt.where(scope)

        total = (await self.session.execute(count_stmt)).scalar() or 0
        stmt = (
            stmt.order_by(EvidenceFile.evidence_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(stmt)
        items = list(result.unique().scalars().all())
        return items, total

    async def get_detail(self, evidence_id: int) -> EvidenceFile | None:
        stmt = (
            select(EvidenceFile)
            .options(*self._load_opts())
            .where(EvidenceFile.evidence_id == evidence_id)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_stats(
        self, user_id: int, user_roles: list[str]
    ) -> dict[str, Any]:
        # Base filter for scoping
        def _scope(stmt):
            if not any(r in ("Admin", "Moderator") for r in user_roles):
                member_cycles = select(EngagementTeam.cycle_id).where(
                    EngagementTeam.user_id == user_id
                )
                stmt = stmt.where(EvidenceFile.cycle_id.in_(member_cycles))
            return stmt

        by_type_stmt = _scope(
            select(
                EvidenceFile.file_type,
                func.count(EvidenceFile.evidence_id),
                func.coalesce(func.sum(EvidenceFile.file_size), 0),
            ).group_by(EvidenceFile.file_type)
        )
        by_status_stmt = _scope(
            select(EvidenceFile.status, func.count(EvidenceFile.evidence_id)).group_by(
                EvidenceFile.status
            )
        )
        total_stmt = _scope(
            select(
                func.count(EvidenceFile.evidence_id),
                func.coalesce(func.sum(EvidenceFile.file_size), 0),
            )
        )

        by_type_rows = (await self.session.execute(by_type_stmt)).all()
        by_status_rows = (await self.session.execute(by_status_stmt)).all()
        total_row = (await self.session.execute(total_stmt)).one()

        return {
            "total_count": int(total_row[0] or 0),
            "total_size": int(total_row[1] or 0),
            "by_file_type": {
                (r[0] or "unknown"): {"count": int(r[1]), "size": int(r[2] or 0)}
                for r in by_type_rows
            },
            "by_status": {r[0]: int(r[1]) for r in by_status_rows},
        }

    async def get_vault(
        self, user_id: int, user_roles: list[str]
    ) -> list[dict[str, Any]]:
        """Return distinct engagements with evidence counts."""
        stmt = (
            select(
                ReviewCycle.cycle_id,
                ReviewCycle.name,
                func.count(EvidenceFile.evidence_id).label("evidence_count"),
            )
            .join(EvidenceFile, EvidenceFile.cycle_id == ReviewCycle.cycle_id)
            .group_by(ReviewCycle.cycle_id, ReviewCycle.name)
        )
        if not any(r in ("Admin", "Moderator") for r in user_roles):
            member_cycles = select(EngagementTeam.cycle_id).where(
                EngagementTeam.user_id == user_id
            )
            stmt = stmt.where(ReviewCycle.cycle_id.in_(member_cycles))
        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "cycle_id": r.cycle_id,
                "engagement_name": r.name,
                "evidence_count": int(r.evidence_count),
            }
            for r in rows
        ]
