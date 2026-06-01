"""Control service — browse catalog, get detail, get changelog. Read-only in V1."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.control_repository import ControlRepository
from app.repositories.control_change_log_repo import ControlChangeLogRepo
from app.repositories.control_repo import ControlRepo
from app.schemas.control import ChangeLogOut, ControlOut


def _to_out(ctrl: ControlRepository) -> ControlOut:
    return ControlOut(
        **{c.key: getattr(ctrl, c.key) for c in ctrl.__table__.columns},
        owner_name=ctrl.owner.user_name if ctrl.owner else None,
        fccg_contact_name=ctrl.fccg_contact.user_name if ctrl.fccg_contact else None,
        frameworks=[fw.framework_name for fw in ctrl.frameworks],
    )


class ControlService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ControlRepo(db)
        self.changelog_repo = ControlChangeLogRepo(db)

    async def browse(
        self,
        filters: dict[str, Any],
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ControlOut], int]:
        controls, total = await self.repo.browse_with_frameworks(filters, page, page_size)
        return [_to_out(c) for c in controls], total

    async def get_detail(self, control_id: int) -> ControlOut:
        ctrl = await self.repo.get_detail(control_id)
        if not ctrl:
            raise NotFoundException("Control not found.")
        return _to_out(ctrl)

    async def get_changelog(self, control_id: int) -> list[ChangeLogOut]:
        # Verify control exists
        ctrl = await self.repo.get_by_id(control_id)
        if not ctrl:
            raise NotFoundException("Control not found.")
        logs = await self.changelog_repo.get_by_control(control_id)
        return [
            ChangeLogOut(
                **{c.key: getattr(log, c.key) for c in log.__table__.columns},
                changer_name=log.changer.user_name if log.changer else None,
                from_version_name=(
                    log.version_from.version_name if log.version_from else None
                ),
                to_version_name=(
                    log.version_to.version_name if log.version_to else None
                ),
            )
            for log in logs
        ]
