"""Unit tests for EvidenceService."""

from __future__ import annotations

import io
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import AppException, ConflictException, ForbiddenException, NotFoundException
from app.schemas.evidence import EvidenceUpdate
from app.services.evidence_service import EvidenceService, ALLOWED_MIME_TYPES, MAX_FILE_SIZE


@pytest.fixture
def db():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def service(db):
    return EvidenceService(db)


def _mock_evidence(evidence_id=1, uploaded_by=1, status="Pending", cycle_id=1):
    ev = MagicMock()
    ev.evidence_id = evidence_id
    ev.file_name = "test.pdf"
    ev.file_type = "application/pdf"
    ev.file_size = 1024
    ev.file_path = "1/1/test.pdf"
    ev.upload_date = int(time.time())
    ev.uploaded_by = uploaded_by
    ev.cycle_id = cycle_id
    ev.control_id = None
    ev.test_id = None
    ev.status = status
    ev.comments = None
    ev.file_version = 1
    ev.created_time = int(time.time())
    ev.updated_time = int(time.time())
    ev.uploader = MagicMock(user_name="admin")
    ev.review_cycle = MagicMock(name="Test Cycle")
    # Fix: MagicMock's name attribute is special, set it explicitly
    ev.review_cycle.name = "Test Cycle"
    ev.control = None
    ev.test = None
    return ev


def _mock_upload_file(content=b"fake pdf content", content_type="application/pdf", filename="test.pdf"):
    f = AsyncMock()
    f.read = AsyncMock(return_value=content)
    f.content_type = content_type
    f.filename = filename
    return f


ADMIN_USER = {"sub": 1, "roles": ["Admin"], "permissions": ["can_upload", "can_approve", "can_reject"]}
AUDITOR_USER = {"sub": 2, "roles": ["Auditor"], "permissions": ["can_upload"]}


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.evidence_service.azure_storage")
async def test_upload_success(mock_azure, service):
    mock_azure.upload_blob = AsyncMock(return_value="1/1/test.pdf")
    service.repo.create = AsyncMock(return_value=MagicMock(evidence_id=1))
    service.repo.get_detail = AsyncMock(return_value=_mock_evidence())

    file = _mock_upload_file()
    result = await service.upload(file, cycle_id=1, control_id=None, test_id=None, comments=None, current_user=ADMIN_USER)
    assert result.evidence_id == 1


@pytest.mark.asyncio
async def test_upload_invalid_mime(service):
    file = _mock_upload_file(content_type="application/exe")
    with pytest.raises(AppException, match="not allowed"):
        await service.upload(file, 1, None, None, None, ADMIN_USER)


@pytest.mark.asyncio
async def test_upload_too_large(service):
    big_content = b"x" * (MAX_FILE_SIZE + 1)
    file = _mock_upload_file(content=big_content)
    with pytest.raises(AppException, match="maximum size"):
        await service.upload(file, 1, None, None, None, ADMIN_USER)


@pytest.mark.asyncio
@patch("app.services.evidence_service.azure_storage")
async def test_upload_blob_failure_rolls_back(mock_azure, service):
    mock_azure.upload_blob = AsyncMock(side_effect=Exception("Azure down"))
    service.repo.create = AsyncMock(return_value=MagicMock(evidence_id=1))

    file = _mock_upload_file()
    with pytest.raises(AppException, match="Failed to upload"):
        await service.upload(file, 1, None, None, None, ADMIN_USER)
    service.db.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# Approve / Reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_success(service):
    ev = _mock_evidence()
    service.repo.get_detail = AsyncMock(return_value=ev)

    result = await service.approve_reject(1, "Approved", "looks good", ADMIN_USER)
    assert ev.status == "Approved"
    service.db.commit.assert_awaited_once()
    # test_log should have been added
    service.db.add.assert_called_once()


@pytest.mark.asyncio
async def test_reject_success(service):
    ev = _mock_evidence()
    service.repo.get_detail = AsyncMock(return_value=ev)

    result = await service.approve_reject(1, "Rejected", "needs revision", ADMIN_USER)
    assert ev.status == "Rejected"


