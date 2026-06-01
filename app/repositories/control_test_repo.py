"""Control test repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models.config_control import ConfigControl
from app.models.control_repository import ControlRepository
from app.models.control_test import ControlTest
from app.models.control_test_template import ControlTestTemplate
from app.repositories.base_repo import BaseRepo


class ControlTestRepo(BaseRepo[ControlTest]):
    model = ControlTest

    async def get_by_config_control(self, config_control_id: int) -> list[ControlTest]:
        """All test objectives for a single configured control."""
        stmt = (
            select(ControlTest)
            .where(ControlTest.config_control_id == config_control_id)
            .order_by(ControlTest.test_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_templates_for_control(self, control_id: int) -> list[ControlTestTemplate]:
        """Return canonical test templates for a control from the cycle-independent table."""
        stmt = (
            select(ControlTestTemplate)
            .where(
                ControlTestTemplate.control_id == control_id,
                ControlTestTemplate.tests.is_not(None),
            )
            .order_by(ControlTestTemplate.template_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_cycle_tests(self, cycle_id: int) -> list[ControlTest]:
        """All test objectives for every control in a cycle, with control info joined."""
        stmt = (
            select(ControlTest)
            .join(ConfigControl, ControlTest.config_control_id == ConfigControl.config_control_id)
            .join(ControlRepository, ConfigControl.control_id == ControlRepository.control_id)
            .where(ConfigControl.cycle_id == cycle_id)
            .options(
                joinedload(ControlTest.config_control).joinedload(ConfigControl.control)
            )
            .order_by(ConfigControl.config_control_id, ControlTest.test_id)
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())
