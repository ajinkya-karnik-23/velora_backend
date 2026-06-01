"""Integration tests for evidence lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
@patch("app.services.evidence_service.azure_storage")
async def test_upload_evidence(mock_azure, client, seeded_users, seeded_engagement):
    mock_azure.upload_blob = AsyncMock(return_value="1/1/test.pdf")

    cid = seeded_engagement["cycle"].cycle_id
    resp = await client.post(
        "/api/v1/evidence/upload-evidence",
        data={"cycle_id": str(cid)},
        files={"file": ("test.pdf", b"fake pdf content", "application/pdf")},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["file_name"] == "test.pdf"
    assert data["status"] == "Pending"
    assert data["file_version"] == 1


@pytest.mark.asyncio
@patch("app.services.evidence_service.azure_storage")
async def test_approve_evidence(mock_azure, client, seeded_users, seeded_engagement):
    mock_azure.upload_blob = AsyncMock(return_value="1/1/test.pdf")

    cid = seeded_engagement["cycle"].cycle_id
    # Upload first
    upload_resp = await client.post(
        "/api/v1/evidence/upload-evidence",
        data={"cycle_id": str(cid)},
        files={"file": ("test.pdf", b"content", "application/pdf")},
        headers=seeded_users["Admin"]["headers"],
    )
    eid = upload_resp.json()["evidence_id"]

    # Approve
    resp = await client.put(
        "/api/v1/evidence/update-evidence-status",
        params={"evidence_id": eid},
        json={"status": "Approved", "comments": "looks good"},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Approved"


@pytest.mark.asyncio
@patch("app.services.evidence_service.azure_storage")
async def test_reject_evidence(mock_azure, client, seeded_users, seeded_engagement):
    mock_azure.upload_blob = AsyncMock(return_value="1/1/test.pdf")

    cid = seeded_engagement["cycle"].cycle_id
    upload_resp = await client.post(
        "/api/v1/evidence/upload-evidence",
        data={"cycle_id": str(cid)},
        files={"file": ("reject.pdf", b"content", "application/pdf")},
        headers=seeded_users["Admin"]["headers"],
    )
    eid = upload_resp.json()["evidence_id"]

    resp = await client.put(
        "/api/v1/evidence/update-evidence-status",
        params={"evidence_id": eid},
        json={"status": "Rejected", "comments": "not complete"},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Rejected"


@pytest.mark.asyncio
@patch("app.services.evidence_service.azure_storage")
async def test_download_evidence(mock_azure, client, seeded_users, seeded_engagement):
    mock_azure.upload_blob = AsyncMock(return_value="1/1/test.pdf")
    mock_azure.download_blob_sas_url = AsyncMock(return_value="https://sas.url/test.pdf")

    cid = seeded_engagement["cycle"].cycle_id
    upload_resp = await client.post(
        "/api/v1/evidence/upload-evidence",
        data={"cycle_id": str(cid)},
        files={"file": ("dl.pdf", b"content", "application/pdf")},
        headers=seeded_users["Admin"]["headers"],
    )
    eid = upload_resp.json()["evidence_id"]

    resp = await client.get(
        "/api/v1/evidence/download-evidence",
        params={"evidence_id": eid},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 200
    assert "url" in resp.json()


@pytest.mark.asyncio
@patch("app.services.evidence_service.azure_storage")
async def test_delete_evidence_admin_only(mock_azure, client, seeded_users, seeded_engagement):
    mock_azure.upload_blob = AsyncMock(return_value="1/1/test.pdf")
    mock_azure.delete_blob = AsyncMock()

    cid = seeded_engagement["cycle"].cycle_id
    upload_resp = await client.post(
        "/api/v1/evidence/upload-evidence",
        data={"cycle_id": str(cid)},
        files={"file": ("del.pdf", b"content", "application/pdf")},
        headers=seeded_users["Admin"]["headers"],
    )
    eid = upload_resp.json()["evidence_id"]

    # Auditor cannot delete
    resp = await client.delete(
        "/api/v1/evidence/delete-evidence",
        params={"evidence_id": eid},
        headers=seeded_users["Auditor"]["headers"],
    )
    assert resp.status_code == 403

    # Admin can delete
    resp = await client.delete(
        "/api/v1/evidence/delete-evidence",
        params={"evidence_id": eid},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_upload_missing_linkage(client, seeded_users):
    resp = await client.post(
        "/api/v1/evidence/upload-evidence",
        files={"file": ("test.pdf", b"data", "application/pdf")},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_evidence(client, seeded_users, seeded_engagement):
    resp = await client.get(
        "/api/v1/evidence/list-evidence",
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "total" in data
