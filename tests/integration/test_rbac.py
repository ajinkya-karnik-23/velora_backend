"""Integration tests for RBAC enforcement."""

from __future__ import annotations

import pytest

from app.schemas.user import UserCreate


@pytest.mark.asyncio
async def test_admin_can_manage_users(client, seeded_users):
    resp = await client.get("/api/v1/users/get-user-stats", headers=seeded_users["Admin"]["headers"])
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auditor_cannot_manage_users(client, seeded_users):
    resp = await client.get("/api/v1/users/get-user-stats", headers=seeded_users["Auditor"]["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_manage_users(client, seeded_users):
    resp = await client.get("/api/v1/users/get-user-stats", headers=seeded_users["Viewer"]["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_create_user(client, seeded_users):
    resp = await client.post(
        "/api/v1/users/create-user",
        json={
            "user_name": "new",
            "email": "new@test.com",
            "password": "Test@12345678",
            "role_ids": [],
        },
        headers=seeded_users["Viewer"]["headers"],
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderator_can_manage_clients(client, seeded_users):
    resp = await client.post(
        "/api/v1/clients/create-client",
        json={
            "client_code": "MOD-001",
            "client_name": "Mod Client",
            "definition_scope": "scope",
            "reference_documents": "docs",
        },
        headers=seeded_users["Moderator"]["headers"],
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_auditor_cannot_create_client(client, seeded_users):
    resp = await client.post(
        "/api/v1/clients/create-client",
        json={
            "client_code": "AUD-001",
            "client_name": "Aud Client",
            "definition_scope": "scope",
            "reference_documents": "docs",
        },
        headers=seeded_users["Auditor"]["headers"],
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_upload_evidence(client, seeded_users):
    resp = await client.post(
        "/api/v1/evidence/upload-evidence",
        data={"cycle_id": "1"},
        files={"file": ("test.pdf", b"data", "application/pdf")},
        headers=seeded_users["Viewer"]["headers"],
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_authenticated_can_list_users(client, seeded_users):
    resp = await client.get("/api/v1/users/list-users", headers=seeded_users["Viewer"]["headers"])
    assert resp.status_code == 200
