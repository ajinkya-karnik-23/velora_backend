"""Unit tests for ConfigControlService."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictException, NotFoundException
from app.services.config_control_service import ConfigControlService


@pytest.fixture
def db():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service(db):
    return ConfigControlService(db)


def _mock_config_control():
    cc = MagicMock()
    cc.config_control_id = 1
    cc.cycle_id = 1
    cc.control_id = 10
    cc.created_time = int(time.time())
    cc.updated_time = int(time.time())
    cc.control = MagicMock(
        control_number="CTRL-001",
        control_name="Test Control",
        domain="IT",
        risk_level="High",
        frequency="Annual",
        status="Active",
    )
    cc.test = MagicMock(test_id=1, tests=None, note=None, comments=None)
    return cc


@pytest.mark.asyncio
async def test_attach_control_success(service):
    service.control_repo.get_by_id = AsyncMock(return_value=MagicMock())
    service.repo.get_by_cycle_and_control = AsyncMock(return_value=None)
    service.repo.create = AsyncMock(return_value=MagicMock(config_control_id=1))

    cc = _mock_config_control()
    service.repo.get_cycle_controls = AsyncMock(return_value=[cc])

    result = await service.attach_control(1, 10)
    service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_attach_control_not_found(service):
    service.control_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException, match="Control not found"):
        await service.attach_control(1, 999)


@pytest.mark.asyncio
async def test_attach_control_duplicate(service):
    service.control_repo.get_by_id = AsyncMock(return_value=MagicMock())
    service.repo.get_by_cycle_and_control = AsyncMock(return_value=MagicMock())

    with pytest.raises(ConflictException, match="already attached"):
        await service.attach_control(1, 10)


@pytest.mark.asyncio
async def test_detach_control_success(service):
    service.repo.get_by_cycle_and_control = AsyncMock(return_value=MagicMock())
    service.repo.delete = AsyncMock()

    await service.detach_control(1, 10)
    service.repo.delete.assert_awaited_once()
    service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_detach_control_not_found(service):
    service.repo.get_by_cycle_and_control = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException, match="not attached"):
        await service.detach_control(1, 999)


@pytest.mark.asyncio
async def test_bulk_attach_skips_duplicates(service):
    service.control_repo.get_by_id = AsyncMock(return_value=MagicMock())
    # First not attached, second already attached
    service.repo.get_by_cycle_and_control = AsyncMock(
        side_effect=[None, MagicMock()]
    )
    service.repo.create = AsyncMock(return_value=MagicMock(config_control_id=1))
    service.repo.get_cycle_controls = AsyncMock(return_value=[_mock_config_control()])

    result = await service.bulk_attach(1, [10, 20])
    # Only one create call (second skipped)
    assert service.repo.create.call_count == 1


@pytest.mark.asyncio
async def test_bulk_attach_control_not_found(service):
    service.control_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException, match="Control 999 not found"):
        await service.bulk_attach(1, [999])
