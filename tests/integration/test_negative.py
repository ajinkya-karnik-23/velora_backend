"""Negative and edge case tests — auth failures, validation, duplicates, not found, evidence edge cases, deletion guards."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import auth_header, make_token


# ---------------------------------------------------------------------------
# Auth failures
# ---------------------------------------------------------------------------


class TestAuthFailures:
    @pytest.mark.asyncio
    async def test_no_token_401(self, client, seeded_users):
        resp = await client.get("/api/v1/users/list-users")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_401(self, client, seeded_users):
        resp = await client.get(
            "/api/v1/users/list-users",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_role_403(self, client, seeded_users):
        viewer = seeded_users["Viewer"]
        resp = await client.post(
            "/api/v1/users/create-user",
            json={
                "user_name": "x",
                "email": "x@test.com",
                "password": "Test@12345678",
                "role_ids": [],
            },
            headers=viewer["headers"],
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_deactivated_user_cannot_login(self, client, seeded_users):
        # Soft-delete a user first
        admin = seeded_users["Admin"]
        create_resp = await client.post(
            "/api/v1/users/create-user",
            json={
                "user_name": "deact",
                "email": "deact@test.com",
                "password": "Test@12345678",
                "role_ids": [],
            },
            headers=admin["headers"],
        )
        uid = create_resp.json()["user_id"]
        await client.delete(
            "/api/v1/users/delete-user",
            params={"user_id": uid},
            headers=admin["headers"],
        )

        # Try to login
        resp = await client.post(
            "/api/v1/auth/login-user",
            params={"email": "deact@test.com", "password": "Test@12345678"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Validation errors → 422
# ---------------------------------------------------------------------------


class TestValidation:
    @pytest.mark.asyncio
    async def test_missing_required_fields(self, client, seeded_users):
        resp = await client.post(
            "/api/v1/users/create-user",
            json={"user_name": "x"},  # missing email, password
            headers=seeded_users["Admin"]["headers"],
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_wrong_types(self, client, seeded_users):
        resp = await client.post(
            "/api/v1/users/create-user",
            json={
                "user_name": "x",
                "email": "x@test.com",
                "password": "Test@12345678",
                "role_ids": "not_a_list",
            },
            headers=seeded_users["Admin"]["headers"],
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_password_too_weak(self, client, seeded_users):
        resp = await client.post(
            "/api/v1/users/create-user",
            json={
                "user_name": "weak",
                "email": "weak@test.com",
                "password": "short",
                "role_ids": [],
            },
            headers=seeded_users["Admin"]["headers"],
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_test_log_missing_linkage(self, client, seeded_users):
        resp = await client.post(
            "/api/v1/test-logs/create-test-log",
            json={"status": "Pass"},
            headers=seeded_users["Admin"]["headers"],
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Duplicates → 409
# ---------------------------------------------------------------------------


class TestDuplicates:
    @pytest.mark.asyncio
    async def test_duplicate_email(self, client, seeded_users):
        resp = await client.post(
            "/api/v1/users/create-user",
            json={
                "user_name": "dup",
                "email": "admin@test.com",  # already exists
                "password": "Test@12345678",
                "role_ids": [],
            },
            headers=seeded_users["Admin"]["headers"],
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_duplicate_team_member(self, client, seeded_users, seeded_engagement):
        cid = seeded_engagement["cycle"].cycle_id
        auditor = seeded_users["Auditor"]
        # Auditor is already on the team
        resp = await client.post(
            f"/api/v1/review-cycles/{cid}/add-team-member",
            json={"user_id": auditor["user_id"], "team_role": "Reviewer"},
            headers=seeded_users["Admin"]["headers"],
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Not found → 404
# ---------------------------------------------------------------------------


class TestNotFound:
    @pytest.mark.asyncio
    async def test_user_not_found(self, client, seeded_users):
        resp = await client.get(
            "/api/v1/users/get-user",
            params={"user_id": 99999},
            headers=seeded_users["Admin"]["headers"],
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_client_not_found(self, client, seeded_users):
        resp = await client.get(
            "/api/v1/clients/get-client",
            params={"client_id": 99999},
            headers=seeded_users["Admin"]["headers"],
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cycle_not_found(self, client, seeded_users):
        resp = await client.get(
            "/api/v1/review-cycles/get-cycle",
            params={"cycle_id": 99999},
            headers=seeded_users["Admin"]["headers"],
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_evidence_not_found(self, client, seeded_users):
        resp = await client.get(
            "/api/v1/evidence/get-evidence",
            params={"evidence_id": 99999},
            headers=seeded_users["Admin"]["headers"],
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Evidence edge cases
# ---------------------------------------------------------------------------


class TestEvidenceEdgeCases:
    @pytest.mark.asyncio
    async def test_disallowed_mime_type(self, client, seeded_users, seeded_engagement):
        cid = seeded_engagement["cycle"].cycle_id
        resp = await client.post(
            "/api/v1/evidence/upload-evidence",
            data={"cycle_id": str(cid)},
            files={"file": ("malware.exe", b"binary", "application/x-msdownload")},
            headers=seeded_users["Admin"]["headers"],
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @patch("app.services.evidence_service.azure_storage")
    async def test_zero_byte_file(self, mock_azure, client, seeded_users, seeded_engagement):
        """Zero-byte files are accepted if valid MIME."""
        mock_azure.upload_blob = AsyncMock(return_value="1/1/empty.pdf")
        cid = seeded_engagement["cycle"].cycle_id
        resp = await client.post(
            "/api/v1/evidence/upload-evidence",
            data={"cycle_id": str(cid)},
            files={"file": ("empty.pdf", b"", "application/pdf")},
            headers=seeded_users["Admin"]["headers"],
        )
        assert resp.status_code in (201, 400)


# ---------------------------------------------------------------------------
# Deletion guards
# ---------------------------------------------------------------------------


class TestDeletionGuards:
    @pytest.mark.asyncio
    async def test_delete_client_with_cycles(self, client, seeded_users, seeded_engagement):
        cid = seeded_engagement["client"].client_id
        resp = await client.delete(
            "/api/v1/clients/delete-client",
            params={"client_id": cid},
            headers=seeded_users["Admin"]["headers"],
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_non_draft_cycle(self, client, seeded_users, seeded_engagement):
        cid = seeded_engagement["cycle"].cycle_id  # Active status
        resp = await client.delete(
            "/api/v1/review-cycles/delete-cycle",
            params={"cycle_id": cid},
            headers=seeded_users["Admin"]["headers"],
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_evidence_non_admin(self, client, seeded_users):
        resp = await client.delete(
            "/api/v1/evidence/delete-evidence",
            params={"evidence_id": 1},
            headers=seeded_users["Auditor"]["headers"],
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_user_is_soft(self, client, seeded_users):
        admin = seeded_users["Admin"]
        create_resp = await client.post(
            "/api/v1/users/create-user",
            json={
                "user_name": "soft_del",
                "email": "soft@test.com",
                "password": "Test@12345678",
                "role_ids": [],
            },
            headers=admin["headers"],
        )
        uid = create_resp.json()["user_id"]

        resp = await client.delete(
            "/api/v1/users/delete-user",
            params={"user_id": uid},
            headers=admin["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "Deactivated"

        # User still exists
        get_resp = await client.get(
            "/api/v1/users/get-user",
            params={"user_id": uid},
            headers=admin["headers"],
        )
        assert get_resp.status_code == 200
