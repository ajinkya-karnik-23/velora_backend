"""Integration tests for engagement team scoping."""

from __future__ import annotations

import pytest

from tests.conftest import make_token


@pytest.mark.asyncio
async def test_auditor_on_team_sees_cycle(client, seeded_users, seeded_engagement):
    """Auditor who is on the team can see the cycle."""
    auditor = seeded_users["Auditor"]
    cid = seeded_engagement["cycle"].cycle_id
    resp = await client.get(
        "/api/v1/review-cycles/get-cycle",
        params={"cycle_id": cid},
        headers=auditor["headers"],
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_always_sees_all(client, seeded_users, seeded_engagement):
    admin = seeded_users["Admin"]
    cid = seeded_engagement["cycle"].cycle_id
    resp = await client.get(
        "/api/v1/review-cycles/get-cycle",
        params={"cycle_id": cid},
        headers=admin["headers"],
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_add_team_member(client, seeded_users, seeded_engagement):
    """Add a new team member to the engagement."""
    viewer = seeded_users["Viewer"]
    cid = seeded_engagement["cycle"].cycle_id
    resp = await client.post(
        f"/api/v1/review-cycles/{cid}/add-team-member",
        json={"user_id": viewer["user_id"], "team_role": "Observer"},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_get_team(client, seeded_users, seeded_engagement):
    cid = seeded_engagement["cycle"].cycle_id
    resp = await client.get(
        f"/api/v1/review-cycles/{cid}/list-team-members",
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 2  # Admin + Auditor from seeded_engagement


@pytest.mark.asyncio
async def test_remove_team_member(client, seeded_users, seeded_engagement):
    auditor = seeded_users["Auditor"]
    cid = seeded_engagement["cycle"].cycle_id
    resp = await client.delete(
        f"/api/v1/review-cycles/{cid}/remove-team-member",
        params={"user_id": auditor["user_id"]},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 204
