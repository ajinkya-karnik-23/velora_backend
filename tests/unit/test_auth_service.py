"""Unit tests for AuthService."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.core.exceptions import UnauthorizedException
from app.core.security import create_refresh_token, hash_password
from app.services.auth_service import AuthService


@pytest.fixture
def db():
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def service(db):
    return AuthService(db)


def _make_user(
    user_id=1,
    email="admin@test.com",
    password="Test@12345678",
    status="Active",
):
    user = MagicMock()
    user.user_id = user_id
    user.email = email
    user.password_hash = hash_password(password)
    user.status = status
    user.user_name = "admin"
    user.last_login = None
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
    # Provide defaults for columns used in UserOut
    user.phone = None
    user.department = None
    user.job_title = None
    user.location = None
    user.profile_picture = None
    user.two_factor_enabled = False
    user.api_access_enabled = False
    user.created_time = int(time.time())
    user.updated_time = int(time.time())
    return user


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success(service):
    user = _make_user()
    service.user_repo.get_by_email = AsyncMock(return_value=user)
    service.user_repo.get_roles_and_permissions = AsyncMock(
        return_value=(["Admin"], ["can_manage_users"])
    )

    token_resp, refresh = await service.login("admin@test.com", "Test@12345678")

    assert token_resp.access_token
    assert refresh
    assert user.last_login is not None


@pytest.mark.asyncio
async def test_login_wrong_password(service):
    user = _make_user()
    service.user_repo.get_by_email = AsyncMock(return_value=user)

    with pytest.raises(UnauthorizedException, match="Invalid email or password"):
        await service.login("admin@test.com", "wrongpassword")


@pytest.mark.asyncio
async def test_login_user_not_found(service):
    service.user_repo.get_by_email = AsyncMock(return_value=None)

    with pytest.raises(UnauthorizedException, match="Invalid email or password"):
        await service.login("missing@test.com", "anything")


@pytest.mark.asyncio
async def test_login_deactivated_user(service):
    user = _make_user(status="Deactivated")
    service.user_repo.get_by_email = AsyncMock(return_value=user)

    with pytest.raises(UnauthorizedException, match="deactivated"):
        await service.login("admin@test.com", "Test@12345678")


# ---------------------------------------------------------------------------
# Refresh tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_success(service):
    user = _make_user()
    refresh_token = create_refresh_token({"sub": 1, "roles": ["Admin"], "permissions": []})
    service.user_repo.get_by_id = AsyncMock(return_value=user)
    service.user_repo.get_roles_and_permissions = AsyncMock(
        return_value=(["Admin"], [])
    )

    token_resp, new_refresh = await service.refresh(refresh_token)
    assert token_resp.access_token
    assert new_refresh


@pytest.mark.asyncio
async def test_refresh_invalid_token(service):
    with pytest.raises(UnauthorizedException, match="Invalid or expired"):
        await service.refresh("garbage.token.data")


@pytest.mark.asyncio
async def test_refresh_deactivated_user(service):
    user = _make_user(status="Deactivated")
    refresh_token = create_refresh_token({"sub": 1, "roles": ["Admin"], "permissions": []})
    service.user_repo.get_by_id = AsyncMock(return_value=user)

    with pytest.raises(UnauthorizedException, match="not found or deactivated"):
        await service.refresh(refresh_token)


# ---------------------------------------------------------------------------
# get_me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_me_success(service):
    user = _make_user()
    service.user_repo.get_with_roles_permissions = AsyncMock(return_value=user)
    service.user_repo.get_roles_and_permissions = AsyncMock(
        return_value=(["Admin"], ["can_manage_users"])
    )

    result = await service.get_me(1)
    assert result.user_id == 1
    assert "Admin" in result.roles


@pytest.mark.asyncio
async def test_get_me_not_found(service):
    service.user_repo.get_with_roles_permissions = AsyncMock(return_value=None)

    with pytest.raises(UnauthorizedException, match="User not found"):
        await service.get_me(999)
