"""Integration tests for review cycle lifecycle."""

from __future__ import annotations

import time

import pytest


@pytest.mark.asyncio
async def test_create_review_cycle(client, seeded_users, seeded_engagement):
    now = int(time.time())
    resp = await client.post(
        "/api/v1/review-cycles/create-cycle",
        json={
            "client_id": seeded_engagement["client"].client_id,
            "review_period": "Q2 2026",
            "name": "New Cycle",
            "start_date": now,
            "due_date": now + 86400 * 30,
        },
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "Draft"


@pytest.mark.asyncio
async def test_list_review_cycles(client, seeded_users, seeded_engagement):
    resp = await client.get(
        "/api/v1/review-cycles/list-cycles",
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_lifecycle_transitions(client, seeded_users, seeded_engagement):
    """Create a Draft cycle and transition through all valid states."""
    now = int(time.time())
    headers = seeded_users["Admin"]["headers"]

    # Create a Draft cycle
    create = await client.post(
        "/api/v1/review-cycles/create-cycle",
        json={
            "client_id": seeded_engagement["client"].client_id,
            "review_period": "Q3",
            "name": "Lifecycle Test",
            "start_date": now,
            "due_date": now + 86400 * 60,
        },
        headers=headers,
    )
    cid = create.json()["cycle_id"]

    # Draft → Active
    resp = await client.put(
        "/api/v1/review-cycles/update-cycle",
        params={"cycle_id": cid},
        json={"status": "Active"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Active"

    # Active → In Review
    resp = await client.put(
        "/api/v1/review-cycles/update-cycle",
        params={"cycle_id": cid},
        json={"status": "In Review"},
        headers=headers,
    )
    assert resp.status_code == 200

    # In Review → Completed
    resp = await client.put(
        "/api/v1/review-cycles/update-cycle",
        params={"cycle_id": cid},
        json={"status": "Completed"},
        headers=headers,
    )
    assert resp.status_code == 200

    # Completed → Archived
    resp = await client.put(
        "/api/v1/review-cycles/update-cycle",
        params={"cycle_id": cid},
        json={"status": "Archived"},
        headers=headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invalid_lifecycle_transition(client, seeded_users, seeded_engagement):
    now = int(time.time())
    headers = seeded_users["Admin"]["headers"]

    create = await client.post(
        "/api/v1/review-cycles/create-cycle",
        json={
            "client_id": seeded_engagement["client"].client_id,
            "review_period": "Q4",
            "name": "Invalid Transition",
            "start_date": now,
            "due_date": now + 86400,
        },
        headers=headers,
    )
    cid = create.json()["cycle_id"]

    # Draft → Completed (skip Active) should fail
    resp = await client.put(
        "/api/v1/review-cycles/update-cycle",
        params={"cycle_id": cid},
        json={"status": "Completed"},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_draft_cycle(client, seeded_users, seeded_engagement):
    now = int(time.time())
    headers = seeded_users["Admin"]["headers"]

    create = await client.post(
        "/api/v1/review-cycles/create-cycle",
        json={
            "client_id": seeded_engagement["client"].client_id,
            "review_period": "Q1",
            "name": "To Delete",
            "start_date": now,
            "due_date": now + 86400,
        },
        headers=headers,
    )
    cid = create.json()["cycle_id"]

    resp = await client.delete(
        "/api/v1/review-cycles/delete-cycle",
        params={"cycle_id": cid},
        headers=headers,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_non_draft_cycle_fails(client, seeded_users, seeded_engagement):
    """Cannot delete an Active cycle."""
    cid = seeded_engagement["cycle"].cycle_id  # status is Active
    resp = await client.delete(
        "/api/v1/review-cycles/delete-cycle",
        params={"cycle_id": cid},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_cycle_stats(client, seeded_users, seeded_engagement):
    cid = seeded_engagement["cycle"].cycle_id
    resp = await client.get(
        "/api/v1/review-cycles/get-cycle-stats",
        params={"cycle_id": cid},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "controls_tested_pct" in data
    assert "evidence_count" in data
    assert "days_remaining" in data
