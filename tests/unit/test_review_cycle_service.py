"""Unit tests for ReviewCycleService."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.schemas.review_cycle import ReviewCycleCreate, ReviewCycleUpdate
from app.services.review_cycle_service import ReviewCycleService, VALID_TRANSITIONS


@pytest.fixture
def db():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def service(db):
    return ReviewCycleService(db)


def _mock_cycle(cycle_id=1, status="Draft", due_date=None):
    now = int(time.time())
    c = MagicMock()
    c.cycle_id = cycle_id
    c.client_id = 1
    c.project_lead = 1
    c.review_period = "Q1"
    c.name = "Test Cycle"
    c.audit_type = "Internal"
    c.priority = "High"
    c.framework = None
    c.start_date = now
    c.due_date = due_date or (now + 86400 * 30)
    c.end_date = None
    c.status = status
    c.score = None
    c.overview = None
    c.description = None
    c.created_time = now
    c.updated_time = now
    c.lead = MagicMock(user_name="admin")
    cols = []
    for key in [
        "cycle_id", "client_id", "project_lead", "review_period", "name",
        "audit_type", "priority", "framework", "start_date", "due_date",
        "end_date", "status", "score", "overview", "description",
        "created_time", "updated_time",
    ]:
        col = MagicMock()
        col.key = key
        cols.append(col)
    table = MagicMock()
    table.columns = cols
    c.__table__ = table
    return c


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_cycle(service):
    cycle = _mock_cycle()
    service.repo.create = AsyncMock(return_value=cycle)
    service.repo.get_with_lead = AsyncMock(return_value=cycle)

    data = ReviewCycleCreate(
        client_id=1, review_period="Q1", name="New",
        start_date=int(time.time()), due_date=int(time.time()) + 86400,
    )
    result = await service.create_cycle(data)
    assert result.name == "Test Cycle"
    service.db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# Lifecycle state transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "from_status,to_status",
    [("Draft", "Active"), ("Active", "In Review"), ("In Review", "Completed"), ("Completed", "Archived")],
)
async def test_valid_transitions(service, from_status, to_status):
    cycle = _mock_cycle(status=from_status)
    service.repo.get_with_lead = AsyncMock(return_value=cycle)
    service.repo.update = AsyncMock(return_value=cycle)

    data = ReviewCycleUpdate(status=to_status)
    await service.update_cycle(1, data)
    service.db.commit.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "from_status,to_status",
    [
        ("Draft", "Completed"),
        ("Draft", "In Review"),
        ("Active", "Archived"),
        ("Archived", "Draft"),
        ("Completed", "Active"),
    ],
)
async def test_invalid_transitions(service, from_status, to_status):
    cycle = _mock_cycle(status=from_status)
    service.repo.get_with_lead = AsyncMock(return_value=cycle)

    data = ReviewCycleUpdate(status=to_status)
    with pytest.raises(AppException, match="Cannot transition"):
        await service.update_cycle(1, data)


# ---------------------------------------------------------------------------
# Delete guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_only_draft(service):
    cycle = _mock_cycle(status="Active")
    service.repo.get_by_id = AsyncMock(return_value=cycle)

    with pytest.raises(ConflictException, match="Draft"):
        await service.delete_cycle(1)


@pytest.mark.asyncio
async def test_delete_blocked_by_evidence(service):
    cycle = _mock_cycle(status="Draft")
    service.repo.get_by_id = AsyncMock(return_value=cycle)

    # Mock evidence count > 0
    mock_result = MagicMock()
    mock_result.scalar.return_value = 3
    service.db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(ConflictException, match="evidence"):
        await service.delete_cycle(1)


@pytest.mark.asyncio
async def test_delete_success(service):
    cycle = _mock_cycle(status="Draft")
    service.repo.get_by_id = AsyncMock(return_value=cycle)
    service.repo.delete = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalar.return_value = 0
    service.db.execute = AsyncMock(return_value=mock_result)

    await service.delete_cycle(1)
    service.repo.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_not_found(service):
    service.repo.get_by_id = AsyncMock(return_value=None)
    with pytest.raises(NotFoundException):
        await service.delete_cycle(999)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stats(service):
    cycle = _mock_cycle(due_date=int(time.time()) + 86400 * 10)
    service.repo.get_by_id = AsyncMock(return_value=cycle)

    mock_result = MagicMock()
    mock_result.scalar.return_value = 0
    service.db.execute = AsyncMock(return_value=mock_result)

    stats = await service.get_stats(1)
    assert "controls_tested_pct" in stats
    assert "evidence_count" in stats
    assert "days_remaining" in stats


@pytest.mark.asyncio
async def test_get_stats_not_found(service):
    service.repo.get_by_id = AsyncMock(return_value=None)
    with pytest.raises(NotFoundException):
        await service.get_stats(999)
