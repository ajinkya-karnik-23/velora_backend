"""Config control repository — attaching controls to cycles."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models.config_control import ConfigControl
from app.repositories.base_repo import BaseRepo


class ConfigControlRepo(BaseRepo[ConfigControl]):
    model = ConfigControl

    async def get_cycle_controls(self, cycle_id: int) -> list[ConfigControl]:
        """Get all controls attached to a cycle with their test records."""
        stmt = (
            select(ConfigControl)
            .options(
                joinedload(ConfigControl.control),
                joinedload(ConfigControl.test),
            )
            .where(ConfigControl.cycle_id == cycle_id)
            .order_by(ConfigControl.config_control_id)
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())

    async def get_by_cycle_and_control(
        self, cycle_id: int, control_id: int
    ) -> ConfigControl | None:
        stmt = select(ConfigControl).where(
            ConfigControl.cycle_id == cycle_id,
            ConfigControl.control_id == control_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
