"""Integration tests for pagination response envelope."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_pagination_envelope(client, seeded_users):
    headers = seeded_users["Admin"]["headers"]
    resp = await client.get("/api/v1/users/list-users", params={"page": 1, "page_size": 2}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert isinstance(data["data"], list)
    assert isinstance(data["total"], int)


@pytest.mark.asyncio
async def test_pagination_respects_page_size(client, seeded_users):
    headers = seeded_users["Admin"]["headers"]
    resp = await client.get("/api/v1/users/list-users", params={"page": 1, "page_size": 1}, headers=headers)
    data = resp.json()
    assert len(data["data"]) <= 1


@pytest.mark.asyncio
async def test_pagination_page_out_of_range(client, seeded_users):
    headers = seeded_users["Admin"]["headers"]
    resp = await client.get("/api/v1/users/list-users", params={"page": 999, "page_size": 10}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"] == []
    assert data["total"] >= 0


@pytest.mark.asyncio
async def test_pagination_max_page_size(client, seeded_users):
    headers = seeded_users["Admin"]["headers"]
    # page_size > 100 should be rejected
    resp = await client.get("/api/v1/users/list-users", params={"page_size": 101}, headers=headers)
    assert resp.status_code == 422
