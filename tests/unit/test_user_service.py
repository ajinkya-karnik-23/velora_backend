"""Unit tests for UserService."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.core.security import hash_password
from app.schemas.user import UserCreate
from app.services.user_service import UserService


@pytest.fixture
def db():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def service(db):
    return UserService(db)


def _mock_user(user_id=1, email="test@test.com", status="Active"):
    user = MagicMock()
    user.user_id = user_id
    user.email = email
    user.status = status
    user.user_name = "testuser"
    user.password_hash = hash_password("Test@12345678")
    user.phone = None
    user.department = None
    user.job_title = None
    user.location = None
    user.profile_picture = None
    user.two_factor_enabled = False
    user.api_access_enabled = False
    user.last_login = None
    user.created_time = int(time.time())
    user.updated_time = int(time.time())
    cols = []
    for key in [
        "user_id", "user_name", "email", "password_hash", "phone",
        "department", "job_title", "location", "profile_picture",
        "status", "two_factor_enabled", "api_access_enabled",
        "last_login", "created_time", "updated_time",
    ]:
        col = MagicMock()
        col.key = key
        cols.append(col)
    table = MagicMock()
    table.columns = cols
    user.__table__ = table
    return user


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_user_success(service):
    service.user_repo.get_by_email = AsyncMock(return_value=None)
    service.user_repo.get_roles_and_permissions = AsyncMock(
        return_value=(["Auditor"], ["can_upload"])
    )

    now = int(time.time())

    # When flush is called, simulate DB populating auto fields
    async def _fake_flush():
        for call_args in service.db.add.call_args_list:
            obj = call_args[0][0]
            if hasattr(obj, "user_id") and obj.user_id is None:
                obj.user_id = 1
            if hasattr(obj, "created_time") and (obj.created_time is None or obj.created_time == 0):
                obj.created_time = now
            if hasattr(obj, "updated_time") and (obj.updated_time is None or obj.updated_time == 0):
                obj.updated_time = now
            if hasattr(obj, "two_factor_enabled") and obj.two_factor_enabled is None:
                obj.two_factor_enabled = False
            if hasattr(obj, "api_access_enabled") and obj.api_access_enabled is None:
                obj.api_access_enabled = False

    service.db.flush = AsyncMock(side_effect=_fake_flush)

    data = UserCreate(
        user_name="new_user",
        email="new@test.com",
        password="Test@12345678",
        role_ids=[1],
    )

    result = await service.create_user(data)
    assert result.email == "new@test.com"
    service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_user_duplicate_email(service):
    service.user_repo.get_by_email = AsyncMock(return_value=_mock_user())

    data = UserCreate(
        user_name="dup",
        email="test@test.com",
        password="Test@12345678",
        role_ids=[],
    )

    with pytest.raises(ConflictException, match="Email already registered"):
        await service.create_user(data)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_user_self_service(service):
    user = _mock_user()
    service.user_repo.get_by_id = AsyncMock(return_value=user)
    service.user_repo.update = AsyncMock(return_value=user)
    service.user_repo.get_roles_and_permissions = AsyncMock(return_value=([], []))

    result = await service.update_user(1, {"user_name": "updated"}, 1, False)
    assert result.user_id == 1


@pytest.mark.asyncio
async def test_update_user_non_admin_other_user(service):
    user = _mock_user(user_id=2)
    service.user_repo.get_by_id = AsyncMock(return_value=user)

    with pytest.raises(ForbiddenException, match="Cannot update another"):
        await service.update_user(2, {"user_name": "hack"}, 1, False)


@pytest.mark.asyncio
async def test_update_user_admin_can_update_others(service):
    user = _mock_user(user_id=2)
    service.user_repo.get_by_id = AsyncMock(return_value=user)
    service.user_repo.update = AsyncMock(return_value=user)
    service.user_repo.get_by_email = AsyncMock(return_value=None)
    service.user_repo.get_roles_and_permissions = AsyncMock(return_value=([], []))

    result = await service.update_user(2, {"email": "new@test.com"}, 1, True)
    assert result.user_id == 2


@pytest.mark.asyncio
async def test_update_user_duplicate_email(service):
    user = _mock_user(user_id=1, email="old@test.com")
    other = _mock_user(user_id=2, email="taken@test.com")
    service.user_repo.get_by_id = AsyncMock(return_value=user)
    service.user_repo.get_by_email = AsyncMock(return_value=other)

    with pytest.raises(ConflictException, match="Email already registered"):
        await service.update_user(1, {"email": "taken@test.com"}, 1, True)


@pytest.mark.asyncio
async def test_update_user_not_found(service):
    service.user_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException, match="User not found"):
        await service.update_user(999, {"user_name": "x"}, 1, True)


# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_soft_delete(service):
    user = _mock_user()
    service.user_repo.get_by_id = AsyncMock(return_value=user)
    service.user_repo.update = AsyncMock(return_value=user)
    service.user_repo.get_roles_and_permissions = AsyncMock(return_value=([], []))

    # After soft-delete the user mock will have status updated
    result = await service.soft_delete(1)
    service.user_repo.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_soft_delete_not_found(service):
    service.user_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException):
        await service.soft_delete(999)


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_roles_success(service):
    user = _mock_user()
    service.user_repo.get_by_id = AsyncMock(return_value=user)
    service.user_repo.get_roles_and_permissions = AsyncMock(return_value=(["Admin"], []))

    # Mock execute for deleting existing roles
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    service.db.execute = AsyncMock(return_value=mock_result)

    result = await service.update_roles(1, [1, 2])
    service.db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_update_roles_user_not_found(service):
    service.user_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException):
        await service.update_roles(999, [1])


# ---------------------------------------------------------------------------
# Password validation (schema-level)
# ---------------------------------------------------------------------------


def test_password_too_weak():
    with pytest.raises(Exception):
        UserCreate(
            user_name="u", email="a@b.com", password="short", role_ids=[]
        )


def test_password_matches_email():
    with pytest.raises(Exception):
        UserCreate(
            user_name="u",
            email="Test@12345678",
            password="Test@12345678",
            role_ids=[],
        )
