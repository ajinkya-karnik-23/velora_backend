"""Integration tests for auth flow — login, refresh, logout, /me."""

from __future__ import annotations

import pytest
import pytest_asyncio

from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_login_success(client, seeded_users):
    resp = await client.post(
        "/api/v1/auth/login-user",
        params={"email": "admin@test.com", "password": "Test@12345678"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # Refresh token set in cookie
    assert "refresh_token" in resp.cookies or "set-cookie" in resp.headers


@pytest.mark.asyncio
async def test_login_wrong_password(client, seeded_users):
    resp = await client.post(
        "/api/v1/auth/login-user",
        params={"email": "admin@test.com", "password": "WrongPass123!"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoint(client, seeded_users):
    admin = seeded_users["Admin"]
    resp = await client.get("/api/v1/auth/get-current-user", headers=admin["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "admin@test.com"


@pytest.mark.asyncio
async def test_me_no_token(client, seeded_users):
    resp = await client.get("/api/v1/auth/get-current-user")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout(client, seeded_users):
    resp = await client.post("/api/v1/auth/logout-user")
    assert resp.status_code == 200
    # Cookie should be cleared (max-age=0 or deleted)
    assert "refresh_token" not in resp.cookies or resp.cookies.get("refresh_token") == ""


@pytest.mark.asyncio
async def test_protected_route_with_expired_token(client, seeded_users):
    resp = await client.get(
        "/api/v1/auth/get-current-user",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401
