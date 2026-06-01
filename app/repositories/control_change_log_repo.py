"""Control change log repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models.control_change_log import ControlChangeLog
from app.repositories.base_repo import BaseRepo


class ControlChangeLogRepo(BaseRepo[ControlChangeLog]):
    model = ControlChangeLog

    async def get_by_control(self, control_id: int) -> list[ControlChangeLog]:
        """Get changelog entries for a control with resolved version names."""
        stmt = (
            select(ControlChangeLog)
            .options(
                joinedload(ControlChangeLog.changer),
                joinedload(ControlChangeLog.version_from),
                joinedload(ControlChangeLog.version_to),
            )
            .where(ControlChangeLog.control_id == control_id)
            .order_by(ControlChangeLog.change_timestamp.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())
