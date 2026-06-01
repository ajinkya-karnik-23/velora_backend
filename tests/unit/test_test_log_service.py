"""Unit tests for TestLogService."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.test_log import TestLogCreate
from app.services.test_log_service import TestLogService


@pytest.fixture
def db():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.get = AsyncMock(return_value=None)
    return session


@pytest.fixture
def service(db):
    return TestLogService(db)


CURRENT_USER = {"sub": 1, "roles": ["Admin"], "permissions": []}


def _mock_log():
    log = MagicMock()
    log.log_id = 1
    log.test_id = 1
    log.control_id = 10
    log.control_number = "CTRL-001"
    log.control_name = "Test Control"
    log.cycle_id = 1
    log.log_date = int(time.time())
    log.changed_by = 1
    log.status = "Pass"
    log.execution_time_seconds = None
    log.report_link = None
    log.notes = None
    log.created_time = int(time.time())
    log.updated_time = int(time.time())
    # Relationships
    log.control = MagicMock(control_number="CTRL-001", control_name="Test Control")
    log.changer = MagicMock(user_name="admin")
    return log


@pytest.mark.asyncio
async def test_create_log_success(service):
    mock_log = _mock_log()
    service.repo.create = AsyncMock(return_value=mock_log)
    service.db.get = AsyncMock(return_value=mock_log)

    data = TestLogCreate(test_id=1, cycle_id=1, status="Pass")
    result = await service.create_log(data, CURRENT_USER)
    assert result.status == "Pass"
    service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_log_with_log_date(service):
    mock_log = _mock_log()
    service.repo.create = AsyncMock(return_value=mock_log)
    service.db.get = AsyncMock(return_value=mock_log)

    now = int(time.time())
    data = TestLogCreate(cycle_id=1, status="Fail", log_date=now)
    result = await service.create_log(data, CURRENT_USER)
    assert result.log_id == 1


@pytest.mark.asyncio
async def test_list_by_cycle(service):
    logs = [_mock_log(), _mock_log()]
    service.repo.get_by_cycle = AsyncMock(return_value=logs)

    result = await service.list_by_cycle(1)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Schema validation (CHECK constraint at Pydantic level)
# ---------------------------------------------------------------------------


def test_create_schema_requires_at_least_one_linkage():
    with pytest.raises(ValueError, match="At least one"):
        TestLogCreate(status="Pass")


def test_create_schema_valid_with_test_id():
    data = TestLogCreate(test_id=1, status="Pass")
    assert data.test_id == 1


def test_create_schema_valid_with_cycle_id():
    data = TestLogCreate(cycle_id=1, status="In Progress")
    assert data.cycle_id == 1


def test_create_schema_valid_with_control_id():
    data = TestLogCreate(control_id=5, status="Fail")
    assert data.control_id == 5
