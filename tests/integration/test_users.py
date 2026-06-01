"""Integration tests for User CRUD."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_user(client, seeded_users):
    resp = await client.post(
        "/api/v1/users/create-user",
        json={
            "user_name": "new_user",
            "email": "newuser@test.com",
            "password": "StrongPass1!",
            "role_ids": [],
        },
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@test.com"
    assert data["status"] == "Active"


@pytest.mark.asyncio
async def test_list_users_paginated(client, seeded_users):
    resp = await client.get(
        "/api/v1/users/list-users",
        params={"page": 1, "page_size": 2},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "total" in data
    assert data["page"] == 1
    assert data["page_size"] == 2


@pytest.mark.asyncio
async def test_list_users_with_filter(client, seeded_users):
    resp = await client.get(
        "/api/v1/users/list-users",
        params={"status": "Active"},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 200
    for u in resp.json()["data"]:
        assert u["status"] == "Active"


@pytest.mark.asyncio
async def test_get_user(client, seeded_users):
    admin = seeded_users["Admin"]
    resp = await client.get(
        "/api/v1/users/get-user",
        params={"user_id": admin["user_id"]},
        headers=admin["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["user_id"] == admin["user_id"]


@pytest.mark.asyncio
async def test_get_user_not_found(client, seeded_users):
    resp = await client.get(
        "/api/v1/users/get-user",
        params={"user_id": 99999},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_user_self(client, seeded_users):
    auditor = seeded_users["Auditor"]
    resp = await client.put(
        "/api/v1/users/update-user",
        params={"user_id": auditor["user_id"]},
        json={"user_name": "updated_auditor"},
        headers=auditor["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["user_name"] == "updated_auditor"


@pytest.mark.asyncio
async def test_soft_delete_user(client, seeded_users):
    # Create a user to delete
    create_resp = await client.post(
        "/api/v1/users/create-user",
        json={
            "user_name": "to_delete",
            "email": "delete_me@test.com",
            "password": "StrongPass1!",
            "role_ids": [],
        },
        headers=seeded_users["Admin"]["headers"],
    )
    user_id = create_resp.json()["user_id"]

    resp = await client.delete(
        "/api/v1/users/delete-user",
        params={"user_id": user_id},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Deactivated"
