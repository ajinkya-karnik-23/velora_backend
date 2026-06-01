"""Integration tests for Client CRUD."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_client(client, seeded_users):
    resp = await client.post(
        "/api/v1/clients/create-client",
        json={
            "client_code": "INT-001",
            "client_name": "Integration Client",
            "definition_scope": "Full scope",
            "reference_documents": "Doc 1, Doc 2",
            "compliance_framework": "SOX",
        },
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["client_code"] == "INT-001"
    assert data["client_name"] == "Integration Client"


@pytest.mark.asyncio
async def test_list_clients(client, seeded_users):
    # Create two clients
    for i in range(2):
        await client.post(
            "/api/v1/clients/create-client",
            json={
                "client_code": f"LIST-{i}",
                "client_name": f"Client {i}",
                "definition_scope": "s",
                "reference_documents": "r",
            },
            headers=seeded_users["Admin"]["headers"],
        )

    resp = await client.get("/api/v1/clients/list-clients", headers=seeded_users["Admin"]["headers"])
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2


@pytest.mark.asyncio
async def test_update_client(client, seeded_users):
    create_resp = await client.post(
        "/api/v1/clients/create-client",
        json={
            "client_code": "UPD-001",
            "client_name": "Before Update",
            "definition_scope": "s",
            "reference_documents": "r",
        },
        headers=seeded_users["Admin"]["headers"],
    )
    cid = create_resp.json()["client_id"]

    resp = await client.put(
        "/api/v1/clients/update-client",
        params={"client_id": cid},
        json={"client_name": "After Update"},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["client_name"] == "After Update"


@pytest.mark.asyncio
async def test_delete_client_no_cycles(client, seeded_users):
    create_resp = await client.post(
        "/api/v1/clients/create-client",
        json={
            "client_code": "DEL-001",
            "client_name": "Delete Me",
            "definition_scope": "s",
            "reference_documents": "r",
        },
        headers=seeded_users["Admin"]["headers"],
    )
    cid = create_resp.json()["client_id"]

    resp = await client.delete(
        "/api/v1/clients/delete-client",
        params={"client_id": cid},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_client_blocked_by_cycles(client, seeded_users, seeded_engagement):
    """Cannot delete a client that has review cycles."""
    cid = seeded_engagement["client"].client_id
    resp = await client.delete(
        "/api/v1/clients/delete-client",
        params={"client_id": cid},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_client_not_found(client, seeded_users):
    resp = await client.get(
        "/api/v1/clients/get-client",
        params={"client_id": 99999},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 404
