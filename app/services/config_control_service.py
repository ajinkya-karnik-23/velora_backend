"""Config control service — attach/detach controls to cycles (atomic)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.models.config_control import ConfigControl
from app.models.control_test import ControlTest
from app.repositories.config_control_repo import ConfigControlRepo
from app.repositories.control_repo import ControlRepo
from app.repositories.control_test_repo import ControlTestRepo
from app.schemas.config_control import ConfigControlOut


def _to_out(cc: ConfigControl) -> ConfigControlOut:
    ctrl = cc.control
    test = cc.test
    return ConfigControlOut(
        config_control_id=cc.config_control_id,
        cycle_id=cc.cycle_id,
        control_id=cc.control_id,
        control_number=ctrl.control_number if ctrl else None,
        control_name=ctrl.control_name if ctrl else None,
        domain=ctrl.domain if ctrl else None,
        risk_level=ctrl.risk_level if ctrl else None,
        frequency=ctrl.frequency if ctrl else None,
        status=ctrl.status if ctrl else None,
        test_id=test.test_id if test else None,
        tests=test.tests if test else None,
        note=test.note if test else None,
        comments=test.comments if test else None,
        created_time=cc.created_time,
        updated_time=cc.updated_time,
    )


class ConfigControlService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ConfigControlRepo(db)
        self.control_repo = ControlRepo(db)
        self.test_repo = ControlTestRepo(db)

    async def _seed_tests(self, config_control_id: int, control_id: int) -> None:
        """Populate ControlTest rows from the cycle-independent ControlTestTemplate table.
        Uses source_test_id from the template so IDs always match the detailed JSONs.
        Falls back to one blank row (auto-increment) only if no templates exist."""
        templates = await self.test_repo.get_templates_for_control(control_id)
        if templates:
            for tmpl in templates:
                kwargs: dict = {
                    "config_control_id": config_control_id,
                    "tests": tmpl.tests,
                    "note": tmpl.note,
                    "comments": tmpl.comments,
                }
                if tmpl.source_test_id is not None:
                    kwargs["test_id"] = tmpl.source_test_id
                self.db.add(ControlTest(**kwargs))
        else:
            self.db.add(ControlTest(config_control_id=config_control_id))
        await self.db.flush()

    async def get_cycle_controls(self, cycle_id: int) -> list[ConfigControlOut]:
        ccs = await self.repo.get_cycle_controls(cycle_id)
        return [_to_out(cc) for cc in ccs]

    async def attach_control(self, cycle_id: int, control_id: int) -> ConfigControlOut:
        # Verify control exists
        ctrl = await self.control_repo.get_by_id(control_id)
        if not ctrl:
            raise NotFoundException("Control not found.")
        # Check duplicate
        existing = await self.repo.get_by_cycle_and_control(cycle_id, control_id)
        if existing:
            raise ConflictException("Control is already attached to this cycle.")
        cc = ConfigControl(cycle_id=cycle_id, control_id=control_id)
        await self.repo.create(cc)  # flush materialises config_control_id
        await self._seed_tests(cc.config_control_id, control_id)
        await self.db.commit()
        # Re-fetch with joins
        ccs = await self.repo.get_cycle_controls(cycle_id)
        for item in ccs:
            if item.control_id == control_id:
                return _to_out(item)
        return _to_out(cc)  # fallback

    async def bulk_attach(self, cycle_id: int, control_ids: list[int]) -> list[ConfigControlOut]:
        for control_id in control_ids:
            ctrl = await self.control_repo.get_by_id(control_id)
            if not ctrl:
                raise NotFoundException(f"Control {control_id} not found.")
            existing = await self.repo.get_by_cycle_and_control(cycle_id, control_id)
            if existing:
                continue  # skip duplicates in bulk
            cc = ConfigControl(cycle_id=cycle_id, control_id=control_id)
            await self.repo.create(cc)
            await self._seed_tests(cc.config_control_id, control_id)
        await self.db.commit()
        return await self.get_cycle_controls(cycle_id)

    async def detach_control(self, cycle_id: int, control_id: int) -> None:
        cc = await self.repo.get_by_cycle_and_control(cycle_id, control_id)
        if not cc:
            raise NotFoundException("Control is not attached to this cycle.")
        await self.repo.delete(cc)
        await self.db.commit()

    async def bulk_detach(self, cycle_id: int, config_control_ids: list[int]) -> None:
        for cc_id in config_control_ids:
            cc = await self.repo.get_by_id(cc_id)
            if cc and cc.cycle_id == cycle_id:
                await self.repo.delete(cc)
        await self.db.commit()

    async def reset_cycle_controls(self, cycle_id: int) -> None:
        ccs = await self.repo.get_cycle_controls(cycle_id)
        for cc in ccs:
            await self.repo.delete(cc)
        await self.db.commit()
