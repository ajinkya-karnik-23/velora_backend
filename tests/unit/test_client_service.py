"""Unit tests for ClientService."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictException, NotFoundException
from app.schemas.client import ClientCreate, ClientUpdate
from app.services.client_service import ClientService


@pytest.fixture
def db():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def service(db):
    return ClientService(db)


def _mock_client(client_id=1):
    c = MagicMock()
    c.client_id = client_id
    c.client_code = "C-001"
    c.client_name = "Test Client"
    c.definition_scope = "scope"
    c.reference_documents = "docs"
    c.compliance_framework = "SOX"
    c.created_time = int(time.time())
    c.updated_time = int(time.time())
    return c


@pytest.mark.asyncio
async def test_create_client(service):
    now = int(time.time())

    async def _fake_create(obj):
        obj.client_id = 1
        obj.created_time = now
        obj.updated_time = now
        return obj

    service.client_repo.create = AsyncMock(side_effect=_fake_create)

    data = ClientCreate(
        client_code="C-001",
        client_name="Test",
        definition_scope="scope",
        reference_documents="docs",
    )
    result = await service.create_client(data)
    assert result.client_id == 1
    service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_client_not_found(service):
    service.client_repo.get_by_id = AsyncMock(return_value=None)
    with pytest.raises(NotFoundException, match="Client not found"):
        await service.get_client(999)


@pytest.mark.asyncio
async def test_get_client_success(service):
    client = _mock_client()
    service.client_repo.get_by_id = AsyncMock(return_value=client)
    result = await service.get_client(1)
    assert result.client_id == 1


@pytest.mark.asyncio
async def test_update_client_not_found(service):
    service.client_repo.get_by_id = AsyncMock(return_value=None)
    with pytest.raises(NotFoundException):
        await service.update_client(999, ClientUpdate(client_name="x"))


@pytest.mark.asyncio
async def test_update_client_success(service):
    client = _mock_client()
    service.client_repo.get_by_id = AsyncMock(return_value=client)
    service.client_repo.update = AsyncMock(return_value=client)
    result = await service.update_client(1, ClientUpdate(client_name="Updated"))
    service.db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_delete_client_blocked_by_cycles(service):
    client = _mock_client()
    service.client_repo.get_by_id = AsyncMock(return_value=client)
    service.client_repo.has_review_cycles = AsyncMock(return_value=True)

    with pytest.raises(ConflictException, match="existing review cycles"):
        await service.delete_client(1)


@pytest.mark.asyncio
async def test_delete_client_success(service):
    client = _mock_client()
    service.client_repo.get_by_id = AsyncMock(return_value=client)
    service.client_repo.has_review_cycles = AsyncMock(return_value=False)
    service.client_repo.delete = AsyncMock()

    await service.delete_client(1)
    service.client_repo.delete.assert_awaited_once()
    service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_client_not_found(service):
    service.client_repo.get_by_id = AsyncMock(return_value=None)
    with pytest.raises(NotFoundException):
        await service.delete_client(999)