@pytest.mark.asyncio
async def test_approve_reject_invalid_status(service):
    with pytest.raises(AppException, match="must be"):
        await service.approve_reject(1, "Invalid", None, ADMIN_USER)


@pytest.mark.asyncio
async def test_approve_evidence_not_found(service):
    service.repo.get_detail = AsyncMock(return_value=None)
    with pytest.raises(NotFoundException):
        await service.approve_reject(999, "Approved", None, ADMIN_USER)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.evidence_service.azure_storage")
async def test_delete_admin_only(mock_azure, service):
    ev = _mock_evidence()
    service.repo.get_by_id = AsyncMock(return_value=ev)
    service.repo.delete = AsyncMock()
    mock_azure.delete_blob = AsyncMock()

    await service.delete(1, ADMIN_USER)
    service.repo.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_non_admin_forbidden(service):
    with pytest.raises(ForbiddenException, match="Only Admin"):
        await service.delete(1, AUDITOR_USER)


@pytest.mark.asyncio
async def test_delete_not_found(service):
    service.repo.get_by_id = AsyncMock(return_value=None)
    with pytest.raises(NotFoundException):
        await service.delete(999, ADMIN_USER)


# ---------------------------------------------------------------------------
# Ownership check
# ---------------------------------------------------------------------------


def test_assert_owner_admin_bypass():
    ev = _mock_evidence(uploaded_by=99)
    # Should not raise for Admin
    EvidenceService._assert_owner_or_privileged(ev, ADMIN_USER)


def test_assert_owner_moderator_bypass():
    ev = _mock_evidence(uploaded_by=99)
    EvidenceService._assert_owner_or_privileged(ev, {"sub": 5, "roles": ["Moderator"]})


def test_assert_owner_is_uploader():
    ev = _mock_evidence(uploaded_by=2)
    EvidenceService._assert_owner_or_privileged(ev, AUDITOR_USER)


def test_assert_owner_forbidden():
    ev = _mock_evidence(uploaded_by=99)
    with pytest.raises(ForbiddenException, match="Not the owner"):
        EvidenceService._assert_owner_or_privileged(ev, AUDITOR_USER)


# ---------------------------------------------------------------------------
# Re-upload versioning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.evidence_service.azure_storage")
async def test_reupload_increments_version(mock_azure, service):
    ev = _mock_evidence()
    ev.file_version = 1
    service.repo.get_detail = AsyncMock(return_value=ev)
    mock_azure.rename_blob = AsyncMock()
    mock_azure.upload_blob = AsyncMock(return_value="1/1/new.pdf")

    file = _mock_upload_file(filename="new.pdf")
    result = await service.reupload(1, file, ADMIN_USER)
    assert ev.file_version == 2
    assert ev.status == "Pending"


@pytest.mark.asyncio
async def test_reupload_not_found(service):
    service.repo.get_detail = AsyncMock(return_value=None)
    file = _mock_upload_file()
    with pytest.raises(NotFoundException):
        await service.reupload(999, file, ADMIN_USER)


@pytest.mark.asyncio
async def test_reupload_invalid_mime(service):
    ev = _mock_evidence()
    service.repo.get_detail = AsyncMock(return_value=ev)

    file = _mock_upload_file(content_type="application/exe")
    with pytest.raises(AppException, match="not allowed"):
        await service.reupload(1, file, ADMIN_USER)


# ---------------------------------------------------------------------------
# Download SAS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.evidence_service.azure_storage")
async def test_download_sas_success(mock_azure, service):
    ev = _mock_evidence()
    service.repo.get_detail = AsyncMock(return_value=ev)
    mock_azure.download_blob_sas_url = AsyncMock(return_value="https://sas-url")

    url = await service.download_sas(1, 1, ["Admin"])
    assert url == "https://sas-url"


@pytest.mark.asyncio
async def test_download_sas_no_file(service):
    ev = _mock_evidence()
    ev.file_path = None
    service.repo.get_detail = AsyncMock(return_value=ev)

    with pytest.raises(ConflictException, match="no associated file"):
        await service.download_sas(1, 1, ["Admin"])
